<script lang="ts">
	import dayjs from '$lib/dayjs';
	import duration from 'dayjs/plugin/duration';
	import relativeTime from 'dayjs/plugin/relativeTime';

	dayjs.extend(duration);
	dayjs.extend(relativeTime);

	import { getContext } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	// Typed, like DocumentRegistry: the bare getContext('i18n') makes svelte-check
	// reject every $i18n.t() in the file with "Cannot use 'i18n' as a store".
	const i18n = getContext<Writable<i18nType>>('i18n');

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte';
	import Pencil from '$lib/components/icons/Pencil.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte';
	import {
		isKnowledgeDrag,
		readDirectoryDrag,
		readDocumentDrag,
		setDirectoryDrag
	} from '$lib/utils/knowledge-dnd';

	export let directory: {
		id: string;
		name: string;
		created_at: number;
		updated_at: number;
		/** Documents in this folder AND everything under it. */
		file_count?: number | null;
	};
	export let writeAccess = false;

	export let onNavigate: (id: string) => void = () => {};
	export let onRename: (id: string, name: string) => void = () => {};
	export let onDelete: (id: string) => void = () => {};
	export let onFileDrop: (fileId: string, directoryId: string) => void = () => {};
	export let onDirDrop: (dirId: string, targetDirectoryId: string) => void = () => {};
	let editing = false;
	let editName = '';
	let editInput: HTMLInputElement;
	let dragOver = false;
	let showDropdown = false;

	const startRename = () => {
		editName = directory.name;
		editing = true;
		showDropdown = false;
		setTimeout(() => editInput?.select(), 0);
	};

	const submitRename = () => {
		if (!editName.trim() || editName === directory.name) {
			editing = false;
			return;
		}
		onRename(directory.id, editName.trim());
		editing = false;
	};

	const cancelRename = () => {
		editing = false;
	};
</script>

<!-- svelte-ignore a11y-no-static-element-interactions -->
<div
	class="group flex items-center gap-2.5 cursor-pointer w-full bg-transparent dark:hover:bg-gray-850/50 hover:bg-white rounded-xl transition
		{dragOver
		? 'bg-gray-100 dark:bg-gray-800 ring-1 ring-gray-300 dark:ring-gray-600'
		: 'hover:bg-gray-100 dark:hover:bg-gray-850'}"
	draggable="true"
	on:dragstart={(e) => {
		setDirectoryDrag(e.dataTransfer, directory.id);
	}}
	on:dblclick={() => {
		if (writeAccess) startRename();
	}}
	on:dragover={(e) => {
		if (!isKnowledgeDrag(e.dataTransfer)) return;
		e.preventDefault();
		e.stopPropagation();
		dragOver = true;
	}}
	on:dragleave={() => {
		dragOver = false;
	}}
	on:drop={(e) => {
		e.preventDefault();
		e.stopPropagation();
		dragOver = false;

		const documentId = readDocumentDrag(e.dataTransfer);
		if (documentId) {
			onFileDrop(documentId, directory.id);
			return;
		}

		const dirId = readDirectoryDrag(e.dataTransfer);
		// Dropping a folder on itself is a no-op, not a cycle — the backend also
		// refuses, but silently doing nothing reads better than a toast.
		if (dirId && dirId !== directory.id) {
			onDirDrop(dirId, directory.id);
		}
	}}
>
	<!-- Sized and inset to match the document rows this now sits above in
	     DocumentRegistry: same size-4 glyph, same text-gray-500, and no padding of
	     its own so both icons share one left edge. It used to be a size-3.5 glyph
	     inside a p-1 button inside a px-2 row — 2px smaller and 12px further in,
	     which read as a wobble down the column. gap-2.5 on the row (above) is the
	     document row's gap, so the labels line up too. -->
	<button class="text-gray-500 shrink-0" type="button" on:click={() => onNavigate(directory.id)}>
		<Folder className="size-4" />
	</button>

	<button
		class="relative flex items-center gap-1 rounded-xl text-left flex-1 justify-between"
		type="button"
		on:click={() => {
			if (editing) return;
			onNavigate(directory.id);
		}}
	>
		<div>
			<div class="flex gap-2 items-center line-clamp-1">
				{#if editing}
					<!-- svelte-ignore a11y-autofocus -->
					<input
						bind:this={editInput}
						bind:value={editName}
						class="text-sm w-full bg-transparent border-none outline-hidden"
						on:keydown={(e) => {
							if (e.key === 'Enter') submitRename();
							if (e.key === 'Escape') cancelRename();
							if (e.key === ' ') e.stopPropagation();
						}}
						on:keyup={(e) => {
							if (e.key === ' ') e.stopPropagation();
						}}
						on:blur={submitRename}
						on:click={(e) => e.stopPropagation()}
						autofocus
					/>
				{:else}
					<div class="line-clamp-1 text-sm">
						{directory.name}
					</div>
				{/if}
			</div>
		</div>

		<div class="flex items-center gap-2 shrink-0">
			<!-- The whole subtree, not this level: a folder that only contains
			     folders would otherwise read «0» while holding the entire corpus.
			     Rendered for 0 as well — an empty folder saying so is information,
			     and a number that appears and disappears makes the column jump. -->
			{#if directory.file_count !== null && directory.file_count !== undefined}
				<div class="text-xs text-gray-400">
					{$i18n.t('{{count}} files', { count: directory.file_count })}
				</div>
			{/if}

			{#if directory.updated_at}
				<Tooltip content={dayjs(directory.updated_at * 1000).format('LLLL')}>
					<div class="text-xs text-gray-400">
						{dayjs(directory.updated_at * 1000).fromNow()}
					</div>
				</Tooltip>
			{/if}
		</div>
	</button>

	{#if writeAccess}
		<div class="flex items-center">
			<Dropdown bind:show={showDropdown} align="end" sideOffset={4}>
				<button
					class="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-gray-850 transition"
					type="button"
				>
					<EllipsisHorizontal className="size-3.5" />
				</button>

				<div slot="content">
					<div
						class="min-w-[140px] rounded-2xl p-1 z-[9999999] bg-white dark:bg-gray-850 dark:text-white shadow-lg border border-gray-100 dark:border-gray-800"
					>
						<button
							type="button"
							class="select-none flex rounded-xl py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition items-center gap-2 text-sm"
							on:click={() => startRename()}
						>
							<Pencil className="size-3.5" />
							{$i18n.t('Rename')}
						</button>
						<button
							type="button"
							class="select-none flex rounded-xl py-1.5 px-3 w-full hover:bg-gray-50 dark:hover:bg-gray-800 transition items-center gap-2 text-sm"
							on:click={() => onDelete(directory.id)}
						>
							<GarbageBin className="size-3.5" />
							{$i18n.t('Delete')}
						</button>
					</div>
				</div>
			</Dropdown>
		</div>
	{/if}
</div>
