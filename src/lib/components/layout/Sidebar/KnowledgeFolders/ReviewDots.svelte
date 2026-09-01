<script lang="ts">
	// The yellow/red marks the sidebar knowledge tree draws next to a folder — and
	// next to the base's own root row, which is why this is a component rather than
	// six lines inlined in the node: the root row is not a KnowledgeFolderNode and
	// the two must never drift in colour, size or wording.
	//
	// Dots only, no numbers. The tree is a narrow column whose job is «where do I
	// go», and the count lives on the folder rows of the knowledge base screen,
	// which is where you land. The tooltip carries it for anyone who wants it.
	//
	// Solid bg-*-500, not Badge.svelte's bg-*-500/20 — at 6px a 20% wash reads as
	// nothing — but the same hue as the «Ждет проверки» / «Отклонено» badges the
	// document rows carry, which is the association worth borrowing.
	//
	// Each dot's hover target is padded out with `p-1 -m-1`: the tooltip is the only
	// place the number lives here, and a 6px target in a narrow column is a hint
	// nobody can hit. The negative margin cancels the padding, so nothing moves.

	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Tooltip from '$lib/components/common/Tooltip.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	export let pending: number | null | undefined = 0;
	export let rejected: number | null | undefined = 0;
	/**
	 * Whether the counts are the viewer's own documents rather than everything.
	 * Only changes the tooltip wording — the backend has already scoped the
	 * numbers — but «2 отклонено» and «2 ваших документа отклонено» are different
	 * claims and the wrong one sends an Эксперт hunting for other people's files.
	 */
	export let scopedToViewer = false;
	export let className = '';
</script>

{#if pending || rejected}
	<span class="flex items-center gap-1 shrink-0 {className}">
		<!-- Red first, as on the knowledge base screen: a rejected document is
		     somebody's move to make now, a pending one is a queue. -->
		{#if rejected}
			<Tooltip
				as="span"
				className="flex"
				content={scopedToViewer
					? $i18n.t('{{count}} of your documents rejected', { count: rejected })
					: $i18n.t('{{count}} rejected', { count: rejected })}
			>
				<span class="p-1 -m-1 flex">
					<span class="size-1.5 rounded-full bg-red-500" />
				</span>
			</Tooltip>
		{/if}

		{#if pending}
			<Tooltip
				as="span"
				className="flex"
				content={scopedToViewer
					? $i18n.t('{{count}} of your documents awaiting review', { count: pending })
					: $i18n.t('{{count}} awaiting review', { count: pending })}
			>
				<span class="p-1 -m-1 flex">
					<span class="size-1.5 rounded-full bg-yellow-500" />
				</span>
			</Tooltip>
		{/if}
	</span>
{/if}
