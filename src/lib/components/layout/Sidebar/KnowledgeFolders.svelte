<script lang="ts">
	// The welding knowledge base's directory tree, in the sidebar slot the upstream
	// chat «Папки» used to occupy (those are off — see ENABLE_FOLDERS in config.py).
	//
	// Its root row IS the «База знаний» menu entry — same BookOpen icon, same row
	// styling, same left edge as «Рабочее пространство» above it. Sidebar.svelte
	// therefore skips the pinned 'knowledge' item when this renders: two rows with
	// one label, one of which silently did nothing when you were already on the
	// screen, was the confusing part. Clicking the root now always lands on the
	// base's root folder, from anywhere.
	//
	// Navigation, plus one mutation: it accepts DROPS. Creating, renaming and
	// deleting folders still live on the knowledge base screen, which is the one
	// place that can also show what is inside them; a second set of menus here
	// would be two surfaces that have to agree about permissions and refreshes.
	//
	// A drop is different from a menu. The tree is the only place showing the whole
	// hierarchy at once, so it is the only place you can move something UP several
	// levels in one gesture — the folder rows on the right can only ever take a
	// document deeper. The drag can only start on the knowledge base screen (that
	// is where the draggable rows are, and they are gated on write access), so this
	// adds a target, not a new way in.
	//
	// Clicking a folder opens the screen scoped to it, via WELDING_KB_HREF?dir=<id>.

	import { getContext, onMount } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import { page } from '$app/stores';
	import { goto } from '$app/navigation';

	import { toast } from 'svelte-sonner';

	import { WELDING_KB_HREF } from '$lib/constants';
	import {
		getKnowledgeDirectories,
		moveDocumentInKnowledge,
		updateKnowledgeDirectory
	} from '$lib/apis/knowledge';
	import {
		knowledgeDirectoryRevision,
		knowledgeDocumentRevision,
		activeKnowledgeDirectoryId
	} from '$lib/stores';
	import { isKnowledgeDrag, readDirectoryDrag, readDocumentDrag } from '$lib/utils/knowledge-dnd';

	import BookOpen from '$lib/components/icons/BookOpen.svelte';
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

	// ── Drops ─────────────────────────────────────────────────────────────
	//
	// Performed here rather than handed to the knowledge base screen: the two are
	// separate component trees with no props between them, and this one already
	// holds the knowledge id and talks to the API for /dirs. The screen finds out
	// through the revision counters, exactly as this component finds out about the
	// folders it creates.
	let rootDragOver = false;

	const handleDrop = async (
		payload: { documentId?: string; directoryId?: string },
		targetDirectoryId: string | null
	) => {
		if (payload.documentId) {
			const res = await moveDocumentInKnowledge(
				localStorage.token,
				knowledgeId,
				payload.documentId,
				targetDirectoryId
			).catch((e) => {
				toast.error(`${e}`);
				return null;
			});

			if (res) {
				toast.success($i18n.t('File moved.'));
				// The screen on the right is what renders the document list; it has no
				// other way to learn the row it is showing has moved.
				knowledgeDocumentRevision.update((n) => n + 1);
			}
			return;
		}

		if (payload.directoryId) {
			const res = await updateKnowledgeDirectory(
				localStorage.token,
				knowledgeId,
				payload.directoryId,
				{
					parent_id: targetDirectoryId
				}
			).catch((e) => {
				toast.error(`${e}`);
				return null;
			});

			if (res) {
				toast.success($i18n.t('Directory moved.'));
				// Both counters: the tree here has to redraw, and the screen's own
				// folder rows and breadcrumbs are just as stale.
				knowledgeDirectoryRevision.update((n) => n + 1);
				knowledgeDocumentRevision.update((n) => n + 1);
			}
		}
	};

	onMount(refresh);
</script>

<!-- Rendered unconditionally, not behind `loaded` or `directories.length > 0`:
     this row is the knowledge base's only entry point in the sidebar now, so it
     must be there on the first paint and on a base that has no folders yet. Only
     the chevron and the children wait for the fetch. -->
<div class="mt-0.5">
	<div class="px-[0.4375rem] flex justify-center text-gray-800 dark:text-gray-200">
		<!-- svelte-ignore a11y-no-static-element-interactions -->
		<div
			class="grow flex items-center rounded-2xl transition {rootDragOver
				? 'bg-gray-100 dark:bg-gray-800 ring-1 ring-gray-300 dark:ring-gray-600'
				: activeId === null && onKnowledgeScreen
					? 'bg-gray-100 dark:bg-gray-900'
					: 'hover:bg-gray-100 dark:hover:bg-gray-900'}"
			on:dragover={(e) => {
				if (!isKnowledgeDrag(e.dataTransfer)) return;
				e.preventDefault();
				e.stopPropagation();
				rootDragOver = true;
			}}
			on:dragleave={() => (rootDragOver = false)}
			on:drop={(e) => {
				e.preventDefault();
				e.stopPropagation();
				rootDragOver = false;

				// null target = out of every folder, back to the base's root. The
				// breadcrumb bar can do this too, but only while you are standing
				// inside a folder; this row is always there.
				const documentId = readDocumentDrag(e.dataTransfer);
				if (documentId) {
					handleDrop({ documentId }, null);
					return;
				}

				const directoryId = readDirectoryDrag(e.dataTransfer);
				if (directoryId) {
					handleDrop({ directoryId }, null);
				}
			}}
		>
			<button
				id="sidebar-knowledge-button"
				class="grow flex items-center space-x-3 min-w-0 px-2.5 py-2 text-left"
				type="button"
				on:click={() => openDirectory(null)}
			>
				<div class="self-center shrink-0">
					<BookOpen className="size-4.5" strokeWidth="1.5" />
				</div>
				<div class="flex flex-1 min-w-0 self-center translate-y-[0.5px]">
					<div class="self-center text-sm font-primary truncate">{$i18n.t('Knowledge Base')}</div>
				</div>
			</button>

			<!-- On the RIGHT, unlike every other row of the tree: keeping it there is
			     what lets the BookOpen icon sit on the same left edge as the menu
			     entries above, so the row still reads as one of them. The children
			     below carry the usual left-hand chevrons. -->
			{#if (childrenOf[''] ?? []).length > 0}
				<button
					class="p-1 mr-1.5 shrink-0 text-gray-400 dark:text-gray-600"
					type="button"
					aria-label={$i18n.t('Knowledge Base')}
					on:click|stopPropagation={() => (open = !open)}
				>
					<ChevronRight className="size-3 transition-transform {open ? 'rotate-90' : ''}" />
				</button>
			{/if}
		</div>
	</div>

	{#if open}
		<div class="px-2">
			{#each childrenOf[''] ?? [] as directory (directory.id)}
				<KnowledgeFolderNode
					{directory}
					{childrenOf}
					{expanded}
					{activeId}
					depth={0}
					onOpen={openDirectory}
					onToggle={toggle}
					onDrop={handleDrop}
				/>
			{/each}
		</div>
	{/if}
</div>
