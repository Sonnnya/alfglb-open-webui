<script lang="ts">
	// The folder picker behind «Переместить» in a document's ⋮ menu.
	//
	// Drag-and-drop already moves documents, but only onto something currently on
	// screen: a subfolder row, a breadcrumb, or the sidebar tree. This is the way
	// that works with the keyboard, on a touch screen, and when the destination is
	// a folder you would otherwise have to go looking for.
	//
	// It reads GET /{id}/dirs — the whole tree, flat, each row carrying parent_id —
	// which is the same call the sidebar tree makes. Not /documents: that returns
	// one level at a time, which is right for a listing and useless for a picker.

	import { getContext } from 'svelte';
	import { toast } from 'svelte-sonner';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import { getKnowledgeDirectories } from '$lib/apis/knowledge';

	import Modal from '$lib/components/common/Modal.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import XMark from '$lib/components/icons/XMark.svelte';
	import Folder from '$lib/components/icons/Folder.svelte';
	import BookOpen from '$lib/components/icons/BookOpen.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	type Directory = { id: string; name: string; parent_id: string | null };

	export let show = false;
	export let knowledgeId: string;
	/** Shown in the header so it is obvious *what* is being moved. */
	export let documentName = '';
	/** Where it is now — that row is marked and cannot be chosen. */
	export let currentDirectoryId: string | null = null;
	export let onMove: (targetDirectoryId: string | null) => void = () => {};

	let directories: Directory[] = [];
	let loading = false;
	let selected: string | null = null;
	let moving = false;

	// Flattened depth-first so the list can be drawn with one {#each} and an indent
	// instead of a recursive component. A picker never needs collapsing — the whole
	// point is seeing every destination at once.
	let rows: { directory: Directory; depth: number }[] = [];

	const flatten = () => {
		const childrenOf: Record<string, Directory[]> = {};
		for (const directory of directories) {
			(childrenOf[directory.parent_id ?? ''] ||= []).push(directory);
		}

		const out: { directory: Directory; depth: number }[] = [];
		const seen = new Set<string>();
		const walk = (parentKey: string, depth: number) => {
			for (const directory of childrenOf[parentKey] ?? []) {
				// Guards a parent_id cycle, which nothing in the schema forbids.
				if (seen.has(directory.id)) continue;
				seen.add(directory.id);
				out.push({ directory, depth });
				walk(directory.id, depth + 1);
			}
		};
		walk('', 0);
		rows = out;
	};

	const load = async () => {
		loading = true;
		const res = await getKnowledgeDirectories(localStorage.token, knowledgeId).catch((e) => {
			toast.error(`${e}`);
			return null;
		});
		// The endpoint returns { directories, pending_count, rejected_count } — the
		// counts are for the sidebar tree's dots and mean nothing in a move picker.
		directories = res?.directories ?? [];
		flatten();
		loading = false;
	};

	$: if (show) {
		selected = currentDirectoryId;
		moving = false;
		load();
	}

	const submit = () => {
		if (moving || selected === currentDirectoryId) return;
		moving = true;
		onMove(selected);
		show = false;
	};
</script>

<Modal size="sm" bind:show>
	<div>
		<div class="flex justify-between items-center dark:text-gray-100 px-5 pt-4 pb-2">
			<div class="min-w-0">
				<h3 class="text-base font-medium">{$i18n.t('Move file')}</h3>
				{#if documentName}
					<div class="text-xs text-gray-500 truncate" title={documentName}>{documentName}</div>
				{/if}
			</div>
			<button
				class="self-center shrink-0 ml-2"
				aria-label={$i18n.t('Close')}
				on:click={() => (show = false)}
			>
				<XMark className="size-5" />
			</button>
		</div>

		<div class="px-5 pb-2">
			<div class="max-h-72 overflow-y-auto scrollbar-hidden -mx-1 px-1">
				{#if loading}
					<div class="flex justify-center py-6"><Spinner className="size-4" /></div>
				{:else}
					<!-- The base itself, i.e. no folder at all. First and always present:
					     without it there is no way back out of a folder from this dialog. -->
					<button
						type="button"
						class="w-full flex items-center gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition {selected ===
						null
							? 'bg-gray-100 dark:bg-gray-850'
							: 'hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
						on:click={() => (selected = null)}
					>
						<BookOpen className="size-4 shrink-0 text-gray-500" strokeWidth="1.5" />
						<span class="truncate">{$i18n.t('Knowledge Base')}</span>
						{#if currentDirectoryId === null}
							<span class="ml-auto shrink-0 text-xs text-gray-400">{$i18n.t('Current')}</span>
						{/if}
					</button>

					{#each rows as { directory, depth } (directory.id)}
						<button
							type="button"
							class="w-full flex items-center gap-2 rounded-xl px-2 py-1.5 text-left text-sm transition {selected ===
							directory.id
								? 'bg-gray-100 dark:bg-gray-850'
								: 'hover:bg-gray-50 dark:hover:bg-gray-850/50'}"
							style="padding-left: {0.5 + (depth + 1) * 0.75}rem"
							on:click={() => (selected = directory.id)}
						>
							<Folder className="size-4 shrink-0 text-gray-500" />
							<span class="truncate">{directory.name}</span>
							{#if currentDirectoryId === directory.id}
								<span class="ml-auto shrink-0 text-xs text-gray-400">{$i18n.t('Current')}</span>
							{/if}
						</button>
					{/each}
				{/if}
			</div>
		</div>

		<div class="flex items-center justify-end px-4 pb-3.5 pt-2 gap-2">
			<button
				class="px-3 py-1 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-200 transition"
				type="button"
				on:click={() => (show = false)}
			>
				{$i18n.t('Cancel')}
			</button>
			<button
				class="px-3.5 py-1.5 text-sm bg-black hover:bg-gray-900 text-white dark:bg-white dark:text-black dark:hover:bg-gray-100 transition rounded-full disabled:opacity-50"
				type="button"
				disabled={loading || moving || selected === currentDirectoryId}
				on:click={submit}
			>
				{$i18n.t('Move')}
			</button>
		</div>
	</div>
</Modal>
