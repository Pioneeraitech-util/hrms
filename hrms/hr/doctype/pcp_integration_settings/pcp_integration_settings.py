# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt

from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document


class PCPIntegrationSettings(Document):
	def validate(self):
		url = (self.pcp_url or "").strip().rstrip("/")
		parsed = urlparse(url)
		if parsed.scheme != "https" or not parsed.netloc:
			frappe.throw(_("Enter the PCP address with https://, for example https://core.pioneeraitech.com"))
		self.pcp_url = f"{parsed.scheme}://{parsed.netloc}"
