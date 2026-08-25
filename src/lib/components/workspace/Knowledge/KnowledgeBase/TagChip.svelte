<script lang="ts">
	// One `#tag` chip. Renders the id, not the label — the id is the full path
	// («сварка/лучевая/лазерная») and that is what makes a chip self-explanatory
	// next to its siblings; the label («Лазерная») only makes sense in a list
	// grouped by heading, which is the picker's job.

	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import type { KnowledgeTag } from '$lib/apis/knowledge';

	export let tag: KnowledgeTag;
	export let active = false;
	export let onClick: ((tag: KnowledgeTag) => void) | null = null;
	export let onRemove: ((tag: KnowledgeTag) => void) | null = null;
</script>

<!--
	`adaptive: false` is what keeps the description next to the chip.

	Popper's computeStyles modifier defaults to `adaptive: true`, which switches
	between anchoring from `top` and from `bottom` depending on where the popper
	sits. Anchoring from `bottom` measures against the bottom edge of the popper's
	offsetParent — `<body>` — and on this screen `<body>` is shorter than the
	viewport (nothing in app.css gives html/body a height, so it is just content
	height). The tooltip then lands ~150px above the chip, near the top of the
	page. Forcing `top` anchoring removes the dependency on that edge; measured,
	the gap becomes exactly the 4px `offset`.

	Set here rather than in common/Tooltip.svelte: that file is upstream and would
	collide on the next sync. The same one-liner there would fix every tooltip on
	this screen, which are all affected the same way.
-->
<Tooltip
	content={tag.description || tag.label}
	tippyOptions={{
		popperOptions: { modifiers: [{ name: 'computeStyles', options: { adaptive: false } }] }
	}}
>
	<span
		class="inline-flex items-center gap-1 max-w-full rounded-md px-1.5 py-0.5 text-xs transition {active
			? 'bg-gray-800 text-white dark:bg-gray-100 dark:text-gray-900'
			: 'bg-gray-100 text-gray-600 dark:bg-gray-850 dark:text-gray-300'}"
	>
		{#if onClick}
			<button
				type="button"
				class="truncate"
				on:click|stopPropagation|preventDefault={() => onClick?.(tag)}
			>
				#{tag.id}
			</button>
		{:else}
			<span class="truncate">#{tag.id}</span>
		{/if}

		{#if onRemove}
			<button
				type="button"
				class="shrink-0 opacity-60 hover:opacity-100"
				aria-label="×"
				on:click|stopPropagation|preventDefault={() => onRemove?.(tag)}
			>
				×
			</button>
		{/if}
	</span>
</Tooltip>
