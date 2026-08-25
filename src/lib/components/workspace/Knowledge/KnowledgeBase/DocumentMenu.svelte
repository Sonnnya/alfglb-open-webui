<script lang="ts">
	// The ⋮ menu on a registry row — everything that used to sit inline as a row of
	// underlined links («Скачать», «Загрузить новую версию», «История», «Удалить
	// все версии»). Four controls per row cost more horizontal space than the
	// filename they belonged to, and a ten-row list read as a wall of links.
	//
	// Deliberately the same Dropdown markup as DirectoryRow: folder rows and
	// document rows sit in one column, so their menus must look and behave alike.

	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import Download from '$lib/components/icons/Download.svelte';
	import DocumentArrowUp from '$lib/components/icons/DocumentArrowUp.svelte';
	import ClockRotateRight from '$lib/components/icons/ClockRotateRight.svelte';
	import ArrowRightTag from '$lib/components/icons/ArrowRightTag.svelte';
	import CheckCircle from '$lib/components/icons/CheckCircle.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	/** Direct link to the published bytes; null when there is nothing to download. */
	export let downloadHref: string | null = null;
	/**
	 * Offer the review actions — a reviewer looking at a revision still awaiting
	 * review. Gates BOTH «Одобрить версию» and «Отклонить версию»: they are the two
	 * outcomes of one decision and are available under exactly the same conditions,
	 * so a single flag is what keeps them from drifting apart.
	 */
	export let canReview = false;
	export let canUpload = false;
	export let canDelete = false;
	/** Offer «Переместить» — anyone who may drag the row may also use the dialog. */
	export let canMove = false;
	/** True while this row's new-version upload is in flight. */
	export let uploading = false;
	/** True while any row's delete is in flight. */
	export let deleting = false;

	export let onApprove: () => void = () => {};
	export let onReject: () => void = () => {};
	export let onUploadVersion: () => void = () => {};
	export let onMove: () => void = () => {};
	export let onHistory: () => void = () => {};
	export let onDelete: () => void = () => {};

	let show = false;

	// Every item closes the menu itself. DirectoryRow gets away without it on
	// delete because a confirm dialog covers the menu; «История» opens a panel
	// underneath it, so a menu left open floats over the thing it just revealed.
	const run = (action: () => void) => {
		show = false;
		action();
	};

	const itemClass =
		'select-none flex rounded-xl py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition items-center gap-2 text-sm disabled:opacity-50';
</script>

<Dropdown bind:show align="end" sideOffset={4}>
	<button
		class="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-850 transition"
		type="button"
		aria-label={$i18n.t('More')}
	>
		<EllipsisHorizontal className="size-3.5" />
	</button>

	<div slot="content">
		<div
			class="min-w-[200px] rounded-2xl p-1 z-[9999999] bg-white dark:bg-gray-850 dark:text-white shadow-lg border border-gray-100 dark:border-gray-800"
		>
			{#if canReview}
				<!-- The two outcomes of a review, listed separately because a menu with
				     only «Одобрить» reads as if rejecting were impossible. Both open the
				     same VersionReviewForm — the one the status badge opens too — with
				     the chosen action pre-selected; the form still offers the other one,
				     so changing your mind after reading the file costs nothing.
				
				     «версию», not «файл»: what gets approved is one revision, not the
				     document. Approving a v2 while a v3 sits pending is a normal thing to
				     do here, and the old label made that sound impossible. -->
				<button type="button" class={itemClass} on:click={() => run(onApprove)}>
					<CheckCircle className="size-3.5" />
					{$i18n.t('Approve version')}
				</button>
				<button type="button" class={itemClass} on:click={() => run(onReject)}>
					<XMark className="size-3.5" />
					{$i18n.t('Reject version')}
				</button>
			{/if}

			{#if downloadHref}
				<a
					class={itemClass}
					href={downloadHref}
					target="_blank"
					rel="noopener noreferrer"
					on:click={() => (show = false)}
				>
					<Download className="size-3.5" />
					{$i18n.t('Download')}
				</a>
			{/if}

			{#if canUpload}
				<button
					type="button"
					class={itemClass}
					disabled={uploading}
					on:click={() => run(onUploadVersion)}
				>
					<DocumentArrowUp className="size-3.5" />
					{$i18n.t('Upload new version')}
				</button>
			{/if}

			{#if canMove}
				<!-- Drag-and-drop can only reach a destination that is already on
				     screen. This reaches any folder in the base, works on a touch
				     screen, and is the only keyboard-operable way to move a document. -->
				<button type="button" class={itemClass} on:click={() => run(onMove)}>
					<ArrowRightTag className="size-3.5" />
					{$i18n.t('Move file')}
				</button>
			{/if}

			<button type="button" class={itemClass} on:click={() => run(onHistory)}>
				<ClockRotateRight className="size-3.5" />
				{$i18n.t('History')}
			</button>

			{#if canDelete}
				<hr class="border-gray-100 dark:border-gray-800 my-1" />
				<button
					type="button"
					class="{itemClass} text-red-600 dark:text-red-500"
					disabled={deleting}
					on:click={() => run(onDelete)}
				>
					<GarbageBin className="size-3.5" />
					{$i18n.t('Delete entire chain')}
				</button>
			{/if}
		</div>
	</div>
</Dropdown>
