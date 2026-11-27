// Copyright (c) 2026, Pioneer AI Tech and contributors
// License: GNU General Public License v3. See license.txt

// Ajab: send this job opening to Ajab so applicants can get AI interviews.
frappe.ui.form.on("Job Opening", {
	async refresh(frm) {
		if (frm.is_new() || !(await hrms_ajab_connected())) return;
		frm.add_custom_button(
			frm.doc.ajab_job_id ? __("Update in Ajab") : __("Send to Ajab"),
			() =>
				frappe.call({
					method: "hrms.ajab_integration.api.send_job_opening",
					args: { job_opening: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending to Ajab…"),
					callback: (r) => {
						if (r.exc) return;
						frappe.show_alert({ message: __("Job is in Ajab"), indicator: "green" });
						frm.reload_doc();
					},
				}),
			__("Ajab"),
		);
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
