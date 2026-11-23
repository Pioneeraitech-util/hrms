# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt
"""
Frappe HR side of "Connect to PCP" (Pioneer Core Platform).

1. An admin clicks Connect to PCP in PCP Integration Settings. We make (or
   reuse) a dedicated integration user with the HR User role only, and a
   one-time code FHR-XXXX-XXXX-XXXX. Only its SHA-256 is stored; it expires
   after 15 minutes. The admin is sent to PCP company settings with the code
   and this site's address filled in.
2. PCP's server redeems the code here (redeem_connection_code). We check it,
   burn it, issue a fresh API secret for the integration user and record
   which PCP company linked. PCP stores the key encrypted and its workflows
   call this site's REST API with it.
3. Disconnecting (from PCP, or here) revokes the integration user's key.
"""

import hashlib
import hmac
import secrets
from urllib.parse import urlencode

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import add_to_date, get_datetime, get_url, now_datetime

SETTINGS = "PCP Integration Settings"
INTEGRATION_USER = "pcp-integration@pcp.invalid"
INTEGRATION_ROLE = "HR User"
CODE_MINUTES = 15
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I


def _hash(code: str) -> str:
	return hashlib.sha256(code.encode()).hexdigest()


def _new_code() -> str:
	groups = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(3)]
	return "FHR-" + "-".join(groups)


def _ensure_integration_user() -> str:
	"""The user PCP signs in as: a System User with the HR User role and nothing else."""
	if not frappe.db.exists("User", INTEGRATION_USER):
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": INTEGRATION_USER,
				"first_name": "PCP",
				"last_name": "Integration",
				"user_type": "System User",
				"send_welcome_email": 0,
				"enabled": 1,
			}
		)
		user.flags.ignore_permissions = True
		user.flags.no_welcome_mail = True
		user.insert()
	user = frappe.get_doc("User", INTEGRATION_USER)
	user.enabled = 1
	roles = {r.role for r in user.roles}
	if roles != {INTEGRATION_ROLE}:
		user.set("roles", [])
		user.append("roles", {"role": INTEGRATION_ROLE})
	user.flags.ignore_permissions = True
	user.save()
	return INTEGRATION_USER


def _revoke_key():
	if frappe.db.exists("User", INTEGRATION_USER):
		user = frappe.get_doc("User", INTEGRATION_USER)
		user.api_key = None
		user.api_secret = None
		user.flags.ignore_permissions = True
		user.save()


def _mark_disconnected():
	settings = frappe.get_single(SETTINGS)
	settings.status = "Not connected"
	settings.code_hash = None
	settings.code_expires = None
	settings.linked_company = None
	settings.linked_company_id = None
	settings.linked_pcp_url = None
	settings.linked_at = None
	settings.flags.ignore_permissions = True
	settings.save()


@frappe.whitelist(methods=["POST"])
def create_connection_code(pcp_url: str | None = None) -> dict:
	"""Desk: make the integration user and a one-time code, and the PCP link that carries it."""
	frappe.only_for(("System Manager", "HR Manager"))
	settings = frappe.get_single(SETTINGS)
	if pcp_url:
		settings.pcp_url = pcp_url
	user = _ensure_integration_user()
	code = _new_code()
	settings.code_hash = _hash(code)
	settings.code_expires = add_to_date(now_datetime(), minutes=CODE_MINUTES)
	settings.integration_user = user
	if settings.status != "Connected":
		settings.status = "Waiting for PCP"
	settings.flags.ignore_permissions = True
	settings.save()  # validate() cleans pcp_url to https://host

	site_url = get_url().rstrip("/")
	query = urlencode({"frappe_code": code, "frappe_site": site_url})
	return {
		"code": code,
		"site_url": site_url,
		"expires_in_minutes": CODE_MINUTES,
		"launch_url": f"{settings.pcp_url}/company-settings/settings/integration?{query}",
	}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60 * 60)
def redeem_connection_code(
	code: str, pcp_company_id: str, pcp_company_name: str | None = None, pcp_url: str | None = None
) -> dict:
	"""PCP's server: trade a valid code for the integration user's API key and secret. Works once."""
	settings = frappe.get_single(SETTINGS)
	clean = (code or "").strip().upper()
	valid = bool(
		settings.code_hash
		and settings.code_expires
		and get_datetime(settings.code_expires) > now_datetime()
		and hmac.compare_digest(settings.code_hash, _hash(clean))
	)
	if not valid:
		frappe.throw(
			_("This connection code is not valid or has expired. Make a new one in Frappe HR."),
			frappe.AuthenticationError,
		)
	if not (pcp_company_id or "").strip():
		frappe.throw(_("PCP did not say which company is connecting."))

	current = frappe.session.user
	frappe.set_user("Administrator")
	try:
		user_name = _ensure_integration_user()
		user = frappe.get_doc("User", user_name)
		api_key = user.api_key or frappe.generate_hash(length=15)
		api_secret = frappe.generate_hash(length=15)
		user.api_key = api_key
		user.api_secret = api_secret
		user.flags.ignore_permissions = True
		user.save()

		settings.reload()
		settings.code_hash = None
		settings.code_expires = None
		settings.status = "Connected"
		settings.integration_user = user_name
		settings.linked_company = (pcp_company_name or "").strip()[:140] or pcp_company_id.strip()[:140]
		settings.linked_company_id = pcp_company_id.strip()[:140]
		settings.linked_pcp_url = (pcp_url or "").strip()[:200]
		settings.linked_at = now_datetime()
		settings.flags.ignore_permissions = True
		settings.save()
		frappe.db.commit()
	finally:
		frappe.set_user(current)

	return {"api_key": api_key, "api_secret": api_secret, "user": user_name, "site_url": get_url().rstrip("/")}


@frappe.whitelist(methods=["POST"])
def disconnect() -> dict:
	"""PCP's server, signed in as the integration user: revoke its own key."""
	if frappe.session.user != INTEGRATION_USER:
		frappe.throw(_("Only the PCP integration user can do this."), frappe.PermissionError)
	frappe.set_user("Administrator")
	_revoke_key()
	_mark_disconnected()
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def disconnect_from_desk() -> dict:
	"""Desk: revoke PCP's key. PCP shows the connection as failing until it is linked again."""
	frappe.only_for(("System Manager", "HR Manager"))
	_revoke_key()
	_mark_disconnected()
	return {"ok": True}
