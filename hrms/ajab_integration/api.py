# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt

"""Frappe HR <-> Ajab (AI interviews).

1. An HR or System Manager pastes the Ajab address and a scoped Ajab API key
   in Ajab Integration Settings (connect). HR checks the key with GET /me and,
   when the key has webhooks:manage, registers this site's webhook endpoint
   in Ajab and stores the signing secret (encrypted).
2. Job Opening -> "Send to Ajab" creates or updates the Ajab job.
3. Job Applicant -> "Schedule AI interview" creates the Ajab candidate (or
   reuses the one with the same email) and the interview; Ajab emails the
   link to the applicant.
4. Ajab calls webhook() when the interview starts, ends, is cancelled or
   scored. HR verifies the signature and updates the Job Applicant; on
   "analysis completed" it reads the scores from GET /interviews/:id/results.
   "Refresh from Ajab" does the same on demand.
5. Employee -> "Sync to Ajab" (or all active employees from the settings)
   creates or updates the Ajab team member via POST /employee-sync.
"""

import hashlib
import hmac
import json
import time

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cstr, get_url, getdate, now_datetime, strip_html_tags
from frappe.utils.password import remove_encrypted_password

from hrms.ajab_integration.client import SETTINGS, AjabError, call, normalize_url, request

MANAGERS = ("System Manager", "HR Manager")
WEBHOOK_METHOD = "hrms.ajab_integration.api.webhook"
WEBHOOK_EVENTS = [
	"interview.created",
	"interview.started",
	"interview.completed",
	"interview.cancelled",
	"interview.analysis.completed",
]
EVENT_STATUS = {
	"interview.started": "recording",
	"interview.completed": "completed",
	"interview.cancelled": "cancelled",
}
OPEN_INTERVIEW_STATES = ("created", "recording", "completed")
SIGNATURE_TOLERANCE_SECONDS = 300


# ---------------------------------------------------------------- settings


def _settings():
	settings = frappe.get_single(SETTINGS)
	settings.flags.ignore_permissions = True
	return settings


def _apply_key_info(settings, me: dict) -> None:
	data = me.get("data") or {}
	org = data.get("organization") or {}
	key = data.get("key") or {}
	settings.organization_id = org.get("id")
	settings.organization_name = org.get("name")
	settings.key_name = key.get("name")
	settings.key_scopes = ", ".join(key.get("scopes") or [])


def _has_scope(settings, scope: str) -> bool:
	return scope in [s.strip() for s in cstr(settings.key_scopes).split(",")]


def webhook_endpoint() -> str:
	return get_url(f"/api/method/{WEBHOOK_METHOD}")


@frappe.whitelist()
def is_connected() -> bool:
	"""For form buttons: any desk user may know whether Ajab is connected."""
	return frappe.db.get_single_value(SETTINGS, "status") == "Connected"


@frappe.whitelist(methods=["POST"])
def connect(ajab_url: str, api_key: str) -> dict:
	"""Check the key against Ajab, save the connection and register the webhook."""
	frappe.only_for(MANAGERS)
	url = normalize_url(ajab_url)
	api_key = (api_key or "").strip()
	if not api_key:
		frappe.throw(_("Paste the Ajab API key"))
	try:
		me = request("GET", "/me", url=url, api_key=api_key)
	except AjabError as e:
		frappe.throw(e.message, title=_("Could not connect to Ajab"))

	settings = _settings()
	settings.ajab_url = url
	settings.api_key = api_key
	settings.status = "Connected"
	settings.connected_at = now_datetime()
	_apply_key_info(settings, me)
	settings.save()

	webhook = None
	if _has_scope(settings, "webhooks:manage"):
		webhook = _register_webhook(settings)
	return {
		"organization": settings.organization_name,
		"scopes": settings.key_scopes,
		"webhook": webhook,
	}


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
	frappe.only_for(MANAGERS)
	settings = _settings()
	me = call("GET", "/me")
	_apply_key_info(settings, me)
	settings.save()
	return {"organization": settings.organization_name, "scopes": settings.key_scopes}


def _register_webhook(settings) -> dict:
	"""Point the Ajab organisation's webhook at this site and store the secret.

	Ajab has one webhook per organisation, so this replaces any other URL.
	The full secret is returned only when the webhook is created or the
	secret is rotated, so an existing webhook gets a fresh secret.
	"""
	endpoint = webhook_endpoint()
	try:
		res = request(
			"PATCH", "/webhooks/config", json={"url": endpoint, "events": WEBHOOK_EVENTS, "isActive": True}
		)
		secret = (res.get("data") or {}).get("secret") or ""
		if "…" in secret or not secret.startswith("whsec_"):
			res = request("POST", "/webhooks/regenerate-secret")
			secret = (res.get("data") or {}).get("secret") or ""
	except AjabError as e:
		settings.webhook_status = "Not registered"
		settings.save()
		return {"registered": False, "message": e.message}

	settings.webhook_secret = secret
	settings.webhook_url = endpoint
	settings.webhook_status = "Registered"
	settings.save()
	return {"registered": True, "url": endpoint}


@frappe.whitelist(methods=["POST"])
def register_webhook() -> dict:
	frappe.only_for(MANAGERS)
	settings = _settings()
	if settings.status != "Connected":
		frappe.throw(_("Connect to Ajab first"))
	result = _register_webhook(settings)
	if not result["registered"]:
		frappe.throw(result["message"], title=_("Webhook not registered"))
	return result


@frappe.whitelist(methods=["POST"])
def send_test_webhook() -> dict:
	frappe.only_for(MANAGERS)
	call("POST", "/webhooks/test")
	return {"sent": True}


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	"""Turn off Ajab's webhook to this site (when it is ours) and forget the key."""
	frappe.only_for(MANAGERS)
	settings = _settings()
	if settings.status == "Connected" and settings.webhook_status == "Registered":
		try:
			current = (request("GET", "/webhooks/config").get("data") or {}).get("url")
			if current == settings.webhook_url:
				request("DELETE", "/webhooks/config")
		except AjabError:
			pass  # The key may already be revoked; disconnecting must still work.

	for field in (
		"ajab_url",
		"organization_id",
		"organization_name",
		"key_name",
		"key_scopes",
		"connected_at",
		"webhook_url",
		"last_webhook_at",
	):
		settings.set(field, None)
	settings.status = "Not connected"
	settings.webhook_status = "Not registered"
	settings.save()
	for field in ("api_key", "webhook_secret"):
		remove_encrypted_password(SETTINGS, SETTINGS, field)
	return {"status": settings.status}


# ---------------------------------------------------------------- jobs


def _job_payload(opening) -> dict:
	payload = {
		"title": opening.job_title,
		"description": strip_html_tags(cstr(opening.description)).strip() or opening.job_title,
		"isActive": opening.status == "Open",
	}
	return payload


def _push_job(opening) -> str:
	payload = _job_payload(opening)
	if opening.get("ajab_job_id"):
		try:
			request("PATCH", f"/jobs/{opening.ajab_job_id}", json=payload)
			opening.db_set("ajab_synced_at", now_datetime(), notify=True)
			return opening.ajab_job_id
		except AjabError as e:
			if e.status_code != 404:
				frappe.throw(e.message, title=_("Ajab"))
			# Deleted in Ajab: create it again below.
	data = call("POST", "/jobs", json=payload).get("data") or {}
	opening.db_set({"ajab_job_id": data.get("_id"), "ajab_synced_at": now_datetime()}, notify=True)
	return opening.ajab_job_id


@frappe.whitelist(methods=["POST"])
def send_job_opening(job_opening: str) -> dict:
	opening = frappe.get_doc("Job Opening", job_opening)
	opening.check_permission("write")
	job_id = _push_job(opening)
	return {"ajab_job_id": job_id}


# ---------------------------------------------------------------- applicants


def _find_or_create_candidate(applicant) -> str:
	if applicant.get("ajab_candidate_id"):
		return applicant.ajab_candidate_id
	email = cstr(applicant.email_id).strip().lower()
	found = call("GET", "/candidates", params={"email": email, "limit": 5}).get("docs") or []
	match = next((c for c in found if cstr(c.get("email")).lower() == email), None)
	if match:
		return match["_id"]
	data = (
		call("POST", "/candidates", json={"name": applicant.applicant_name, "email": email}).get("data") or {}
	)
	return data.get("_id")


@frappe.whitelist(methods=["POST"])
def schedule_interview(job_applicant: str) -> dict:
	"""Create the Ajab candidate and AI interview for this applicant."""
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	applicant.check_permission("write")
	if not applicant.job_title:
		frappe.throw(_("Set the Job Opening on this applicant first"))
	if not applicant.email_id:
		frappe.throw(_("The applicant needs an email address"))
	if applicant.get("ajab_interview_id") and applicant.get("ajab_interview_status") in OPEN_INTERVIEW_STATES:
		frappe.throw(
			_(
				"This applicant already has an AI interview ({0}). Cancel it first to schedule a new one."
			).format(applicant.ajab_interview_status)
		)

	opening = frappe.get_doc("Job Opening", applicant.job_title)
	job_id = opening.get("ajab_job_id") or _push_job(opening)
	candidate_id = _find_or_create_candidate(applicant)
	send_email = bool(frappe.db.get_single_value(SETTINGS, "send_interview_email"))
	data = (
		call(
			"POST",
			"/interviews",
			json={"candidateId": candidate_id, "jobId": job_id, "sendEmail": send_email},
		).get("data")
		or {}
	)

	applicant.db_set(
		{
			"ajab_candidate_id": candidate_id,
			"ajab_interview_id": data.get("_id"),
			"ajab_interview_status": data.get("status") or "created",
			"ajab_analysis_status": None,
			"ajab_final_score": 0,
			"ajab_interview_score": 0,
			"ajab_resume_score": 0,
			"ajab_rating": None,
			"ajab_summary": None,
			"ajab_last_update": now_datetime(),
		},
		notify=True,
	)
	applicant.add_comment(
		"Info",
		_("AI interview scheduled in Ajab{0}.").format(
			_(", invite emailed to {0}").format(applicant.email_id) if send_email else ""
		),
	)
	return {"ajab_interview_id": applicant.ajab_interview_id, "email_sent": send_email}


@frappe.whitelist(methods=["POST"])
def cancel_interview(job_applicant: str) -> dict:
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	applicant.check_permission("write")
	if not applicant.get("ajab_interview_id"):
		frappe.throw(_("This applicant has no AI interview"))
	call("POST", f"/interviews/{applicant.ajab_interview_id}/cancel")
	applicant.db_set({"ajab_interview_status": "cancelled", "ajab_last_update": now_datetime()}, notify=True)
	applicant.add_comment("Info", _("AI interview cancelled in Ajab."))
	return {"status": "cancelled"}


def _apply_results(applicant, results: dict) -> None:
	scores = results.get("scores") or {}
	analysis = results.get("aiAnalysis") or {}
	summary = analysis.get("summary") if isinstance(analysis, dict) else None
	if isinstance(summary, dict):
		summary = summary.get("detailed") or summary.get("brief")
	rating = analysis.get("overallRating") if isinstance(analysis, dict) else None
	applicant.db_set(
		{
			"ajab_interview_status": results.get("status"),
			"ajab_analysis_status": results.get("analysisStatus"),
			"ajab_final_score": scores.get("final") or 0,
			"ajab_interview_score": scores.get("interview") or 0,
			"ajab_resume_score": scores.get("resume") or 0,
			"ajab_rating": cstr(rating).replace("_", " ") or None,
			"ajab_summary": cstr(summary) or None,
			"ajab_last_update": now_datetime(),
		},
		notify=True,
	)


def _refresh(applicant) -> dict:
	interview = call("GET", f"/interviews/{applicant.ajab_interview_id}").get("data") or {}
	status = interview.get("status")
	analysis_status = interview.get("analysisStatus")
	settings = frappe.get_single(SETTINGS)
	if status == "completed" and analysis_status == "completed" and _has_scope(settings, "results:read"):
		was_scored = applicant.get("ajab_analysis_status") == "completed"
		_apply_results(
			applicant, call("GET", f"/interviews/{applicant.ajab_interview_id}/results").get("data") or {}
		)
		if not was_scored:
			applicant.add_comment(
				"Info", _("AI interview scored in Ajab: final score {0}.").format(applicant.ajab_final_score)
			)
	else:
		applicant.db_set(
			{
				"ajab_interview_status": status,
				"ajab_analysis_status": analysis_status,
				"ajab_last_update": now_datetime(),
			},
			notify=True,
		)
	return {
		"status": status,
		"analysis_status": analysis_status,
		"final_score": applicant.get("ajab_final_score"),
	}


@frappe.whitelist(methods=["POST"])
def refresh_interview(job_applicant: str) -> dict:
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	applicant.check_permission("write")
	if not applicant.get("ajab_interview_id"):
		frappe.throw(_("This applicant has no AI interview"))
	return _refresh(applicant)


# ---------------------------------------------------------------- webhook


def verify_signature(secret: str, body: str, header: str, now: float | None = None) -> bool:
	"""x-ajab-signature: t=<unix>,v1=<hex HMAC-SHA256(secret, "t.body")>, at most 5 minutes old."""
	parts = dict(p.split("=", 1) for p in cstr(header).split(",") if "=" in p)
	t, v1 = parts.get("t", ""), parts.get("v1", "")
	if not t.isdigit() or not v1:
		return False
	if abs((now or time.time()) - int(t)) > SIGNATURE_TOLERANCE_SECONDS:
		return False
	expected = hmac.new(secret.encode(), f"{t}.{body}".encode(), hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, v1)


def _reject(status: int, message: str) -> dict:
	frappe.local.response.http_status_code = status
	return {"ok": False, "message": message}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=60)
def webhook() -> dict:
	"""Signed interview updates from Ajab. Payloads carry ids and status only."""
	settings = frappe.get_single(SETTINGS)
	secret = (
		settings.get_password("webhook_secret", raise_exception=False)
		if settings.status == "Connected"
		else None
	)
	body = frappe.request.get_data(as_text=True)
	if not secret or not verify_signature(secret, body, frappe.get_request_header("X-Ajab-Signature")):
		return _reject(401, "invalid signature")

	try:
		event = json.loads(body)
	except ValueError:
		return _reject(400, "invalid body")
	if event.get("organizationId") != settings.organization_id:
		return _reject(403, "wrong organisation")

	# Deliveries can repeat; handle each event id once.
	seen_key = f"ajab_webhook_event:{event.get('id')}"
	if frappe.cache.get_value(seen_key):
		return {"ok": True, "duplicate": True}
	frappe.cache.set_value(seen_key, 1, expires_in_sec=7 * 24 * 3600)

	frappe.db.set_single_value(SETTINGS, "last_webhook_at", now_datetime(), update_modified=False)
	# Record changes as Administrator rather than Guest, as the PCP integration does.
	frappe.set_user("Administrator")
	try:
		handled = _handle_event(event)
	finally:
		frappe.set_user("Guest")
	return {"ok": True, "handled": handled}


def _handle_event(event: dict) -> bool:
	data = event.get("data") or {}
	interview_id = data.get("interviewId")
	etype = event.get("type")
	if not interview_id or etype not in WEBHOOK_EVENTS:
		return False
	name = frappe.db.get_value("Job Applicant", {"ajab_interview_id": interview_id})
	if not name:
		return False

	if etype == "interview.analysis.completed":
		frappe.enqueue(
			"hrms.ajab_integration.api.refresh_applicant_job",
			queue="short",
			job_applicant=name,
			enqueue_after_commit=True,
		)
		return True

	applicant = frappe.get_doc("Job Applicant", name)
	status = EVENT_STATUS.get(etype) or data.get("status")
	applicant.db_set({"ajab_interview_status": status, "ajab_last_update": now_datetime()}, notify=True)
	if etype in ("interview.started", "interview.completed", "interview.cancelled"):
		label = {
			"interview.started": _("started"),
			"interview.completed": _("finished"),
			"interview.cancelled": _("cancelled"),
		}[etype]
		applicant.add_comment("Info", _("Ajab: the AI interview {0}.").format(label))
	return True


def refresh_applicant_job(job_applicant: str) -> None:
	"""Background job: read the results after Ajab finishes scoring."""
	applicant = frappe.get_doc("Job Applicant", job_applicant)
	try:
		_refresh(applicant)
	except frappe.ValidationError:
		frappe.log_error(
			title="Ajab: could not read interview results",
			reference_doctype="Job Applicant",
			reference_name=job_applicant,
		)


# ---------------------------------------------------------------- employees


def _employee_payload(employee, role: str) -> dict:
	email = employee.company_email or employee.user_id or employee.personal_email
	if not email:
		frappe.throw(_("Employee {0} has no email address").format(employee.name))
	payload = {
		"empId": employee.name,
		"name": employee.employee_name,
		"email": email,
		"role": role or "recruiter",
		"status": "active" if employee.status == "Active" else "inactive",
	}
	if employee.designation:
		payload["designation"] = employee.designation
	if employee.date_of_joining:
		payload["startDate"] = getdate(employee.date_of_joining).isoformat()
	return payload


def _sync_employee(employee, role: str) -> str:
	data = call("POST", "/employee-sync", json=_employee_payload(employee, role)).get("data") or {}
	employee.db_set({"ajab_member_id": data.get("memberId"), "ajab_synced_at": now_datetime()}, notify=True)
	return employee.ajab_member_id


@frappe.whitelist(methods=["POST"])
def sync_employee(employee: str) -> dict:
	doc = frappe.get_doc("Employee", employee)
	doc.check_permission("write")
	frappe.only_for(MANAGERS)
	role = frappe.db.get_single_value(SETTINGS, "default_member_role")
	return {"ajab_member_id": _sync_employee(doc, role)}


@frappe.whitelist(methods=["POST"])
def sync_all_employees() -> dict:
	"""Queue a sync of every active employee that has an email."""
	frappe.only_for(MANAGERS)
	if frappe.db.get_single_value(SETTINGS, "status") != "Connected":
		frappe.throw(_("Connect to Ajab first"))
	names = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
	frappe.enqueue(
		"hrms.ajab_integration.api.sync_all_employees_job",
		queue="long",
		employees=names,
		user=frappe.session.user,
		enqueue_after_commit=True,
	)
	return {"queued": len(names)}


def sync_all_employees_job(employees: list, user: str) -> None:
	role = frappe.db.get_single_value(SETTINGS, "default_member_role")
	synced, failed = 0, []
	for name in employees:
		try:
			_sync_employee(frappe.get_doc("Employee", name), role)
			synced += 1
		except frappe.ValidationError as e:
			failed.append(f"{name}: {strip_html_tags(cstr(e))}")
		frappe.db.commit()
	message = _("Ajab employee sync finished: {0} synced, {1} failed.").format(synced, len(failed))
	if failed:
		message += "<br>" + "<br>".join(frappe.utils.escape_html(f) for f in failed[:20])
	frappe.publish_realtime("msgprint", {"message": message, "title": _("Ajab")}, user=user)
