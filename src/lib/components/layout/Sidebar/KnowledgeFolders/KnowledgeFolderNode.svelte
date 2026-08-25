<script lang="ts">
	// One row of the sidebar knowledge tree, recursing into its own children.
	//
	// Expansion state lives in the parent, not here: opening a deep link has to be
	// able to expand every ancestor of the target folder at once, which a node that
	// owns its own boolean cannot be told to do.

	import Folder from '$lib/components/icons/Folder.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import { isKnowledgeDrag, readDirectoryDrag, readDocumentDrag } from '$lib/utils/knowledge-dnd';

	type Directory = { id: string; name: string; parent_id: string | null };

	export let directory: Directory;
	export let childrenOf: Record<string, Directory[]> = {};
	export let expanded: Record<string, boolean> = {};
	export let activeId: string | null = null;
	export let depth = 0;

	export let onOpen: (directoryId: string) => void = () => {};
	export let onToggle: (directoryId: string) => void = () => {};
	/**
	 * A drop landed on this row. The parent performs the move — it holds the
	 * knowledge id and the API client — so a node stays what it was: a row that
	 * knows its own id and nothing about the base.
	 */
	export let onDrop: (
		payload: { documentId?: string; directoryId?: string },
		targetDirectoryId: string | null
	) => void = () => {};

	$: children = childrenOf[directory.id] ?? [];

	let dragOver = false;
</script>

<div>
	<!-- svelte-ignore a11y-no-static-element-interactions -->
	<div
		class="w-full flex items-center gap-1 rounded-lg transition {dragOver
			? 'bg-gray-100 dark:bg-gray-800 ring-1 ring-gray-300 dark:ring-gray-600'
			: activeId === directory.id
				? 'bg-gray-100 dark:bg-gray-900'
				: 'hover:bg-gray-100 dark:hover:bg-gray-900'}"
		style="padding-left: {depth * 0.75}rem"
		on:dragover={(e) => {
			if (!isKnowledgeDrag(e.dataTransfer)) return;
			// preventDefault is what marks this element as a valid drop target; without
			// it the browser refuses the drop and the drag just snaps back.
			e.preventDefault();
			e.stopPropagation();
			dragOver = true;
		}}
		on:dragleave={() => (dragOver = false)}
		on:drop={(e) => {
			e.preventDefault();
			e.stopPropagation();
			dragOver = false;

			const documentId = readDocumentDrag(e.dataTransfer);
			if (documentId) {
				onDrop({ documentId }, directory.id);
				return;
			}

			const directoryId = readDirectoryDrag(e.dataTransfer);
			if (directoryId && directoryId !== directory.id) {
				onDrop({ directoryId }, directory.id);
			}
		}}
	>
		<!-- The chevron ONLY toggles, so you can look inside a folder without leaving
		     the one you are in. The label does both: it opens the folder on the right
		     AND reveals its children on the left, which is what Explorer does on a
		     single click and what makes the tree usable without hunting for chevrons. -->
		{#if children.length > 0}
			<button
				class="p-1 shrink-0 text-gray-400 dark:text-gray-600"
				type="button"
				aria-label={directory.name}
				on:click|stopPropagation={() => onToggle(directory.id)}
			>
				<ChevronRight
					className="size-3 transition-transform {expanded[directory.id] ? 'rotate-90' : ''}"
				/>
			</button>
		{:else}
			<div class="size-5 shrink-0" />
		{/if}

		<button
			class="flex-1 min-w-0 flex items-center gap-1.5 py-1 pr-2 text-left"
			type="button"
			on:click={() => {
				// Expand on the way in, never collapse: clicking a folder you are
				// already inside should not fold away the children you came to see.
				if (children.length > 0 && !expanded[directory.id]) {
					onToggle(directory.id);
				}
				onOpen(directory.id);
			}}
		>
			<Folder className="size-3.5 shrink-0 text-gray-500" />
			<span class="truncate text-sm">{directory.name}</span>
		</button>
	</div>

	{#if expanded[directory.id]}
		{#each children as child (child.id)}
			<svelte:self
				directory={child}
				{childrenOf}
				{expanded}
				{activeId}
				depth={depth + 1}
				{onOpen}
				{onToggle}
				{onDrop}
			/>
		{/each}
	{/if}
</div>
