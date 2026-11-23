import frappeUIPreset from "frappe-ui/src/tailwind/preset";
export default {
	presets: [frappeUIPreset],
	content: [
		"./index.html",
		"./src/**/*.{vue,js,ts,jsx,tsx}",
		"./node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
		"../node_modules/frappe-ui/src/components/**/*.{vue,js,ts,jsx,tsx}",
	],
	theme: {
		extend: {
			// Pioneer: gray follows the PCP theme and dark mode (hrms/public/css/pioneer-ui.css)
			colors: {
				gray: Object.fromEntries(
					[50, 100, 200, 300, 400, 500, 600, 700, 800, 900].map((s) => [
						s,
						`rgb(var(--pcp-gray-${s}) / <alpha-value>)`,
					])
				),
			},
		},
	},
	plugins: [],
};
