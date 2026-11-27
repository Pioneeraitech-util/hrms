// Pioneer HR: the core Pioneer sign-in layout for the login pages (login, signup, forgot password,
// email link). Loaded on web pages through web_include_js in hooks.py.
//
// core.pioneeraitech.com signs in on a two-panel page (ata-parent src/edition/healthcare/auth/
// AuthShell.tsx): a brand panel on the left (logo, eyebrow, title, one line, tagline, the hero
// mark) and the form in a 380px column on the right, with the copyright line at its foot. Frappe's
// login template is one centred card, so this adds the brand panel and footer around it; the
// form itself is Frappe's, restyled by pioneer-theme.css (body.pcp-auth). Under 900px the brand
// panel hides and the card shows its own logo, as on core.
//
// Core's sign-in page is light in both OS modes, so these pages are too (data-theme="light").
// Other web pages (careers, job openings) are not touched.
(function () {
	if (!document.querySelector(".for-login, .for-forgot, .for-signup, .for-login-with-email-link")) return;

	document.documentElement.setAttribute("data-theme", "light");
	var body = document.body;
	if (!body || body.classList.contains("pcp-auth")) return;
	body.classList.add("pcp-auth");

	function el(tag, cls, text) {
		var n = document.createElement(tag);
		if (cls) n.className = cls;
		if (text) n.textContent = text;
		return n;
	}

	var brand = el("aside", "pcp-auth-brand");
	brand.setAttribute("aria-label", "Pioneer HR");

	var logo = el("img", "pcp-auth-logo");
	logo.src = "/assets/hrms/images/pioneer/pcp-logo.svg";
	logo.alt = "Pioneer Healthcare";
	brand.appendChild(logo);

	var copy = el("div", "pcp-auth-copy");
	copy.appendChild(el("p", "pcp-auth-eyebrow", "Hire • Manage • Pay • Grow"));
	copy.appendChild(el("h2", "pcp-auth-title", "Pioneer HR"));
	copy.appendChild(
		el("p", "pcp-auth-lead", "Sign in to manage people, leave, attendance and payroll.")
	);
	brand.appendChild(copy);

	brand.appendChild(el("p", "pcp-auth-tagline", "Technology for a healthier tomorrow"));

	var art = el("img", "pcp-auth-art");
	art.src = "/assets/hrms/images/pioneer/pcp-hero-mark.png";
	art.alt = "";
	art.setAttribute("aria-hidden", "true");
	brand.appendChild(art);

	body.insertBefore(brand, body.firstChild);

	// Sentence case, as everywhere on core ("Sign in", not "Sign In"). Only the untranslated
	// English titles are touched.
	var titles = { "Sign In": "Sign in", "Sign Up": "Sign up", "Forgot Password?": "Forgot password?" };
	document.querySelectorAll(".page-card-head h4").forEach(function (h) {
		var t = h.textContent.trim();
		if (titles[t]) h.textContent = titles[t];
	});

	var main = document.querySelector("#page-login, .page-content-wrapper");
	if (main) {
		var foot = el(
			"p",
			"pcp-auth-foot",
			"© " + new Date().getFullYear() + " Pioneer Healthcare Platform"
		);
		main.appendChild(foot);
	}
})();
