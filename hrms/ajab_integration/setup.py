# Copyright (c) 2026, Pioneer AI Tech and contributors
# License: GNU General Public License v3. See license.txt

"""Custom fields that hold the Ajab ids and AI interview results on HR records.

Created on every migrate (idempotent), so the recruitment doctypes' own JSON
stays as upstream ships it.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def _ro(fieldname: str, label: str, fieldtype: str = "Data", **extra) -> dict:
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": fieldtype,
		"read_only": 1,
		"no_copy": 1,
		**extra,
	}


SCORED = "eval:doc.ajab_analysis_status=='completed'"


def get_custom_fields() -> dict:
	return {
		"Job Opening": [
			{
				"fieldname": "ajab_tab",
				"label": "AI Interview",
				"fieldtype": "Tab Break",
				"insert_after": "publish_salary_range",
			},
			_ro("ajab_job_id", "Ajab job ID", insert_after="ajab_tab"),
			_ro("ajab_synced_at", "Sent to Ajab on", "Datetime", insert_after="ajab_job_id"),
		],
		"Job Applicant": [
			{
				"fieldname": "ajab_tab",
				"label": "AI Interview",
				"fieldtype": "Tab Break",
				"insert_after": "upper_range",
			},
			_ro("ajab_interview_status", "Interview status", insert_after="ajab_tab", in_standard_filter=1),
			_ro("ajab_analysis_status", "Analysis status", insert_after="ajab_interview_status"),
			_ro("ajab_rating", "AI recommendation", insert_after="ajab_analysis_status", depends_on=SCORED),
			_ro("ajab_last_update", "Last update from Ajab", "Datetime", insert_after="ajab_rating"),
			{"fieldname": "ajab_column_1", "fieldtype": "Column Break", "insert_after": "ajab_last_update"},
			_ro(
				"ajab_final_score",
				"Final score",
				"Float",
				insert_after="ajab_column_1",
				precision="1",
				depends_on=SCORED,
			),
			_ro(
				"ajab_interview_score",
				"Interview score",
				"Float",
				insert_after="ajab_final_score",
				precision="1",
				depends_on=SCORED,
			),
			_ro(
				"ajab_resume_score",
				"Resume score",
				"Float",
				insert_after="ajab_interview_score",
				precision="1",
				depends_on=SCORED,
			),
			{
				"fieldname": "ajab_summary_section",
				"label": "AI summary",
				"fieldtype": "Section Break",
				"insert_after": "ajab_resume_score",
				"depends_on": SCORED,
			},
			_ro("ajab_summary", "Summary", "Small Text", insert_after="ajab_summary_section"),
			{
				"fieldname": "ajab_ids_section",
				"label": "Ajab references",
				"fieldtype": "Section Break",
				"insert_after": "ajab_summary",
				"collapsible": 1,
			},
			_ro("ajab_candidate_id", "Ajab candidate ID", insert_after="ajab_ids_section"),
			_ro("ajab_interview_id", "Ajab interview ID", insert_after="ajab_candidate_id", search_index=1),
		],
		"Employee": [
			_ro("ajab_member_id", "Ajab member ID", insert_after="user_id"),
			_ro("ajab_synced_at", "Synced to Ajab on", "Datetime", insert_after="ajab_member_id"),
		],
	}


def create_ajab_custom_fields() -> None:
	create_custom_fields(get_custom_fields(), ignore_validate=True, update=True)
