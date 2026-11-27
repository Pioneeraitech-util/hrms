# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt

"""Small HTTP client for the Ajab public API (/api/v1).

Every call sends the organisation's scoped key in x-api-key. Errors come back
as AjabError with a message that is safe to show to HR users.
"""

from urllib.parse import urlparse

import requests

import frappe
from frappe import _

SETTINGS = "Ajab Integration Settings"
TIMEOUT_SECONDS = 20
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class AjabError(Exception):
	def __init__(self, message: str, status_code: int | None = None, code: str | None = None):
		super().__init__(message)
		self.message = message
		self.status_code = status_code
		self.code = code


def normalize_url(url: str) -> str:
	"""Return scheme://host[:port]. https is required except for a local Ajab."""
	parsed = urlparse((url or "").strip())
	if parsed.scheme not in ("http", "https") or not parsed.netloc:
		frappe.throw(_("Enter the Ajab API address with https://, for example https://api.ajab.ai"))
	if parsed.scheme == "http" and parsed.hostname not in LOCAL_HOSTS and not frappe.conf.developer_mode:
		frappe.throw(_("The Ajab API address must use https://"))
	return f"{parsed.scheme}://{parsed.netloc}"


def _friendly(status: int, body: dict) -> str:
	detail = body.get("message") or body.get("error") or ""
	if status == 401:
		return _("Ajab rejected the API key. It may be wrong, revoked or expired.")
	if status == 403:
		return _("The Ajab API key is not allowed to do this. {0}").format(detail).strip()
	if status == 404:
		return _("Ajab could not find this record. It may have been deleted in Ajab.")
	if status == 429:
		return _("Ajab's daily request limit for this key was reached. Try again tomorrow.")
	return _("Ajab returned an error ({0}). {1}").format(status, detail).strip()


def request(
	method: str,
	path: str,
	json: dict | None = None,
	params: dict | None = None,
	url: str | None = None,
	api_key: str | None = None,
) -> dict:
	"""Call Ajab and return the parsed JSON body. Uses the saved connection by default."""
	if url is None or api_key is None:
		settings = frappe.get_single(SETTINGS)
		if settings.status != "Connected" or not settings.ajab_url:
			raise AjabError(_("Ajab is not connected. Open Ajab Integration Settings and connect first."))
		url = url or settings.ajab_url
		api_key = api_key or settings.get_password("api_key")

	try:
		response = requests.request(
			method,
			f"{url}/api/v1{path}",
			json=json,
			params=params,
			headers={"x-api-key": api_key, "accept": "application/json"},
			timeout=TIMEOUT_SECONDS,
			allow_redirects=False,
		)
	except requests.RequestException:
		raise AjabError(_("Could not reach Ajab at {0}. Check the address and try again.").format(url))

	try:
		body = response.json()
	except ValueError:
		body = {}
	if response.status_code >= 400 or body.get("success") is False:
		raise AjabError(_friendly(response.status_code, body), response.status_code, body.get("error"))
	return body


def call(method: str, path: str, **kwargs) -> dict:
	"""request() that turns AjabError into a frappe.throw for whitelisted methods."""
	try:
		return request(method, path, **kwargs)
	except AjabError as e:
		frappe.throw(e.message, title=_("Ajab"))
