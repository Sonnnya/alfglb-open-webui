<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import {
		WEBUI_NAME,
		showSidebar,
		functions,
		user,
		mobile,
		models,
		knowledge,
		tools
	} from '$lib/stores';
	import { page } from '$app/stores';
	import { WELDING_KB_HREF } from '$lib/constants';
	import { goto } from '$app/navigation';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Sidebar from '$lib/components/icons/Sidebar.svelte';

	const i18n = getContext('i18n');

	let loaded = false;

	onMount(async () => {
		if ($user?.role !== 'admin') {
			// Workspace is admin-only in this build (mirrors isMenuItemVisible in
			// src/lib/utils/menu-items.ts, which stops drawing the menu entry) with
			// ONE exception: the seeded knowledge base. It lives at
			// /workspace/knowledge/{id}, i.e. under this very layout, so a blanket
			// redirect here would lock every Эксперт out of the only screen the tier
			// exists for. The upstream per-tab checks below are kept intact for that
			// path and for if this is ever relaxed.
			if (!$page.url.pathname.startsWith(WELDING_KB_HREF)) {
				goto('/');
			} else if ($page.url.pathname.includes('/models') && !$user?.permissions?.workspace?.models) {
				goto('/');
			} else if (
				$page.url.pathname.includes('/knowledge') &&
				!$user?.permissions?.workspace?.knowledge
			) {
				goto('/');
			} else if (
				$page.url.pathname.includes('/prompts') &&
				!$user?.permissions?.workspace?.prompts
			) {
				goto('/');
			} else if ($page.url.pathname.includes('/tools') && !$user?.permissions?.workspace?.tools) {
				goto('/');
			} else if ($page.url.pathname.includes('/skills') && !$user?.permissions?.workspace?.skills) {
				goto('/');
			}
		}

		loaded = true;
	});
</script>

<svelte:head>
	<title>
		{$i18n.t('Workspace')} • {$WEBUI_NAME}
	</title>
</svelte:head>

{#if loaded}
	<div
		class=" relative flex flex-col w-full h-screen max-h-[100dvh] transition-width duration-200 ease-in-out {$showSidebar
			? 'md:max-w-[calc(100%-var(--sidebar-width))]'
			: ''} max-w-full"
	>
		<nav class="   px-2.5 pt-1.5 backdrop-blur-xl drag-region select-none">
			<div class=" flex items-center gap-1">
				{#if $mobile}
					<div class="{$showSidebar ? 'md:hidden' : ''} self-center flex flex-none items-center">
						<Tooltip
							content={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
							interactive={true}
						>
							<button
								id="sidebar-toggle-button"
								class=" cursor-pointer flex rounded-lg hover:bg-gray-100 dark:hover:bg-gray-850 transition cursor-"
								aria-label={$showSidebar ? $i18n.t('Close Sidebar') : $i18n.t('Open Sidebar')}
								on:click={() => {
									showSidebar.set(!$showSidebar);
								}}
							>
								<div class=" self-center p-1.5">
									<Sidebar />
								</div>
							</button>
						</Tooltip>
					</div>
				{/if}

				<!-- No tab strip on the knowledge base screen, for anyone including admins:
				     «База знаний» is its own destination reached straight from the main menu,
				     and Модели / Промпты / Скиллы sitting above it made it read as a
				     Workspace tab that had lost its own tab. Elsewhere under /workspace the
				     strip is admin-only — the only non-admin who reaches this layout is an
				     Эксперт, and every tab they could see is gone. -->
				<div
					class={$user?.role === 'admin' && !$page.url.pathname.startsWith(WELDING_KB_HREF)
						? ''
						: 'hidden'}
				>
					<div
						class="flex gap-1 scrollbar-none overflow-x-auto w-fit text-center text-sm font-medium rounded-full bg-transparent py-1 touch-auto pointer-events-auto"
					>
						{#if $user?.role === 'admin' || $user?.permissions?.workspace?.models}
							<a
								draggable="false"
								aria-current={$page.url.pathname.includes('/workspace/models') ? 'page' : null}
								class="min-w-fit p-1.5 {$page.url.pathname.includes('/workspace/models')
									? ''
									: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition select-none"
								href="/workspace/models">{$i18n.t('Models')}</a
							>
						{/if}

						<!-- «Knowledge» tab intentionally removed from this build: the deployment has
						     one knowledge base, and «База знаний» in the main menu goes straight to it
						     (WELDING_KB_HREF). The /workspace/knowledge route still exists and still
						     compiles — see the guard in its +page.svelte. -->

						{#if $user?.role === 'admin' || $user?.permissions?.workspace?.prompts}
							<a
								draggable="false"
								aria-current={$page.url.pathname.includes('/workspace/prompts') ? 'page' : null}
								class="min-w-fit p-1.5 {$page.url.pathname.includes('/workspace/prompts')
									? ''
									: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition select-none"
								href="/workspace/prompts">{$i18n.t('Prompts')}</a
							>
						{/if}

						{#if $user?.role === 'admin' || $user?.permissions?.workspace?.skills}
							<a
								draggable="false"
								aria-current={$page.url.pathname.includes('/workspace/skills') ? 'page' : null}
								class="min-w-fit p-1.5 {$page.url.pathname.includes('/workspace/skills')
									? ''
									: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition select-none"
								href="/workspace/skills"
							>
								{$i18n.t('Skills')}
							</a>
						{/if}

						{#if $user?.role === 'admin' || $user?.permissions?.workspace?.tools}
							<a
								draggable="false"
								aria-current={$page.url.pathname.includes('/workspace/tools') ? 'page' : null}
								class="min-w-fit p-1.5 {$page.url.pathname.includes('/workspace/tools')
									? ''
									: 'text-gray-300 dark:text-gray-600 hover:text-gray-700 dark:hover:text-white'} transition select-none"
								href="/workspace/tools"
							>
								{$i18n.t('Tools')}
							</a>
						{/if}
					</div>
				</div>

				<!-- <div class="flex items-center text-xl font-medium">{$i18n.t('Workspace')}</div> -->
			</div>
		</nav>

		<div
			class="  pb-1 px-3 md:px-[18px] flex-1 max-h-full overflow-y-auto"
			id="workspace-container"
		>
			<slot />
		</div>
	</div>
{/if}
