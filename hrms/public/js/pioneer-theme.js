// Pioneer HR: light/dark mode for the login pages (login, signup, forgot password).
//
// Frappe's web pages never set `data-theme`, so they are always light. This sets it on <html>
// from the choice the employee app saved (localStorage "pcp-theme": light | dark | automatic),
// falling back to the OS setting, so pioneer-theme.css and Frappe's own dark tokens apply.
// Only pages with the login card are touched; other web pages (careers, job openings) stay
// light because they were not designed for dark mode. Loaded through web_include_js in hooks.py.
(function () {
	if (!document.querySelector(".page-card, .for-login, .for-forgot, .for-signup")) return;

	var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

	function savedChoice() {
		try {
			return localStorage.getItem("pcp-theme") || "automatic";
		} catch (e) {
			return "automatic";
		}
	}

	function apply() {
		var choice = savedChoice();
		var dark = choice === "dark" || (choice === "automatic" && media && media.matches);
		document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
	}

	apply();
	if (media && media.addEventListener) media.addEventListener("change", apply);
})();
