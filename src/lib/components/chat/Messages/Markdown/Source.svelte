<script lang="ts">
	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';
	import { decodeString } from '$lib/utils';
	import { user } from '$lib/stores';

	// Typed: the bare getContext('i18n') makes svelte-check reject every $i18n.t()
	// in the file with "Cannot use 'i18n' as a store".
	const i18n = getContext<Writable<i18nType>>('i18n');

	// The inline citation chip beside an answer. Clicking it opens the same
	// CitationModal the «Источники» list does, so it carries the same rule:
	// admins only. See the long note in Messages/Citations.svelte — that component
	// owns the decision, this one only has to stop LOOKING clickable.
	//
	// Read from the store here rather than threaded down as a prop: the chip sits
	// six components deep (ResponseMessage -> ContentRenderer -> Markdown ->
	// MarkdownInlineTokens -> SourceToken -> here), and drilling a flag through all
	// of them to change one element's tag is not worth it.
	$: canOpenSources = $user?.role === 'admin';

	export let id;

	export let title: string = 'N/A';

	export let onClick: Function = () => {};

	// Helper function to return only the domain from a URL
	function getDomain(url: string): string {
		const domain = url.replace('http://', '').replace('https://', '').split(/[/?#]/)[0];

		if (domain.startsWith('www.')) {
			return domain.slice(4);
		}
		return domain;
	}

	const getDisplayTitle = (title: string) => {
		if (!title) return 'N/A';
		if (title.length > 30) {
			return title.slice(0, 15) + '...' + title.slice(-10);
		}
		return title;
	};

	// Helper function to check if text is a URL and return the domain
	function formattedTitle(title: string): string {
		if (title.startsWith('http')) {
			return getDomain(title);
		}

		return title;
	}
</script>

{#if title !== 'N/A'}
	{#if canOpenSources}
		<button
			aria-label={$i18n.t('View source: {{title}}', { title: formattedTitle(decodeString(title)) })}
			class="text-[10px] w-fit translate-y-[2px] px-2 py-0.5 dark:bg-white/5 dark:text-white/80 dark:hover:text-white bg-gray-50 text-black/80 hover:text-black transition rounded-xl"
			on:click={() => {
				onClick(id);
			}}
		>
			<span class="line-clamp-1">
				{getDisplayTitle(formattedTitle(decodeString(title)))}
			</span>
		</button>
	{:else}
		<!-- Still says which document the sentence came from — that is the whole
		     value of an inline citation — but no longer offers to open it. Same box,
		     minus the hover states and the cursor. -->
		<span
			class="text-[10px] w-fit inline-block translate-y-[2px] px-2 py-0.5 dark:bg-white/5 dark:text-white/80 bg-gray-50 text-black/80 rounded-xl"
		>
			<span class="line-clamp-1">
				{getDisplayTitle(formattedTitle(decodeString(title)))}
			</span>
		</span>
	{/if}
{/if}
