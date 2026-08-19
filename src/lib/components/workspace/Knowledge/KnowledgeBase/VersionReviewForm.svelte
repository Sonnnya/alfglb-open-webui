<script lang="ts">
	// The approve / reject form for one revision.
	//
	// Its own component because it is rendered in two places: under the registry
	// row (for the latest revision) and inside «История» (for any earlier revision
	// still pending). Those two are not the same thing — once a v3 exists the
	// registry row stops showing a pending v2, so the history badge is the only
	// way to reach it.

	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');

	export let note = '';
	export let submitting = false;
	export let onApprove: () => void = () => {};
	export let onReject: () => void = () => {};
	export let onCancel: () => void = () => {};
</script>

<div class="mt-2 flex flex-col gap-2 rounded-lg bg-gray-50 dark:bg-gray-850 p-2.5">
	<input
		class="w-full text-xs bg-transparent outline-hidden"
		bind:value={note}
		placeholder={$i18n.t('Reason (optional)')}
	/>
	<div class="flex gap-2">
		<button
			type="button"
			class="px-2.5 py-1 rounded-lg text-xs font-medium bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
			disabled={submitting}
			on:click={onApprove}>{$i18n.t('Approve')}</button
		>
		<button
			type="button"
			class="px-2.5 py-1 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
			disabled={submitting}
			on:click={onReject}>{$i18n.t('Reject')}</button
		>
		<button type="button" class="px-2.5 py-1 rounded-lg text-xs" on:click={onCancel}
			>{$i18n.t('Cancel')}</button
		>
	</div>
</div>
