// Copyright (c) 2026, Pioneer AI Tech and contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("PCP Integration Settings", {
	refresh(frm) {
		const connected = frm.doc.status === "Connected";
		frm.disable_save();
		frm.add_custom_button(connected ? __("Connect again") : __("Connect to PCP"), () =>
			connect(frm),
		).addClass(connected ? "" : "btn-primary");
		if (connected || frm.doc.status === "Waiting for PCP") {
			frm.add_custom_button(__("Disconnect"), () =>
				frappe.confirm(
					__("PCP workflows will stop reaching this site until you connect again. Disconnect?"),
					() =>
						frappe
							.call("hrms.pioneer_integration.api.disconnect_from_desk")
							.then(() => frm.reload_doc()),
				),
			);
		}
		if (connected) {
			frm.set_intro(
				__("Connected to {0}. PCP workflows sign in here as {1}.", [
					frappe.utils.escape_html(frm.doc.linked_company || __("PCP")),
					frappe.utils.escape_html(frm.doc.integration_user || ""),
				]),
				"green",
			);
		}
	},
});

function connect(frm) {
	const go = () =>
		frappe
			.call({
				method: "hrms.pioneer_integration.api.create_connection_code",
				args: { pcp_url: frm.doc.pcp_url },
				freeze: true,
			})
			.then(({ message }) => {
				frm.reload_doc();
				const d = new frappe.ui.Dialog({
					title: __("Connect to PCP"),
					fields: [
						{
							fieldtype: "HTML",
							options: `<p>${__("Open PCP to finish. The code is filled in for you. If PCP asks for it, enter:")}</p>
								<p style="font-family: var(--font-mono, monospace); font-size: 1.4em; letter-spacing: .08em; text-align: center;">${frappe.utils.escape_html(message.code)}</p>
								<p class="text-muted small">${__("Site address: {0}. The code works once and expires in 15 minutes.", [frappe.utils.escape_html(message.site_url)])}</p>`,
						},
					],
					primary_action_label: __("Open PCP"),
					primary_action() {
						window.open(message.launch_url, "_blank", "noopener");
						d.hide();
					},
				});
				d.show();
			});
	if (frm.is_dirty()) frm.save().then(go);
	else go();
}
