// Shared definition of the pinnable menu items, used by both the sidebar
// (src/lib/components/layout/Sidebar.svelte) and the user menu
// (src/lib/components/layout/Sidebar/UserMenu.svelte). Only the visibility
// predicate and the metadata are shared — each menu keeps its own rendering.

import { WELDING_KB_HREF } from '$lib/constants';

export const DEFAULT_PINNED_ITEMS = ['knowledge', 'workspace'];

export type MenuItemMeta = { label: string; href: string; iconType: string };

const MENU_ITEMS: Record<string, MenuItemMeta> = {
	// 'Knowledge Base' already exists as an i18n key ("База знаний" in ru-RU) and
	// survives i18n:parse via literals in other components — see the i18n section
	// of CLAUDE.md before changing this string.
	// Links to the one seeded collection, not the collections list.
	knowledge: { label: 'Knowledge Base', href: WELDING_KB_HREF, iconType: 'knowledge' },
	workspace: { label: 'Workspace', href: '/workspace', iconType: 'workspace' },
	automations: { label: 'Automations', href: '/automations', iconType: 'automations' },
	calendar: { label: 'Calendar', href: '/calendar', iconType: 'calendar' },
	playground: { label: 'Playground', href: '/playground', iconType: 'playground' }
};

export const getMenuItemMeta = (id: string): MenuItemMeta | undefined => MENU_ITEMS[id];

// Notes was replaced by the Knowledge Base. pinnedMenuItems is persisted per
// user, so anyone who ever reordered their menu has a stored array still
// containing 'notes' and would otherwise never see the new entry — the users
// most likely to have customised it are the ones the tiers are for. Mapping the
// id keeps whatever position they chose.
export const migratePinnedItems = (items: string[]): string[] => {
	const migrated = items.map((id) => (id === 'notes' ? 'knowledge' : id));
	return migrated.filter((id, index) => migrated.indexOf(id) === index);
};

// `config` and `user` are the resolved stores' values, not the stores.
export const isMenuItemVisible = (id: string, config: any, user: any): boolean => {
	switch (id) {
		case 'knowledge':
			// Tier membership never reaches the client — the seeded expert /
			// master-expert groups carry workspace.knowledge, and get_permissions()
			// flattens that into the session payload before it crosses the wire.
			return user?.role === 'admin' || (user?.permissions?.workspace?.knowledge ?? false);
		case 'workspace':
			// Admin-only in this build. The upstream test was "holds any workspace
			// permission", which let an Эксперт in on workspace.knowledge alone — and
			// the only tab they could see there was the collections list, which is
			// itself hidden now. «База знаний» above is their entry point instead.
			// src/routes/(app)/workspace/+layout.svelte enforces the same rule; this
			// only decides whether to draw the menu entry.
			return user?.role === 'admin';
		case 'automations':
			return (
				config?.features?.enable_automations &&
				(user?.role === 'admin' || user?.permissions?.features?.automations)
			);
		case 'calendar':
			return (
				config?.features?.enable_calendar &&
				(user?.role === 'admin' || user?.permissions?.features?.calendar)
			);
		case 'playground':
			return user?.role === 'admin';
		default:
			return false;
	}
};
