<script lang="ts">
	// The welding knowledge base's directory tree, in the sidebar slot the upstream
	// chat «Папки» used to occupy (those are off — see ENABLE_FOLDERS in config.py).
	//
	// Navigation only. Creating, renaming, deleting and moving folders all live on
	// the knowledge base screen, which is the one place that can also show what is
	// inside them; a second set of controls here would be two menus that have to
	// agree about permissions and refreshes. Clicking a folder opens the screen
	// scoped to it, via WELDING_KB_HREF?dir=<id>.

	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	import { WELDING_KB_HREF } from '$lib/constants';
	import { getKnowledgeDirectories } from '$lib/apis/knowledge';
	import { knowledgeDirectoryRevision, activeKnowledgeDirectoryId } from '$lib/stores';

	import Folder from '$lib/components/icons/Folder.svelte';
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte';
	import KnowledgeFolderNode from './KnowledgeFolders/KnowledgeFolderNode.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	export let knowledgeId: string;

	type Directory = { id: string; name: string; parent_id: string | null };

	let directories: Directory[] = [];
	let loaded = false;
	let open = true;
	let expanded: Record<string, boolean> = {};

	// parent_id -> children, so each node looks its children up instead of
	// filtering the whole list (O(n²) once a base has real depth).
	let childrenOf: Record<string, Directory[]> = {};
	$: {
		const next: Record<string, Directory[]> = {};
		for (const directory of directories) {
			const key = directory.parent_id ?? '';
			(next[key] ||= []).push(directory);
		}
		childrenOf = next;
	}

	// Which folder the knowledge base screen is showing, so the tree can highlight
	// it. From the shared store rather than the URL: the address bar is updated
	// cosmetically and $page.url does not reliably reflect it in the same tick.
	$: onKnowledgeScreen = $page.url.pathname.startsWith(WELDING_KB_HREF);
	$: activeId = onKnowledgeScreen ? $activeKnowledgeDirectoryId : null;

	export const refresh = async () => {
		const res = await getKnowledgeDirectories(localStorage.token, knowledgeId).catch(() => null);
		// Deliberately silent: a sidebar section the user did not ask for should not
		// raise a toast when it fails. It stays empty instead.
		if (res) {
			directories = res;
		}
		loaded = true;
	};

	// A folder deep in the tree is unreachable while its ancestors are collapsed,
	// so a deep link expands the path down to its target once the rows are known.
	const revealPathTo = (directoryId: string | null) => {
		if (!directoryId) return;
		const byId = new Map(directories.map((d) => [d.id, d]));
		let current = byId.get(directoryId);
		const seen = new Set<string>();
		while (current?.parent_id && !seen.has(current.parent_id)) {
			seen.add(current.parent_id);
			expanded[current.parent_id] = true;
			current = byId.get(current.parent_id);
		}
		expanded = expanded;
	};

	$: if (loaded && activeId) revealPathTo(activeId);

	// Refetch whenever the knowledge base screen creates, renames, moves or deletes
	// a folder. Without this the tree is whatever it was at mount — a folder made
	// on the right never appears on the left until a reload, which reads as the
	// creation having failed. Referencing the store inside the block is what makes
	// this reactive to it.
	let appliedRevision = -1;
	$: if (loaded && $knowledgeDirectoryRevision !== appliedRevision) {
		appliedRevision = $knowledgeDirectoryRevision;
		refresh();
	}

	const openDirectory = (directoryId: string | null) => {
		// Publish first, so a screen that is already mounted reacts immediately.
		activeKnowledgeDirectoryId.set(directoryId);

		const href = directoryId ? `${WELDING_KB_HREF}?dir=${directoryId}` : WELDING_KB_HREF;
		if (onKnowledgeScreen) {
			// Already there — a goto() to the same route would not remount the screen
			// anyway, and the store has done the work. Just keep the URL honest.
			history.replaceState(history.state, '', href);
		} else {
			// Coming from a chat or elsewhere: route to the screen, which reads ?dir=
			// once on mount.
			goto(href);
		}
	};

	const toggle = (directoryId: string) => {
		expanded = { ...expanded, [directoryId]: !expanded[directoryId] };
	};

	onMount(refresh);
</script>

{#if loaded && directories.length > 0}
	<div class="px-2 mt-0.5">
		<!-- The base itself is the root NODE of the tree, not a section header with a
		     separate «All documents» entry underneath. That entry was the artefact of
		     using Folder.svelte as the header: it expands and collapses but dispatches
		     no click, so getting back to the root needed a row of its own. Explorer
		     does not work that way — the root is one row, its chevron folds the tree,
		     its label opens the root. So this is the same KnowledgeFolderNode markup
		     as every other row, with a null id meaning "the base". -->
		<div
			class="w-full flex items-center gap-1 rounded-lg transition {activeId === null &&
			$page.url.pathname.startsWith(WELDING_KB_HREF)
				? 'bg-gray-100 dark:bg-gray-900'
				: 'hover:bg-gray-100 dark:hover:bg-gray-900'}"
		>
			<button
				class="p-1 shrink-0 text-gray-400 dark:text-gray-600"
				type="button"
				aria-label={$i18n.t('Knowledge base')}
				on:click|stopPropagation={() => (open = !open)}
			>
				<ChevronRight className="size-3 transition-transform {open ? 'rotate-90' : ''}" />
			</button>

			<button
				class="flex-1 min-w-0 flex items-center gap-1.5 py-1 pr-2 text-left"
				type="button"
				on:click={() => openDirectory(null)}
			>
				<Folder className="size-3.5 shrink-0 text-gray-500" />
				<span class="truncate text-sm">{$i18n.t('Knowledge base')}</span>
			</button>
		</div>

		{#if open}
			{#each childrenOf[''] ?? [] as directory (directory.id)}
				<KnowledgeFolderNode
					{directory}
					{childrenOf}
					{expanded}
					{activeId}
					depth={1}
					onOpen={openDirectory}
					onToggle={toggle}
				/>
			{/each}
		{/if}
	</div>
{/if}
