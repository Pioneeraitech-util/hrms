<template>
	<img v-if="variant === 'mark'" :src="`${base}/pcp-icon.svg`" alt="Pioneer Core Platform" />
	<span v-else class="inline-flex">
		<img
			class="pcp-logo-light h-full w-auto"
			:src="`${base}/pcp-logo.svg`"
			alt="Pioneer Core Platform"
		/>
		<img
			class="pcp-logo-dark h-full w-auto"
			:src="`${base}/pcp-logo-dark.svg`"
			alt=""
			aria-hidden="true"
		/>
	</span>
</template>

<script setup>
// Pioneer: the PCP logo. `mark` is the square icon, `wordmark` the full logo, which swaps to
// its dark version in dark mode (classes in hrms/public/css/pioneer-ui.css).
defineProps({
	variant: { type: String, default: "wordmark" },
})
const base = "/assets/hrms/images/pioneer"
</script>
