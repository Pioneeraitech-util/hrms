// Copyright (c) 2026, Pioneer AI Tech and contributors
// License: GNU General Public License v3. See license.txt

// Ajab: schedule an AI interview for this applicant and follow its result.
const AJAB_OPEN_STATES = ["created", "recording", "completed"];

frappe.ui.form.on("Job Applicant", {
	async refresh(frm) {
		if (frm.is_new() || !(await hrms_ajab_connected())) return;
		const group = __("Ajab");
		const status = frm.doc.ajab_interview_status;
		const call = (method, message, args = {}) =>
			frappe.call({
				method: `hrms.ajab_integration.api.${method}`,
				args: { job_applicant: frm.doc.name, ...args },
				freeze: true,
				freeze_message: __("Talking to Ajab…"),
				callback: (r) => {
					if (r.exc) return;
					frappe.show_alert({ message, indicator: "green" });
					frm.reload_doc();
				},
			});

		if (!frm.doc.ajab_interview_id || !AJAB_OPEN_STATES.includes(status)) {
			frm.add_custom_button(
				__("Schedule AI interview"),
				() =>
					frappe.confirm(
						__("Create an AI interview in Ajab for {0} ({1})?", [
							frappe.utils.escape_html(frm.doc.applicant_name),
							frappe.utils.escape_html(frm.doc.email_id || ""),
						]),
						() => call("schedule_interview", __("AI interview scheduled")),
					),
				group,
			);
		}
		if (frm.doc.ajab_interview_id) {
			frm.add_custom_button(
				__("Refresh from Ajab"),
				() => call("refresh_interview", __("Updated from Ajab")),
				group,
			);
			if (status === "created") {
				frm.add_custom_button(
					__("Cancel AI interview"),
					() =>
						frappe.confirm(__("Cancel the AI interview in Ajab?"), () =>
							call("cancel_interview", __("AI interview cancelled")),
						),
					group,
				);
			}
		}
		if (
			frm.doc.ajab_final_score !== null &&
			frm.doc.ajab_final_score !== undefined &&
			frm.doc.ajab_analysis_status === "completed"
		) {
			frm.dashboard.add_comment(
				__("AI interview score: {0}{1}", [
					frm.doc.ajab_final_score,
					frm.doc.ajab_rating
						? " · " +
						  __("recommendation: {0}", [
								frappe.utils.escape_html(frm.doc.ajab_rating),
						  ])
						: "",
				]),
				"blue",
				true,
			);
		} else if (status) {
			frm.dashboard.add_comment(
				__("AI interview: {0}", [frappe.utils.escape_html(status)]),
				"blue",
				true,
			);
		}
	},
});

window.hrms_ajab_connected =
	window.hrms_ajab_connected ||
	(async () => {
		const now = Date.now();
		const cache = window.__hrms_ajab_status;
		if (cache && now - cache.at < 60000) return cache.value;
		const r = await frappe.call({
			method: "hrms.ajab_integration.api.is_connected",
			type: "GET",
		});
		window.__hrms_ajab_status = { at: now, value: !!r.message };
		return !!r.message;
	});
