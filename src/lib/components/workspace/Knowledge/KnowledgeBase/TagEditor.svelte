<script lang="ts">
	// The tag editor for one document: a filter box over the vocabulary, grouped
	// by the headings the taxonomy defines, with the document's current tags
	// shown as removable chips.
	//
	// The vocabulary is CLOSED to ordinary write access — an Эксперт picks from
	// the list and cannot invent a tag, because near-duplicates («гост» beside
	// «ГОСТ») quietly split the corpus in two. Мастер-эксперт and admins get the
	// «создать» affordance at the bottom of an empty search.

	import { getContext, onMount } from 'svelte';
	import { toast } from 'svelte-sonner';
	import type { i18n as i18nType } from 'i18next';
	import type { Writable } from 'svelte/store';

	import type { KnowledgeTag } from '$lib/apis/knowledge';
	import { createKnowledgeTag, getKnowledgeTags } from '$lib/apis/knowledge';

	import TagChip from './TagChip.svelte';
	import Spinner from '$lib/components/common/Spinner.svelte';

	const i18n = getContext<Writable<i18nType>>('i18n');

	export let selected: KnowledgeTag[] = [];
	export let canCurate = false;
	export let onSave: (tagIds: string[]) => Promise<void> | void = () => {};
	export let onClose: () => void = () => {};

	let vocabulary: KnowledgeTag[] = [];
	let loading = true;
	let saving = false;
	let query = '';

	// Working copy: nothing is written until «Сохранить», so escaping out of a
	// half-made change leaves the document alone.
	let chosen = new Set(selected.map((tag) => tag.id));
	$: chosenList = vocabulary.filter((tag) => chosen.has(tag.id));

	$: normalizedQuery = query.trim().toLowerCase();
	// Aliases are searched too — «аргон» has to find #рад, «пенетрант» #пвк. They
	// are the registry's «Синонимы и алиасы (для ИИ)» column, and the id alone is
	// an acronym an expert may not have in mind while typing. `deprecated` is
	// deliberately NOT searched: those are wordings the registry rejects, and
	// surfacing them here would teach people to keep using them.
	$: matches = normalizedQuery
		? vocabulary.filter(
				(tag) =>
					tag.id.includes(normalizedQuery) ||
					tag.label.toLowerCase().includes(normalizedQuery) ||
					(tag.description ?? '').toLowerCase().includes(normalizedQuery) ||
					(tag.meta?.aliases ?? []).some((alias) => alias.toLowerCase().includes(normalizedQuery))
			)
		: vocabulary;

	// group heading -> tags. Tags keep the order the API returned them in (by id,
	// so a branch stays together); the headings are ordered by `meta.group_order`,
	// which the seeded registry stamps on every tag. Without it the sections come
	// out in whatever order the alphabetically-first tag put them — «Объекты
	// применения» above «Технологии», which is not how the registry reads.
	// A tag minted through the UI carries no meta at all, so it sorts last under
	// «Другие».
	$: grouped = Object.values(
		matches.reduce<Record<string, { group: string; order: number; tags: KnowledgeTag[] }>>(
			(acc, tag) => {
				const group = tag.meta?.group ?? $i18n.t('Other');
				const order = tag.meta?.group_order ?? Number.MAX_SAFE_INTEGER;
				(acc[group] ||= { group, order, tags: [] }).tags.push(tag);
				return acc;
			},
			{}
		)
	).sort((a, b) => a.order - b.order || a.group.localeCompare(b.group));

	const toggle = (tag: KnowledgeTag) => {
		if (chosen.has(tag.id)) {
			chosen.delete(tag.id);
		} else {
			chosen.add(tag.id);
		}
		chosen = chosen;
	};

	const createAndSelect = async () => {
		const label = query.trim();
		if (!label) return;
		try {
			const tag = await createKnowledgeTag(localStorage.token, { label });
			vocabulary = [...vocabulary, tag].sort((a, b) => a.id.localeCompare(b.id));
			chosen.add(tag.id);
			chosen = chosen;
			query = '';
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	const save = async () => {
		saving = true;
		try {
			await onSave([...chosen]);
			onClose();
		} finally {
			saving = false;
		}
	};

	onMount(async () => {
		try {
			vocabulary = await getKnowledgeTags(localStorage.token);
		} catch (e) {
			toast.error(`${e}`);
		}
		loading = false;
	});
</script>

<div class="mt-2 rounded-xl border border-gray-100 dark:border-gray-850 p-3">
	{#if loading}
		<div class="flex justify-center py-4"><Spinner className="size-4" /></div>
	{:else}
		{#if chosenList.length > 0}
			<div class="flex flex-wrap gap-1 mb-2">
				{#each chosenList as tag (tag.id)}
					<TagChip {tag} active onRemove={toggle} />
				{/each}
			</div>
		{/if}

		<input
			bind:value={query}
			class="w-full text-sm bg-transparent outline-hidden border-b border-gray-100 dark:border-gray-850 pb-1 mb-2"
			placeholder={$i18n.t('Search tags')}
		/>

		<div class="max-h-64 overflow-y-auto">
			{#each grouped as { group, tags } (group)}
				<div class="mb-2">
					<div class="text-xs text-gray-400 mb-1">{group}</div>
					<div class="flex flex-wrap gap-1">
						{#each tags as tag (tag.id)}
							<TagChip {tag} active={chosen.has(tag.id)} onClick={toggle} />
						{/each}
					</div>
				</div>
			{:else}
				<div class="text-xs text-gray-400 py-2">
					{$i18n.t('No tags found')}
				</div>
			{/each}
		</div>

		<div class="flex items-center justify-between mt-3">
			<div>
				{#if canCurate && normalizedQuery && matches.length === 0}
					<button
						type="button"
						class="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 transition"
						on:click={createAndSelect}
					>
						{$i18n.t('Create tag')} «{query.trim()}»
					</button>
				{/if}
			</div>

			<div class="flex gap-1.5">
				<button
					type="button"
					class="px-3 py-1 text-xs rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition"
					on:click={onClose}
				>
					{$i18n.t('Cancel')}
				</button>
				<button
					type="button"
					class="px-3 py-1 text-xs rounded-lg bg-black text-white dark:bg-white dark:text-black transition disabled:opacity-50"
					disabled={saving}
					on:click={save}
				>
					{$i18n.t('Save')}
				</button>
			</div>
		</div>
	{/if}
</div>
