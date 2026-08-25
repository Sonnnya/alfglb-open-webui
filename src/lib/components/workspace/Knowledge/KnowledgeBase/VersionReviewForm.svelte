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
	/**
	 * Which outcome the reviewer reached for. Both buttons are always rendered —
	 * this only decides which one is solid and which is outlined, so opening the
	 * form from «Отклонить версию» does not present «Одобрить» as the obvious
	 * thing to click. Defaults to 'approve', which is what the status badge means.
	 */
	export let intent: 'approve' | 'reject' = 'approve';
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
	<!-- Order is fixed regardless of intent: buttons that swap places between
	     openings are how people click the wrong one. Only the emphasis moves. -->
	<div class="flex gap-2">
		<button
			type="button"
			class="px-2.5 py-1 rounded-lg text-xs font-medium disabled:opacity-50 {intent === 'approve'
				? 'bg-green-600 hover:bg-green-700 text-white'
				: 'border border-green-600 text-green-700 dark:text-green-500 hover:bg-green-600/10'}"
			disabled={submitting}
			on:click={onApprove}>{$i18n.t('Approve')}</button
		>
		<button
			type="button"
			class="px-2.5 py-1 rounded-lg text-xs font-medium disabled:opacity-50 {intent === 'reject'
				? 'bg-red-600 hover:bg-red-700 text-white'
				: 'border border-red-600 text-red-700 dark:text-red-500 hover:bg-red-600/10'}"
			disabled={submitting}
			on:click={onReject}>{$i18n.t('Reject')}</button
		>
		<button type="button" class="px-2.5 py-1 rounded-lg text-xs" on:click={onCancel}
			>{$i18n.t('Cancel')}</button
		>
	</div>
</div>
