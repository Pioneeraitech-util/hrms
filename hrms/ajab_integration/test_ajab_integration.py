# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import frappe
from frappe.tests import IntegrationTestCase

from hrms.ajab_integration import api
from hrms.ajab_integration.client import SETTINGS, normalize_url
from hrms.ajab_integration.setup import create_ajab_custom_fields

ORG = "org_test_1"
SECRET = "whsec_unit_test_secret"


def _response(status: int, body: dict) -> MagicMock:
	res = MagicMock()
	res.status_code = status
	res.json.return_value = body
	return res


class FakeAjab:
	"""Routes requests.request(method, url, ...) to canned Ajab responses and records calls."""

	def __init__(self, routes: dict):
		self.routes = routes
		self.calls = []

	def __call__(self, method, url, json=None, params=None, headers=None, **kwargs):
		path = url.split("/api/v1", 1)[1]
		self.calls.append((method, path, json, params, headers))
		status, body = self.routes[(method, path)]
		return _response(status, body)


def _sign(body: str, t: int | None = None, secret: str = SECRET) -> str:
	t = t or int(time.time())
	return f"t={t},v1={hmac.new(secret.encode(), f'{t}.{body}'.encode(), hashlib.sha256).hexdigest()}"


class TestAjabIntegration(IntegrationTestCase):
	def setUp(self):
		create_ajab_custom_fields()
		settings = frappe.get_single(SETTINGS)
		settings.update(
			{
				"ajab_url": "https://ajab.example.com",
				"api_key": "ajab_unit_test_key",
				"status": "Connected",
				"organization_id": ORG,
				"organization_name": "Unit Org",
				"key_scopes": "jobs:read, jobs:write, candidates:read, candidates:write, interviews:read, "
				"interviews:write, results:read, webhooks:manage, members:sync",
				"webhook_secret": SECRET,
				"webhook_status": "Registered",
				"send_interview_email": 1,
			}
		)
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.cache.delete_keys("ajab_webhook_event:")

	# ------------------------------------------------------------ helpers

	def test_signature_verification(self):
		body = '{"a":1}'
		self.assertTrue(api.verify_signature(SECRET, body, _sign(body)))
		self.assertFalse(api.verify_signature(SECRET, body + " ", _sign(body)))
		self.assertFalse(api.verify_signature("whsec_other", body, _sign(body)))
		self.assertFalse(api.verify_signature(SECRET, body, _sign(body, t=int(time.time()) - 3600)))
		self.assertFalse(api.verify_signature(SECRET, body, "garbage"))
		self.assertFalse(api.verify_signature(SECRET, body, ""))

	def test_url_normalisation(self):
		self.assertEqual(normalize_url("https://api.ajab.ai/api/v1/"), "https://api.ajab.ai")
		self.assertEqual(normalize_url("http://localhost:8140"), "http://localhost:8140")
		with patch.dict(frappe.conf, {"developer_mode": 0}):
			self.assertRaises(frappe.ValidationError, normalize_url, "http://api.ajab.ai")
		self.assertRaises(frappe.ValidationError, normalize_url, "api.ajab.ai")

	# ------------------------------------------------------------ connect

	def test_connect_saves_key_encrypted_and_registers_webhook(self):
		fake = FakeAjab(
			{
				("GET", "/me"): (
					200,
					{
						"success": True,
						"data": {
							"organization": {"id": "org_new", "name": "New Org"},
							"key": {"name": "HR", "scopes": ["jobs:read", "webhooks:manage"]},
						},
					},
				),
				("PATCH", "/webhooks/config"): (
					200,
					{"success": True, "data": {"secret": "whsec_abcd…wxyz"}},
				),
				("POST", "/webhooks/regenerate-secret"): (
					200,
					{"success": True, "data": {"secret": "whsec_fresh"}},
				),
			}
		)
		with patch("hrms.ajab_integration.client.requests.request", fake):
			result = api.connect("https://ajab.example.com/", "ajab_new_key")

		self.assertTrue(result["webhook"]["registered"])
		settings = frappe.get_single(SETTINGS)
		self.assertEqual(settings.organization_name, "New Org")
		self.assertEqual(settings.get_password("api_key"), "ajab_new_key")
		self.assertNotEqual(frappe.db.get_single_value(SETTINGS, "api_key"), "ajab_new_key")
		self.assertEqual(settings.get_password("webhook_secret"), "whsec_fresh")
		patch_call = next(c for c in fake.calls if c[0] == "PATCH")
		self.assertTrue(patch_call[2]["url"].endswith("/api/method/hrms.ajab_integration.api.webhook"))
		self.assertEqual(fake.calls[0][4]["x-api-key"], "ajab_new_key")

	def test_connect_with_bad_key_changes_nothing(self):
		fake = FakeAjab({("GET", "/me"): (401, {"success": False, "error": "INVALID_API_KEY"})})
		with patch("hrms.ajab_integration.client.requests.request", fake):
			self.assertRaises(frappe.ValidationError, api.connect, "https://ajab.example.com", "ajab_wrong")
		self.assertEqual(frappe.get_single(SETTINGS).get_password("api_key"), "ajab_unit_test_key")

	# ------------------------------------------------------------ jobs and applicants

	def _opening_and_applicant(self, email: str):
		opening = frappe.get_doc(
			{
				"doctype": "Job Opening",
				"job_title": f"Ajab Unit Job {frappe.generate_hash(length=6)}",
				"designation": frappe.get_all("Designation", limit=1, pluck="name")[0],
				"company": frappe.get_all("Company", limit=1, pluck="name")[0],
				"status": "Open",
				"description": "<p>Python <b>and</b> SQL</p>",
			}
		).insert(ignore_permissions=True)
		if frappe.db.exists("Job Applicant", email):
			frappe.delete_doc("Job Applicant", email, force=True)
		applicant = frappe.get_doc(
			{
				"doctype": "Job Applicant",
				"applicant_name": "Unit Applicant",
				"email_id": email,
				"job_title": opening.name,
				"status": "Open",
			}
		).insert(ignore_permissions=True)
		return opening, applicant

	def test_schedule_interview_creates_job_candidate_and_interview(self):
		opening, applicant = self._opening_and_applicant("ajab.unit.applicant@example.com")
		fake = FakeAjab(
			{
				("POST", "/jobs"): (201, {"success": True, "data": {"_id": "job1"}}),
				("GET", "/candidates"): (200, {"success": True, "docs": []}),
				("POST", "/candidates"): (201, {"success": True, "data": {"_id": "cand1"}}),
				("POST", "/interviews"): (
					201,
					{"success": True, "data": {"_id": "iv1", "status": "created"}},
				),
			}
		)
		with patch("hrms.ajab_integration.client.requests.request", fake):
			api.schedule_interview(applicant.name)
			# A second interview while one is open is refused before calling Ajab.
			self.assertRaises(frappe.ValidationError, api.schedule_interview, applicant.name)

		job_post = next(c for c in fake.calls if c[:2] == ("POST", "/jobs"))
		self.assertEqual(job_post[2]["description"], "Python and SQL")
		self.assertEqual(fake.calls[1][3], {"email": "ajab.unit.applicant@example.com", "limit": 5})
		self.assertEqual(fake.calls[-1][2], {"candidateId": "cand1", "jobId": "job1", "sendEmail": True})
		self.assertEqual(len([c for c in fake.calls if c[:2] == ("POST", "/interviews")]), 1)
		self.assertEqual(frappe.db.get_value("Job Opening", opening.name, "ajab_job_id"), "job1")
		row = frappe.db.get_value(
			"Job Applicant",
			applicant.name,
			["ajab_candidate_id", "ajab_interview_id", "ajab_interview_status"],
			as_dict=True,
		)
		self.assertEqual(
			(row.ajab_candidate_id, row.ajab_interview_id, row.ajab_interview_status),
			("cand1", "iv1", "created"),
		)

	def test_existing_candidate_is_reused(self):
		_opening, applicant = self._opening_and_applicant("ajab.unit.reuse@example.com")
		fake = FakeAjab(
			{
				("POST", "/jobs"): (201, {"success": True, "data": {"_id": "job2"}}),
				("GET", "/candidates"): (
					200,
					{"success": True, "docs": [{"_id": "cand_old", "email": "AJAB.unit.reuse@example.com"}]},
				),
				("POST", "/interviews"): (
					201,
					{"success": True, "data": {"_id": "iv2", "status": "created"}},
				),
			}
		)
		with patch("hrms.ajab_integration.client.requests.request", fake):
			api.schedule_interview(applicant.name)
		self.assertNotIn(("POST", "/candidates"), [c[:2] for c in fake.calls])
		self.assertEqual(
			frappe.db.get_value("Job Applicant", applicant.name, "ajab_candidate_id"), "cand_old"
		)

	def test_refresh_reads_results_when_scored(self):
		_opening, applicant = self._opening_and_applicant("ajab.unit.results@example.com")
		applicant.db_set({"ajab_interview_id": "iv3", "ajab_interview_status": "recording"})
		fake = FakeAjab(
			{
				("GET", "/interviews/iv3"): (
					200,
					{"success": True, "data": {"status": "completed", "analysisStatus": "completed"}},
				),
				("GET", "/interviews/iv3/results"): (
					200,
					{
						"success": True,
						"data": {
							"status": "completed",
							"analysisStatus": "completed",
							"scores": {"resume": 70, "interview": 80, "final": 76.5},
							"aiAnalysis": {
								"overallRating": "strong_yes",
								"summary": {"brief": "b", "detailed": "Detailed summary"},
							},
						},
					},
				),
			}
		)
		with patch("hrms.ajab_integration.client.requests.request", fake):
			api.refresh_interview(applicant.name)
		row = frappe.db.get_value(
			"Job Applicant",
			applicant.name,
			[
				"ajab_final_score",
				"ajab_interview_score",
				"ajab_resume_score",
				"ajab_rating",
				"ajab_summary",
				"ajab_analysis_status",
			],
			as_dict=True,
		)
		self.assertEqual(row.ajab_final_score, 76.5)
		self.assertEqual(row.ajab_rating, "strong yes")
		self.assertEqual(row.ajab_summary, "Detailed summary")
		self.assertEqual(row.ajab_analysis_status, "completed")

	# ------------------------------------------------------------ webhook

	def _post_webhook(self, event: dict, signature: str | None = None):
		body = json.dumps(event)
		env = EnvironBuilder(
			method="POST",
			data=body,
			content_type="application/json",
			headers={"X-Ajab-Signature": signature if signature is not None else _sign(body)},
		).get_environ()
		frappe.local.request = Request(env)
		frappe.local.response = frappe._dict()
		frappe.local.request_ip = "127.0.0.1"
		user = frappe.session.user
		try:
			result = api.webhook()
		finally:
			frappe.set_user(user)
		return result, frappe.local.response.get("http_status_code")

	def test_webhook_updates_applicant_and_rejects_bad_requests(self):
		_opening, applicant = self._opening_and_applicant("ajab.unit.hook@example.com")
		applicant.db_set({"ajab_interview_id": "iv4", "ajab_interview_status": "created"})
		event = {
			"id": "evt1",
			"type": "interview.started",
			"organizationId": ORG,
			"data": {"interviewId": "iv4", "status": "recording"},
		}

		result, status = self._post_webhook(event, signature="t=1,v1=00")
		self.assertEqual(status, 401)
		result, status = self._post_webhook({**event, "organizationId": "someone_else"})
		self.assertEqual(status, 403)
		self.assertEqual(
			frappe.db.get_value("Job Applicant", applicant.name, "ajab_interview_status"), "created"
		)

		result, status = self._post_webhook(event)
		self.assertTrue(result["handled"])
		self.assertEqual(
			frappe.db.get_value("Job Applicant", applicant.name, "ajab_interview_status"), "recording"
		)
		result, _status = self._post_webhook(event)
		self.assertTrue(result.get("duplicate"))

	def test_webhook_refused_when_disconnected(self):
		frappe.db.set_single_value(SETTINGS, "status", "Not connected")
		event = {
			"id": "evt2",
			"type": "interview.started",
			"organizationId": ORG,
			"data": {"interviewId": "x"},
		}
		_result, status = self._post_webhook(event)
		self.assertEqual(status, 401)

	# ------------------------------------------------------------ employees and disconnect

	def test_employee_payload(self):
		employee = frappe._dict(
			name="HR-EMP-X",
			employee_name="Rina R",
			company_email="rina@example.com",
			user_id=None,
			personal_email=None,
			status="Left",
			designation="Recruiter",
			date_of_joining="2025-01-15",
		)
		payload = api._employee_payload(employee, "recruiter")
		self.assertEqual(
			payload,
			{
				"empId": "HR-EMP-X",
				"name": "Rina R",
				"email": "rina@example.com",
				"role": "recruiter",
				"status": "inactive",
				"designation": "Recruiter",
				"startDate": "2025-01-15",
			},
		)
		self.assertRaises(
			frappe.ValidationError,
			api._employee_payload,
			frappe._dict(employee, company_email=None),
			"recruiter",
		)

	def test_disconnect_removes_key_and_our_webhook(self):
		frappe.db.set_single_value(SETTINGS, "webhook_url", "https://hr.example.com/hook")
		fake = FakeAjab(
			{
				("GET", "/webhooks/config"): (
					200,
					{"success": True, "data": {"url": "https://hr.example.com/hook"}},
				),
				("DELETE", "/webhooks/config"): (200, {"success": True, "data": {"deleted": True}}),
			}
		)
		with patch("hrms.ajab_integration.client.requests.request", fake):
			api.disconnect()
		self.assertIn(("DELETE", "/webhooks/config"), [c[:2] for c in fake.calls])
		settings = frappe.get_single(SETTINGS)
		self.assertEqual(settings.status, "Not connected")
		self.assertIsNone(settings.get_password("api_key", raise_exception=False))
		self.assertIsNone(settings.get_password("webhook_secret", raise_exception=False))
