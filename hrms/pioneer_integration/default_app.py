import frappe


def set_hrms_as_default_app():
	"""Open Pioneer HR right after sign-in, not the apps screen.

	Frappe sends a signed-in user to the default app's route (add_to_apps_screen -> app_home,
	/desk/hr-setup). The site default lives in System Settings; a user's own default (User.default_app)
	still wins. Runs on every migrate, so a fresh site and every deploy get it.
	"""
	if "hrms" not in frappe.get_installed_apps():
		return
	if not frappe.get_meta("System Settings").has_field("default_app"):
		return
	if frappe.db.get_single_value("System Settings", "default_app") != "hrms":
		frappe.db.set_single_value("System Settings", "default_app", "hrms")
		frappe.clear_cache()
