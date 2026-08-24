<script lang="ts">
	import { afterUpdate, getContext } from 'svelte';
	const i18n = getContext('i18n');

	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import { isKnowledgeDrag, readDirectoryDrag, readDocumentDrag } from '$lib/utils/knowledge-dnd';

	export let rootLabel: string = 'Root';
	export let breadcrumbs: { id: string; name: string }[] = [];
	export let onNavigate: (directoryId: string | null) => void = () => {};
	/**
	 * A DOCUMENT id, despite the name and the payload key — see knowledge-dnd.ts.
	 * The parent must therefore route this to the document-keyed move, not the
	 * file-keyed one: wiring it to the latter is what made dropping onto a
	 * breadcrumb silently fail, since a document id is not a file id.
	 */
	export let onMoveFile: (documentId: string, targetDirectoryId: string | null) => void = () => {};
	export let onMoveDir: (dirId: string, targetDirectoryId: string | null) => void = () => {};

	let breadcrumbEl: HTMLDivElement;
	let dragOverCrumb: number | null = null;

	afterUpdate(() => {
		if (breadcrumbEl) breadcrumbEl.scrollLeft = breadcrumbEl.scrollWidth;
	});

	const handleDragOver = (e: DragEvent, index: number) => {
		if (!isKnowledgeDrag(e.dataTransfer)) return;
		e.preventDefault();
		e.stopPropagation();
		dragOverCrumb = index;
	};

	const handleDragLeave = (index: number) => {
		if (dragOverCrumb === index) dragOverCrumb = null;
	};

	const handleDrop = (e: DragEvent, targetDirId: string | null) => {
		e.preventDefault();
		e.stopPropagation();
		dragOverCrumb = null;

		const documentId = readDocumentDrag(e.dataTransfer);
		if (documentId) {
			onMoveFile(documentId, targetDirId);
			return;
		}

		const dirId = readDirectoryDrag(e.dataTransfer);
		// A crumb IS an ancestor of the folder being dragged, so this is the only
		// way to move a folder UP the tree — the folder rows below can only ever
		// take it deeper.
		if (dirId && dirId !== targetDirId) {
			onMoveDir(dirId, targetDirId);
		}
	};
</script>

<div
	bind:this={breadcrumbEl}
	class="flex items-center flex-1 min-w-0 overflow-x-auto scrollbar-none"
>
	<button
		class="text-xs shrink-0 py-0.5 hover:underline transition
			{breadcrumbs.length === 0
			? 'text-gray-700 dark:text-gray-300'
			: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400'}
			{dragOverCrumb === -1 ? 'bg-gray-100 dark:bg-gray-800 rounded-lg' : ''}"
		on:click={() => onNavigate(null)}
		on:dragover={(e) => handleDragOver(e, -1)}
		on:dragleave={() => handleDragLeave(-1)}
		on:drop={(e) => handleDrop(e, null)}
	>
		{rootLabel}
	</button>

	{#each breadcrumbs as crumb, i}
		<ChevronRight className="size-3 shrink-0 mx-0.5 text-gray-300 dark:text-gray-600" />
		<button
			class="text-xs shrink-0 py-0.5 hover:underline transition
				{i === breadcrumbs.length - 1
				? 'text-gray-700 dark:text-gray-300'
				: 'text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400'}
				{dragOverCrumb === i ? 'bg-gray-100 dark:bg-gray-800 rounded-lg' : ''}"
			on:click={() => onNavigate(crumb.id)}
			on:dragover={(e) => handleDragOver(e, i)}
			on:dragleave={() => handleDragLeave(i)}
			on:drop={(e) => handleDrop(e, crumb.id)}
		>
			{crumb.name}
		</button>
	{/each}
</div>
