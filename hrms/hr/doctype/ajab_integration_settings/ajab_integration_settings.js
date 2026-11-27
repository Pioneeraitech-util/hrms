// Copyright (c) 2026, Pioneer AI Tech and contributors
// License: GNU General Public License v3. See license.txt

const AJAB_API = "hrms.ajab_integration.api";

frappe.ui.form.on("Ajab Integration Settings", {
	refresh(frm) {
		const connected = frm.doc.status === "Connected";
		frm.add_custom_button(connected ? __("Connect again") : __("Connect to Ajab"), () =>
			hrms_ajab.show_connect_dialog(frm),
		);
		if (!connected) {
			frm.set_intro(
				__("Not connected. Click Connect to Ajab and paste an Ajab API key."),
				"orange",
			);
			return;
		}

		const webhookOk = frm.doc.webhook_status === "Registered";
		frm.set_intro(
			webhookOk
				? __(
						"Connected to Ajab organisation {0}. Interview updates arrive automatically.",
						[frappe.utils.escape_html(frm.doc.organization_name || "")],
				  )
				: __(
						"Connected to {0}, but Ajab cannot send interview updates yet. Give the key the webhooks:manage scope, then click Register webhook. Until then, use Refresh from Ajab on the applicant.",
						[frappe.utils.escape_html(frm.doc.organization_name || "")],
				  ),
			webhookOk ? "green" : "orange",
		);

		frm.add_custom_button(__("Test connection"), () =>
			hrms_ajab.run(frm, "test_connection", (r) =>
				frappe.msgprint(
					__("Connected to {0}. Key scopes: {1}", [r.organization, r.scopes]),
				),
			),
		);
		frm.add_custom_button(
			__("Register webhook"),
			() =>
				hrms_ajab.run(frm, "register_webhook", () =>
					frappe.show_alert({ message: __("Webhook registered"), indicator: "green" }),
				),
			__("Webhook"),
		);
		if (webhookOk) {
			frm.add_custom_button(
				__("Send test event"),
				() =>
					hrms_ajab.run(frm, "send_test_webhook", () =>
						frappe.show_alert({
							message: __(
								"Ajab is sending a test event. Last update received will change in a few seconds.",
							),
							indicator: "blue",
						}),
					),
				__("Webhook"),
			);
		}
		frm.add_custom_button(__("Sync all employees"), () =>
			frappe.confirm(
				__(
					"Send every active employee to Ajab as a team member with the role {0}? New members get an email to set their password.",
					[frm.doc.default_member_role],
				),
				() =>
					hrms_ajab.run(frm, "sync_all_employees", (r) =>
						frappe.show_alert({
							message: __("Syncing {0} employees in the background", [r.queued]),
							indicator: "blue",
						}),
					),
			),
		);
		frm.add_custom_button(__("Disconnect"), () =>
			frappe.confirm(
				__(
					"Disconnect from Ajab? HR forgets the API key and Ajab stops sending interview updates here. Records already in Ajab stay there.",
				),
				() => hrms_ajab.run(frm, "disconnect"),
			),
		);
	},
});

window.hrms_ajab = Object.assign(window.hrms_ajab || {}, {
	run(frm, method, onDone) {
		frappe.call({
			method: `${AJAB_API}.${method}`,
			freeze: true,
			freeze_message: __("Talking to Ajab…"),
			callback: (r) => {
				if (r.exc) return;
				onDone && onDone(r.message);
				frm.reload_doc();
			},
		});
	},

	show_connect_dialog(frm) {
		const dialog = new frappe.ui.Dialog({
			title: __("Connect to Ajab"),
			fields: [
				{
					fieldname: "ajab_url",
					fieldtype: "Data",
					label: __("Ajab API address"),
					reqd: 1,
					default: frm.doc.ajab_url || "https://",
					description: __(
						"The address of the Ajab API, for example https://api.ajab.ai",
					),
				},
				{
					fieldname: "api_key",
					fieldtype: "Password",
					label: __("API key"),
					reqd: 1,
					description: __(
						"From Ajab: Settings → API Keys. Starts with ajab_. Stored encrypted.",
					),
				},
			],
			primary_action_label: __("Connect"),
			primary_action(values) {
				frappe.call({
					method: `${AJAB_API}.connect`,
					args: values,
					freeze: true,
					freeze_message: __("Checking the key with Ajab…"),
					callback: (r) => {
						if (r.exc) return;
						dialog.hide();
						const w = r.message.webhook;
						let note = __("Connected to {0}.", [
							frappe.utils.escape_html(r.message.organization || ""),
						]);
						if (w && w.registered)
							note += " " + __("Ajab will send interview updates to this site.");
						else if (w) note += " " + __("Webhook not registered: {0}", [w.message]);
						else
							note +=
								" " +
								__(
									"The key has no webhooks:manage scope, so interview updates must be refreshed by hand.",
								);
						frappe.msgprint({
							title: __("Ajab"),
							message: note,
							indicator: w && w.registered ? "green" : "orange",
						});
						frm.reload_doc();
					},
				});
			},
		});
		dialog.show();
	},
});
