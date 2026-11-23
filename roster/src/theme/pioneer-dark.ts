// Pioneer: light/dark mode for Roster, matching PCP.
//
// Sets `data-theme` on <html>, which drives frappe-ui's dark tokens, Tailwind `dark:` variants
// and hrms/public/css/pioneer-ui.css. The choice is the user's Desk theme (User.desk_theme:
// Light | Dark | Automatic, changed from Desk's user menu -> Toggle Theme). It is cached in
// localStorage ("pcp-theme", also read by the login page) so the next load paints at once.
// Automatic, a guest, or a failed lookup falls back to the OS setting.

const KEY = "pcp-theme";
const media = window.matchMedia?.("(prefers-color-scheme: dark)");

function read() {
	try {
		return localStorage.getItem(KEY) || "automatic";
	} catch {
		return "automatic";
	}
}

function save(choice: string) {
	try {
		localStorage.setItem(KEY, choice);
	} catch {
		// storage unavailable (private mode): the theme still applies for this visit
	}
}

function apply(choice: string = read()) {
	const dark = choice === "dark" || (choice === "automatic" && media?.matches);
	document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
}

function sessionUser() {
	const match = document.cookie.match(/(?:^|;\s*)user_id=([^;]*)/);
	const user = match ? decodeURIComponent(match[1]) : "";
	return user && user !== "Guest" ? user : null;
}

async function loadUserChoice() {
	const user = sessionUser();
	if (!user) return;
	const params = new URLSearchParams({
		doctype: "User",
		fieldname: "desk_theme",
		filters: JSON.stringify({ name: user }),
	});
	try {
		const res = await fetch(`/api/method/frappe.client.get_value?${params}`, {
			headers: { Accept: "application/json" },
		});
		if (!res.ok) return;
		const theme = (await res.json())?.message?.desk_theme;
		if (!theme) return;
		const choice = theme.toLowerCase();
		save(choice);
		apply(choice);
	} catch {
		// offline or no permission: keep the cached choice or the OS setting
	}
}

apply();
media?.addEventListener?.("change", () => apply());
loadUserChoice();
