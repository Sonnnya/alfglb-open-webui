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
		approveVersion,
		getDocumentVersions,
		getKnowledgeDocuments,
		rejectVersion
	} from '$lib/apis/knowledge';

	import Pagination from '$lib/components/common/Pagination.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';
	import Badge from '$lib/components/common/Badge.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import DocumentPage from '$lib/components/icons/DocumentPage.svelte';

	// Typed rather than the bare getContext('i18n') used elsewhere: untyped, every
	// $i18n.t() call raises "Cannot use 'i18n' as a store" under svelte-check.
	const i18n = getContext<Writable<i18nType>>('i18n');

	export let knowledgeId: string;
	/** Whether the viewer may approve or reject — a Мастер-эксперт or an admin. */
	export let canReview = false;

	const PER_PAGE = 30;

	let documents: any[] = [];
	let total = 0;
	let page = 1;
	let query = '';
	let loading = true;

	// document_id -> versions, loaded lazily when «История» is expanded
	let expanded: Record<string, any[] | null> = {};

	let searchDebounce: ReturnType<typeof setTimeout>;

	const load = async () => {
		loading = true;
		const res = await getKnowledgeDocuments(localStorage.token, knowledgeId, {
			query: query || undefined,
			page
		}).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			documents = res.items ?? [];
			total = res.total ?? 0;
		}
		loading = false;
	};

	// Called by the parent after an upload or delete. The parent's own init()
	// only refreshes the legacy /files data, which by design cannot contain a
	// document that has no approved version — so without this the row a user
	// just uploaded would not appear until a full page reload.
	export const refresh = () => load();

	const onSearchInput = () => {
		clearTimeout(searchDebounce);
		searchDebounce = setTimeout(() => {
			page = 1;
			load();
		}, 300);
	};

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

	// document_id of the row whose review form is open, if any. Only one at a time
	// — reviewing is a deliberate act, not something to fan out across the list.
	let reviewingId: string | null = null;
	let reviewNote = '';
	let submitting = false;

	const openReview = (documentId: string) => {
		reviewingId = reviewingId === documentId ? null : documentId;
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
			delete expanded[documentId];
			await load();
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

	$: if (page) load();

	onMount(load);
</script>

<div class="flex flex-col w-full">
	<div class="flex items-center gap-2 px-1 pb-2">
		<div class="self-center text-gray-400">
			<Search className="size-3.5" />
		</div>
		<input
			class="w-full text-sm bg-transparent outline-hidden"
			bind:value={query}
			on:input={onSearchInput}
			placeholder={$i18n.t('Search')}
		/>
	</div>

	{#if loading}
		<div class="flex justify-center py-6"><Spinner className="size-5" /></div>
	{:else if documents.length === 0}
		<div class="py-6 text-center text-xs text-gray-500">{$i18n.t('No content found')}</div>
	{:else}
		<div class="flex flex-col w-full">
			{#each documents as doc (doc.document_id)}
				<div class="w-full border-b border-gray-50 dark:border-gray-850 py-2">
					<div class="flex items-center gap-2.5 w-full">
						<div class="text-gray-500 shrink-0">
							<DocumentPage className="size-4" />
						</div>

						<div class="flex-1 min-w-0">
							<div class="text-sm font-medium truncate">{doc.filename}</div>
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
								     approve/reject form. For everyone else it is just a label. -->
								<button
									type="button"
									class="cursor-pointer"
									title={$i18n.t('Approve')}
									on:click={() => openReview(doc.document_id)}
								>
									<Badge type={statusType(doc.status)} content={statusLabel(doc.status)} />
								</button>
							{:else}
								<Badge type={statusType(doc.status)} content={statusLabel(doc.status)} />
							{/if}

							<a
								class="text-xs underline"
								href={`${WEBUI_API_BASE_URL}/files/${doc.file_id}/content`}
								target="_blank"
								rel="noopener noreferrer">{$i18n.t('Download')}</a
							>

							<button
								type="button"
								class="text-xs underline"
								on:click={() => toggleHistory(doc.document_id)}>{$i18n.t('History')}</button
							>
						</div>
					</div>

					{#if reviewingId === doc.document_id}
						<div class="mt-2 ml-7 flex flex-col gap-2 rounded-lg bg-gray-50 dark:bg-gray-850 p-2.5">
							<input
								class="w-full text-xs bg-transparent outline-hidden"
								bind:value={reviewNote}
								placeholder={$i18n.t('Reason (optional)')}
							/>
							<div class="flex gap-2">
								<button
									type="button"
									class="px-2.5 py-1 rounded-lg text-xs font-medium bg-green-600 hover:bg-green-700 text-white disabled:opacity-50"
									disabled={submitting}
									on:click={() => review(doc.document_id, doc.version_id ?? '', true)}
									>{$i18n.t('Approve')}</button
								>
								<button
									type="button"
									class="px-2.5 py-1 rounded-lg text-xs font-medium bg-red-600 hover:bg-red-700 text-white disabled:opacity-50"
									disabled={submitting}
									on:click={() => review(doc.document_id, doc.version_id ?? '', false)}
									>{$i18n.t('Reject')}</button
								>
								<button
									type="button"
									class="px-2.5 py-1 rounded-lg text-xs"
									on:click={() => (reviewingId = null)}>{$i18n.t('Cancel')}</button
								>
							</div>
						</div>
					{/if}

					{#if expanded[doc.document_id] !== undefined}
						<div class="pl-7 pt-2">
							{#if expanded[doc.document_id] === null}
								<Spinner className="size-4" />
							{:else}
								{#each expanded[doc.document_id] ?? [] as version (version.id)}
									<div class="flex gap-2 text-xs text-gray-500 py-0.5">
										<span class="w-8 shrink-0">v{version.version_no}</span>
										<span class="w-24 shrink-0"
											>{dayjs(version.created_at * 1000).format('DD.MM.YYYY')}</span
										>
										<span class="truncate">
											{version.comment ?? ''}{#if version.review_note}
												— {version.review_note}{/if}
										</span>
									</div>
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
