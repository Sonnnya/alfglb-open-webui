<script lang="ts">
	// Flat, paginated document registry — the «Реестр документов» of the design.
	//
	// Reads /knowledge/{id}/documents, not /files: the registry shows each
	// document's LATEST revision including ones still awaiting review, whereas
	// /files answers "what is published" and is what the model's search tool uses.
	// A row can therefore read «Ждет проверки» while the model still serves the
	// previously approved revision — that is intended, not a bug.

	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	import dayjs from '$lib/dayjs';
	import relativeTime from 'dayjs/plugin/relativeTime';
	dayjs.extend(relativeTime);

	import { WEBUI_API_BASE_URL } from '$lib/constants';
	import {
		addFileToKnowledgeById,
		approveVersion,
		deleteKnowledgeDocument,
		deleteKnowledgeVersion,
		getDocumentVersions,
		getKnowledgeDocuments,
		rejectVersion
	} from '$lib/apis/knowledge';
	import { uploadFile } from '$lib/apis/files';
	import { knowledgeDirectoryRevision, user } from '$lib/stores';

	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import VersionReviewForm from './VersionReviewForm.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import DocumentPage from '$lib/components/icons/DocumentPage.svelte';
	import DirectoryRow from './DirectoryRow.svelte';
	import DocumentMenu from './DocumentMenu.svelte';
	import MoveDocumentModal from './MoveDocumentModal.svelte';
	import { setDocumentDrag } from '$lib/utils/knowledge-dnd';

	// Typed rather than the bare getContext('i18n') used elsewhere: untyped, every
	// $i18n.t() call raises "Cannot use 'i18n' as a store" under svelte-check.
	const i18n = getContext<Writable<i18nType>>('i18n');

	export let knowledgeId: string;
	/** Whether the viewer may approve or reject — a Мастер-эксперт or an admin. */
	export let canReview = false;
	/** Whether the viewer may propose a new version — anyone with write access. */
	export let canUpload = false;
	/**
	 * Files the SERVER reports as still processing, rendered above the list with a
	 * spinner. Not the parent's own picks — those are announced by its progress
	 * banner, and drawing them here too meant the same upload appeared twice.
	 * These are the ones nothing else accounts for: an upload whose page was
	 * reloaded, another session's, or an orphan left by a worker that died.
	 */
	export let uploading: any[] = [];
	/**
	 * The parent is uploading right now. Only suppresses the «нет содержимого»
	 * empty state: uploading the first file into an empty folder would otherwise
	 * render «ничего нет» directly under a banner naming the file being added.
	 */
	export let busy = false;
	/**
	 * Search text, owned by the parent's toolbar.
	 *
	 * The registry used to carry its own input, which left two search boxes on
	 * one screen — the collection search above (meaningless with a single
	 * knowledge base) and this one. The parent's box now drives this instead.
	 */
	export let query = '';
	/**
	 * The folder being shown. `null` means the root level; the registry is then a
	 * file manager rather than a flat list.
	 *
	 * A search overrides it — see load(): people searching want hits from the whole
	 * base, not from the folder they happen to be standing in, so a non-empty query
	 * drops the scoping and the folder rows with it.
	 */
	export let directoryId: string | null = null;
	/** Whether the viewer may create, rename, move or delete folders. */
	export let writeAccess = false;

	export let onNavigate: (directoryId: string | null) => void = () => {};
	export let onRenameDirectory: (directoryId: string, name: string) => void = () => {};
	export let onDeleteDirectory: (directoryId: string) => void = () => {};
	export let onMoveDirectory: (directoryId: string, targetId: string | null) => void = () => {};
	export let onMoveDocument: (documentId: string, targetId: string | null) => void = () => {};
	/**
	 * Reports the folder path back to the parent, which draws the breadcrumbs above
	 * this component. Sent from here because /documents is what actually knows it —
	 * the parent's legacy /files call also returns a path, but it is fetched on a
	 * different trigger and would drift on a search, where scoping is dropped.
	 */
	export let onTree: (breadcrumbs: any[]) => void = () => {};
	/**
	 * How many documents the whole base holds — every folder, every status.
	 *
	 * Reported from here for the same reason the breadcrumbs are: /documents is
	 * what knows it. Deliberately NOT `total`, which is what this listing pages
	 * through and so shrinks to the open folder or to the search hits. The header
	 * count above the list wants the invariant number.
	 */
	export let onTotal: (totalAll: number) => void = () => {};

	// Must match DOCUMENT_REGISTRY_PAGE_COUNT in backend/open_webui/routers/knowledge.py —
	// the server decides how many rows come back, this only decides whether to draw
	// the pager, so a mismatch hides it while pages still exist.
	const PER_PAGE = 10;

	let documents: any[] = [];
	let directories: any[] = [];
	let total = 0;
	let page = 1;
	let loading = true;

	// document_id -> versions, loaded lazily when «История» is expanded
	let expanded: Record<string, any[] | null> = {};

	let searchDebounce: ReturnType<typeof setTimeout>;

	const load = async () => {
		loading = true;
		// directoryId is sent as '' for the root — the API distinguishes "omitted"
		// (flat across every folder) from "explicitly root". A search deliberately
		// omits it so results span the whole base.
		const searching = (query ?? '').trim().length > 0;
		const res = await getKnowledgeDocuments(localStorage.token, knowledgeId, {
			query: query || undefined,
			directoryId: searching ? undefined : (directoryId ?? ''),
			page
		}).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			documents = res.items ?? [];
			// Folders come back only in folder mode AND only on page 1, so a search
			// empties this by itself and the list reads as a flat result set.
			directories = res.directories ?? [];
			total = res.total ?? 0;
			// Empty while searching, which is what clears the breadcrumb — showing
			// «База знаний / ГОСТы» above results gathered from the whole base
			// would be a straightforward lie about what is on screen.
			onTree(res.breadcrumbs ?? []);
			onTotal(res.total_all ?? 0);
		}
		loading = false;
	};

	// Called by the parent after an upload or delete. The parent's own init()
	// only refreshes the legacy /files data, which by design cannot contain a
	// document that has no approved version — so without this the row a user
	// just uploaded would not appear until a full page reload.
	export const refresh = () => load();

	// Every mutation this component performs changes a review count, and the
	// sidebar tree draws its dots from those. It is a different component tree with
	// no props between us, so the revision counter is the only channel — the same
	// one folder mutations already use, because «the tree is stale» is one fact.
	// Approving is the case that matters most: the reviewer works down the yellow
	// dots, and a dot that does not clear as they go is worse than no dot at all.
	//
	// Deliberately NOT knowledgeDocumentRevision: the parent watches that one and
	// would refetch the legacy /files list and re-run load() on top of the load()
	// each of these has already done.
	const notifyTree = () => knowledgeDirectoryRevision.update((n) => n + 1);

	// Debounced here rather than in the parent: the parent's handler also refetches
	// the legacy /files list, and the two want different timing.
	let appliedDirectoryId = directoryId;
	$: if (directoryId !== appliedDirectoryId) {
		appliedDirectoryId = directoryId;
		if (page !== 1) {
			page = 1;
		} else {
			load();
		}
	}

	let appliedQuery = query;
	$: if (query !== appliedQuery) {
		appliedQuery = query;
		clearTimeout(searchDebounce);
		searchDebounce = setTimeout(() => {
			// Assigning page triggers the reactive load below; when already on the
			// first page that assignment is a no-op, so load explicitly.
			if (page !== 1) {
				page = 1;
			} else {
				load();
			}
		}, 300);
	}

	const toggleHistory = async (documentId: string) => {
		if (expanded[documentId] !== undefined) {
			delete expanded[documentId];
			expanded = expanded;
			return;
		}

		expanded = { ...expanded, [documentId]: null };
		const versions = await getDocumentVersions(localStorage.token, knowledgeId, documentId).catch(
			(e) => {
				toast.error(`${e}`);
				return [];
			}
		);
		expanded = { ...expanded, [documentId]: versions ?? [] };
	};

	// ── New version upload ────────────────────────────────────────────────
	//
	// Deliberately a two-step flow rather than the parent's single uploadFile()
	// with metadata.knowledge_id: that metadata makes routers/files.py auto-link
	// the file as a *new* document. A version has to name the document it belongs
	// to, which only POST /knowledge/{id}/file/add accepts.
	//
	// uploadFile() with its default stream=true returns only once the file's
	// process status is completed or failed, so /file/add — which rejects an
	// unprocessed file — is safe to call straight after.
	let versionInput: HTMLInputElement;
	let versionTargetId: string | null = null;
	let uploadingId: string | null = null;

	const pickNewVersion = (documentId: string) => {
		versionTargetId = documentId;
		versionInput.value = '';
		versionInput.click();
	};

	const onVersionPicked = async (e: Event) => {
		const file = (e.target as HTMLInputElement).files?.[0];
		const documentId = versionTargetId;
		versionTargetId = null;
		if (!file || !documentId) return;

		if (file.size === 0) {
			toast.error($i18n.t('You cannot upload an empty file.'));
			return;
		}

		uploadingId = documentId;
		try {
			const uploaded = await uploadFile(localStorage.token, file);
			if (!uploaded) {
				toast.error($i18n.t('Failed to upload file.'));
				return;
			}
			if (uploaded.error) {
				toast.error(`${uploaded.error}`);
				return;
			}

			await addFileToKnowledgeById(localStorage.token, knowledgeId, uploaded.id, null, {
				documentId
			});

			toast.success($i18n.t('Pending review'));
			delete expanded[documentId];
			await load();
			notifyTree();
		} catch (err) {
			toast.error(`${err}`);
		} finally {
			uploadingId = null;
		}
	};

	// ── Move ──────────────────────────────────────────────────────────────
	//
	// The same onMoveDocument the drag-and-drop path calls — the dialog only picks
	// the destination differently. Kept whole here rather than in the parent so the
	// row that opened it is the row that gets moved.
	let movingDocument: { id: string; name: string; directoryId: string | null } | null = null;
	let showMoveModal = false;

	const openMove = (doc: any) => {
		movingDocument = {
			id: doc.document_id,
			name: doc.filename,
			directoryId: doc.directory_id ?? null
		};
		showMoveModal = true;
	};

	// ── Delete ────────────────────────────────────────────────────────────
	//
	// Deleting takes the document's whole version history with it, so the right
	// to do it follows the document's OWNER (owner_id), not the latest version's
	// author — those diverge as soon as someone proposes a version on another
	// person's document. A Мастер-эксперт may delete anyone's; the backend
	// enforces the same rule, this only decides whether to draw the button.
	let confirmDeleteId: string | null = null;
	let deleting = false;

	const mayDelete = (doc: any) => canReview || doc.owner_id === $user?.id;

	const confirmDelete = async () => {
		const documentId = confirmDeleteId;
		if (!documentId || deleting) return;

		deleting = true;
		const res = await deleteKnowledgeDocument(localStorage.token, knowledgeId, documentId).catch(
			(e) => {
				toast.error(`${e}`);
				return null;
			}
		);
		deleting = false;
		confirmDeleteId = null;

		if (res) {
			toast.success($i18n.t('Deleted'));
			delete expanded[documentId];
			// Deleting the last row of a page would otherwise leave an empty view.
			if (documents.length === 1 && page > 1) {
				page -= 1;
			} else {
				await load();
			}
			notifyTree();
		}
	};

	// ── Per-version delete ────────────────────────────────────────────────
	//
	// Narrower than the document delete above, and keyed on a different person:
	// this is an Эксперт withdrawing a version *they* authored, so the rule is
	// author_id, not owner_id. Reviewers may remove anyone's. The backend refuses
	// the published version outright — the button isn't drawn for it either.
	let confirmVersion: { documentId: string; version: any } | null = null;
	let deletingVersion = false;

	// version.is_published comes from the backend, which compares the version's
	// file against the document's published one. The row-level doc.is_published
	// cannot answer this: it describes only the latest version, so with an
	// approved v1 and a pending v2 it is false for both.
	// The published version can only go when it is the *only* one — then the whole
	// document goes with it and nothing is left pointing at a missing file. The
	// backend applies the same rule; this just avoids drawing a button that 400s.
	const mayDeleteVersion = (version: any, versions: any[]) =>
		(!version.is_published || versions.length <= 1) &&
		(canReview || version.author_id === $user?.id);

	const confirmVersionDelete = async () => {
		const target = confirmVersion;
		if (!target || deletingVersion) return;

		deletingVersion = true;
		const res = await deleteKnowledgeVersion(
			localStorage.token,
			knowledgeId,
			target.version.id
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});
		deletingVersion = false;
		confirmVersion = null;

		if (res) {
			toast.success($i18n.t('Deleted'));
			delete expanded[target.documentId];
			// Removing the last version removes the document, so the row itself is
			// gone — a plain history reload would render an empty panel under a row
			// that no longer exists.
			await load();
			notifyTree();
		}
	};

	// version_id of the version whose review form is open, if any. Only one at a
	// time — reviewing is a deliberate act, not something to fan out across the
	// list.
	//
	// Keyed on the VERSION, not the document: the registry row only ever shows the
	// latest revision, so once a v3 is uploaded a v2 still awaiting review becomes
	// unreachable from it. The same badge in «История» opens this form for any
	// pending revision, and the backend approves whichever version_id it is given
	// regardless of newer ones existing.
	let reviewingId: string | null = null;
	let reviewNote = '';
	let submitting = false;
	// Which outcome the reviewer reached for, so the form can emphasise it. Not a
	// decision — the form still offers both, and nothing is submitted until one of
	// its buttons is pressed.
	let reviewIntent: 'approve' | 'reject' = 'approve';

	const openReview = (versionId: string, intent: 'approve' | 'reject' = 'approve') => {
		// Re-opening with the OTHER intent should switch the emphasis rather than
		// close the form: picking «Отклонить версию» while the approve form is open
		// is a change of mind, not a request to dismiss it.
		reviewingId = reviewingId === versionId && reviewIntent === intent ? null : versionId;
		reviewIntent = intent;
		reviewNote = '';
	};

	const review = async (documentId: string, versionId: string, approve: boolean) => {
		if (!versionId || submitting) return;
		submitting = true;

		const action = approve ? approveVersion : rejectVersion;
		const res = await action(localStorage.token, knowledgeId, versionId, reviewNote || null).catch(
			(e) => {
				toast.error(`${e}`);
				return null;
			}
		);
		submitting = false;

		if (res) {
			toast.success(approve ? $i18n.t('Approved') : $i18n.t('Rejected'));
			reviewingId = null;
			reviewNote = '';
			// Reload rather than patch in place: approving republishes the document,
			// which changes is_published on the row and what the model can retrieve.
			const wasExpanded = expanded[documentId] !== undefined;
			delete expanded[documentId];
			expanded = expanded;
			await load();
			notifyTree();
			// Reviewing from «История» should leave «История» open, showing the
			// verdict that was just recorded — toggleHistory refetches it.
			if (wasExpanded) {
				await toggleHistory(documentId);
			}
		}
	};

	// Status drives the badge colour and label. Literal t() calls, because
	// i18next-parser only sees literals and drops any key it cannot find.
	const statusLabel = (status: string) =>
		status === 'approved'
			? $i18n.t('Approved')
			: status === 'rejected'
				? $i18n.t('Rejected')
				: $i18n.t('Pending review');

	const statusType = (status: string) =>
		status === 'approved' ? 'success' : status === 'rejected' ? 'error' : 'warning';

	// «Скачать» in the ⋮ menu. The per-version route rather than /files/{id}/content
	// for two reasons: it sends Content-Disposition: attachment, which is what the
	// item promises, and it authorises on the KNOWLEDGE BASE — a revision still
	// awaiting review has no knowledge_file row, so has_access_to_file cannot
	// resolve it and the file route 404s for everyone but the uploader (see the
	// docstring on download_version in routers/knowledge.py).
	//
	// The filename link above deliberately does NOT use this: it opens the document
	// in a tab, and an attachment response would flash a tab open and hand back a
	// download instead. Legacy documents predate versioning and have no version
	// row, so they fall back to the file route.
	const downloadHref = (doc: any) =>
		doc.version_id
			? `${WEBUI_API_BASE_URL}/knowledge/${knowledgeId}/version/${doc.version_id}/download`
			: doc.file_id
				? `${WEBUI_API_BASE_URL}/files/${doc.file_id}/content`
				: null;

	$: if (page) load();

	onMount(load);
</script>

<ConfirmDialog
	show={confirmDeleteId !== null}
	message={$i18n.t(
		'This action cannot be undone. The document and its entire version history will be removed from the knowledge base.'
	)}
	confirmLabel={$i18n.t('Delete')}
	on:confirm={confirmDelete}
	on:cancel={() => (confirmDeleteId = null)}
/>

<ConfirmDialog
	show={confirmVersion !== null}
	message={(expanded[confirmVersion?.documentId ?? '']?.length ?? 0) <= 1
		? $i18n.t(
				'This is the only revision, so the document will be removed from the knowledge base as well. This action cannot be undone.'
			)
		: $i18n.t('This action cannot be undone. This revision will be removed from the history.')}
	confirmLabel={$i18n.t('Delete')}
	on:confirm={confirmVersionDelete}
	on:cancel={() => (confirmVersion = null)}
/>

{#if movingDocument}
	<MoveDocumentModal
		bind:show={showMoveModal}
		{knowledgeId}
		documentName={movingDocument.name}
		currentDirectoryId={movingDocument.directoryId}
		onMove={(targetId) => onMoveDocument(movingDocument?.id ?? '', targetId)}
	/>
{/if}

<input
	bind:this={versionInput}
	type="file"
	class="hidden"
	on:change={onVersionPicked}
	aria-label={$i18n.t('Upload new version')}
/>

<div class="flex flex-col w-full">
	<!-- Uploads in flight, above the list and outside the loading branch: a refresh
	     triggered by the upload itself would otherwise blank them out at exactly the
	     moment the user needs to see progress. -->
	{#each uploading as item (item.itemId ?? item.id ?? item.name)}
		<div class="w-full border-b border-gray-50 dark:border-gray-850 py-2">
			<div class="flex items-center gap-2.5 w-full">
				<div class="shrink-0 text-gray-500"><Spinner className="size-4" /></div>
				<div class="flex-1 min-w-0">
					<div class="text-sm font-medium truncate text-gray-500">
						{item.name ?? item.filename ?? ''}
					</div>
					<div class="text-xs text-gray-400">{$i18n.t('Uploading...')}</div>
				</div>
			</div>
		</div>
	{/each}

	{#if loading}
		<div class="flex justify-center py-6"><Spinner className="size-5" /></div>
	{:else if documents.length === 0 && directories.length === 0 && uploading.length === 0 && !busy}
		<div class="py-6 text-center text-xs text-gray-500">{$i18n.t('No content found')}</div>
	{:else}
		<div class="flex flex-col w-full">
			<!-- Folders first, and deliberately OUTSIDE the pager: a level holds a
			     handful of them, and paging them alongside documents would put
			     subfolders on page 2 where nobody looks for them. `total` counts
			     documents only, which is what the server paginates. -->
			{#each directories as directory (directory.id)}
				<!-- py-2, matching the document rows below: py-1 made folder rows
				     visibly shorter than the files under them. -->
				<div class="w-full border-b border-gray-50 dark:border-gray-850 py-2">
					<DirectoryRow
						{directory}
						{writeAccess}
						scopedToViewer={!canReview}
						onNavigate={(dirId) => onNavigate(dirId)}
						onRename={(dirId, name) => onRenameDirectory(dirId, name)}
						onDelete={(dirId) => onDeleteDirectory(dirId)}
						onFileDrop={(documentId, dirId) => onMoveDocument(documentId, dirId)}
						onDirDrop={(dirId, targetId) => onMoveDirectory(dirId, targetId)}
					/>
				</div>
			{/each}

			{#each documents as doc (doc.document_id)}
				<div
					class="w-full border-b border-gray-50 dark:border-gray-850 py-2"
					draggable={writeAccess}
					on:dragstart={(e) => {
						if (!writeAccess) return;
						// A DOCUMENT id, not a file id — see knowledge-dnd.ts. Every drop
						// target reads it through the same helper, so folder rows,
						// breadcrumbs and the sidebar tree all accept this identically.
						setDocumentDrag(e.dataTransfer, doc.document_id);
					}}
				>
					<!-- The header line toggles «История». Only this line, not the whole
					     row: the expanded panel and the review form are siblings below it,
					     and a click anywhere in them would otherwise fold the thing the
					     user just opened.

					     Guarded by closest() rather than stopPropagation on each control,
					     so a control added later cannot silently start collapsing rows.
					     The filename link, the status badge and the ⋮ menu all keep their
					     own behaviour. Keyboard users reach the same thing through
					     «История» in the ⋮ menu, which is why this needs no key handler. -->
					<!-- svelte-ignore a11y-click-events-have-key-events a11y-no-static-element-interactions -->
					<div
						class="flex items-center gap-2.5 w-full cursor-pointer rounded-xl hover:bg-gray-50 dark:hover:bg-gray-850/50 transition"
						on:click={(e) => {
							if ((e.target as HTMLElement)?.closest('a, button, input')) return;
							toggleHistory(doc.document_id);
						}}
					>
						<div class="text-gray-500 shrink-0">
							<DocumentPage className="size-4" />
						</div>

						<div class="flex-1 min-w-0">
							<!-- OPENS the document in a tab — clicking a name is what people try
							     first, and this is unchanged. Deliberately not downloadHref():
							     that is the ⋮ menu's «Скачать», which responds with an
							     attachment and would turn one click into a flashed-open tab plus
							     a file on disk. -->
							<!-- inline-block, not block: `block` stretched the anchor across the
							     whole remaining width of the row, so clicking the empty space
							     beside a short filename hit the link. That is invisible until the
							     row itself became clickable — then most of the row silently
							     refused to toggle the history. max-w-full keeps truncate working. -->
							<a
								class="inline-block max-w-full text-sm font-medium truncate hover:underline"
								href={`${WEBUI_API_BASE_URL}/files/${doc.file_id}/content`}
								target="_blank"
								rel="noopener noreferrer"
								title={doc.filename}>{doc.filename}</a
							>
							<div class="text-xs text-gray-500 truncate">
								{dayjs(doc.updated_at * 1000).fromNow()}
								{#if doc.author?.name}· {doc.author.name}{/if}
								{#if doc.comment}· {doc.comment}{/if}
							</div>
						</div>

						<div class="flex items-center gap-1.5 shrink-0">
							<Badge type="muted" content={`v${doc.version_no}`} />

							{#if canReview && doc.status === 'pending' && doc.version_id}
								<!-- For a reviewer the status is the control: it opens the
								     approve/reject form. For everyone else it is just a label.
								     The ⋮ menu's «Одобрить версию» / «Отклонить версию» open the
								     same form — the badge is not obviously clickable until you
								     have tried it once. Its tooltip names neither outcome,
								     because it offers both. -->
								<button
									type="button"
									class="cursor-pointer"
									title={$i18n.t('Review version')}
									on:click={() => openReview(doc.version_id)}
								>
									<Badge type={statusType(doc.status)} content={statusLabel(doc.status)} />
								</button>
							{:else}
								<Badge type={statusType(doc.status)} content={statusLabel(doc.status)} />
							{/if}

							<!-- The «Загрузить новую версию» button used to carry its own
							     «Загружается...» label; inside a closed menu that feedback is
							     invisible, so the row shows a spinner where the controls are. -->
							{#if uploadingId === doc.document_id}
								<Spinner className="size-3.5" />
							{/if}

							<DocumentMenu
								downloadHref={downloadHref(doc)}
								canReview={canReview && doc.status === 'pending' && !!doc.version_id}
								{canUpload}
								canDelete={mayDelete(doc)}
								uploading={uploadingId !== null}
								{deleting}
								onApprove={() => openReview(doc.version_id, 'approve')}
								onReject={() => openReview(doc.version_id, 'reject')}
								canMove={writeAccess}
								onUploadVersion={() => pickNewVersion(doc.document_id)}
								onMove={() => openMove(doc)}
								onHistory={() => toggleHistory(doc.document_id)}
								onDelete={() => (confirmDeleteId = doc.document_id)}
							/>
						</div>
					</div>

					{#if reviewingId === doc.version_id}
						<div class="ml-7">
							<VersionReviewForm
								bind:note={reviewNote}
								{submitting}
								intent={reviewIntent}
								onApprove={() => review(doc.document_id, doc.version_id ?? '', true)}
								onReject={() => review(doc.document_id, doc.version_id ?? '', false)}
								onCancel={() => (reviewingId = null)}
							/>
						</div>
					{/if}

					{#if expanded[doc.document_id] !== undefined}
						<div class="pl-7 pt-2">
							{#if expanded[doc.document_id] === null}
								<Spinner className="size-4" />
							{:else}
								{#each expanded[doc.document_id] ?? [] as version (version.id)}
									<!-- Each revision carries its own verdict: without it a reader
									     cannot tell whether the version a pending one supersedes was
									     approved or rejected. `comment` is the author's changelog,
									     `review_note` the reviewer's — different people, shown apart. -->
									<div class="flex gap-2 text-xs text-gray-500 py-1 items-baseline">
										<span class="w-8 shrink-0">v{version.version_no}</span>
										<span class="w-32 shrink-0"
											>{dayjs(version.created_at * 1000).format('DD.MM.YYYY HH:mm')}</span
										>
										<span class="shrink-0">
											{#if canReview && version.status === 'pending' && version.id !== doc.version_id}
												<!-- The registry row above only ever shows the LATEST
												     revision, so a v2 still awaiting review becomes
												     unreachable the moment a v3 is uploaded. This badge is
												     the way back to it — approving here publishes v2 even
												     though a newer pending revision exists.
												
												     Skipped for the row's own version: reviewingId is a
												     version id, so that one would match both this form and
												     the row's, rendering the controls twice. Explicit
												     inequality, not a truthiness test — doc.version_id is
												     null for a legacy document with no version row, and
												     those badges should stay clickable. -->
												<button
													type="button"
													class="cursor-pointer"
													title={$i18n.t('Review version')}
													on:click={() => openReview(version.id)}
												>
													<Badge
														type={statusType(version.status)}
														content={statusLabel(version.status)}
													/>
												</button>
											{:else}
												<Badge
													type={statusType(version.status)}
													content={statusLabel(version.status)}
												/>
											{/if}
										</span>

										<!-- The file as uploaded for THIS revision. Versions of one
										     document routinely carry different filenames, and the
										     registry row above can only show the latest. `filename` is
										     null when the underlying file row is gone; the row still
										     renders, just without a download. -->
										{#if version.filename}
											<a
												class="w-40 shrink-0 truncate hover:underline"
												href={`${WEBUI_API_BASE_URL}/knowledge/${knowledgeId}/version/${version.id}/download`}
												target="_blank"
												rel="noopener noreferrer"
												title={version.filename}>{version.filename}</a
											>
											<a
												class="shrink-0 underline"
												href={`${WEBUI_API_BASE_URL}/knowledge/${knowledgeId}/version/${version.id}/download`}
												target="_blank"
												rel="noopener noreferrer">{$i18n.t('Download')}</a
											>
										{/if}

										{#if mayDeleteVersion(version, expanded[doc.document_id] ?? [])}
											<button
												type="button"
												class="shrink-0 underline text-red-600 dark:text-red-500 disabled:opacity-50"
												disabled={deletingVersion}
												on:click={() => (confirmVersion = { documentId: doc.document_id, version })}
												>{$i18n.t('Delete')}</button
											>
										{/if}

										<span class="min-w-0 truncate">
											{#if version.author?.name}{version.author.name}{/if}{#if version.comment}
												— {version.comment}{/if}
											{#if version.review_note || version.reviewer?.name}
												<span class="text-gray-400">
													·
													{#if version.reviewer?.name}{$i18n.t('Reviewed by')}: {version.reviewer
															.name}{/if}{#if version.review_note}
														— {version.review_note}{/if}
												</span>
											{/if}
										</span>
									</div>

									{#if reviewingId === version.id && version.id !== doc.version_id}
										<div class="pb-2 pr-2">
											<VersionReviewForm
												bind:note={reviewNote}
												{submitting}
												intent={reviewIntent}
												onApprove={() => review(doc.document_id, version.id, true)}
												onReject={() => review(doc.document_id, version.id, false)}
												onCancel={() => (reviewingId = null)}
											/>
										</div>
									{/if}
								{/each}
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>

		{#if total > PER_PAGE}
			<Pagination bind:page count={total} perPage={PER_PAGE} />
		{/if}
	{/if}
</div>
