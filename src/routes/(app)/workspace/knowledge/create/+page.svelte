<script>
	// This deployment has exactly one knowledge base («База знаний по сварке»), so
	// the create-a-collection screen is dead weight: every entry point links straight to
	// WELDING_KB_HREF. The component below is deliberately LEFT IN PLACE and still
	// compiles — nothing about multi-collection support was deleted — but the route
	// bounces before it renders, so the screen is unreachable in this build.
	//
	// To bring it back: delete this guard and restore the «Knowledge» tab in
	// src/routes/(app)/workspace/+layout.svelte.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { WELDING_KB_HREF } from '$lib/constants';
	import CreateKnowledgeBase from '$lib/components/workspace/Knowledge/CreateKnowledgeBase.svelte';

	let allowed = false;
	onMount(() => {
		goto(WELDING_KB_HREF);
	});
</script>

{#if allowed}
	<CreateKnowledgeBase />
{/if}
