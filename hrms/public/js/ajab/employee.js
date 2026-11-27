// Copyright (c) 2026, Pioneer AI Tech and contributors
// License: GNU General Public License v3. See license.txt

// Ajab: create or update this employee as an Ajab team member.
frappe.ui.form.on("Employee", {
	async refresh(frm) {
		if (frm.is_new() || !frappe.user.has_role(["HR Manager", "System Manager"])) return;
		if (!(await hrms_ajab_connected())) return;
		frm.add_custom_button(
			frm.doc.ajab_member_id ? __("Update in Ajab") : __("Sync to Ajab"),
			() =>
				frappe.call({
					method: "hrms.ajab_integration.api.sync_employee",
					args: { employee: frm.doc.name },
					freeze: true,
					freeze_message: __("Sending to Ajab…"),
					callback: (r) => {
						if (r.exc) return;
						frappe.show_alert({
							message: __("Employee synced to Ajab"),
							indicator: "green",
						});
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
