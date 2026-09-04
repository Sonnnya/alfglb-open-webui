<script lang="ts">
	import Fuse from 'fuse.js';
	import { toast } from 'svelte-sonner';
	import { v4 as uuidv4 } from 'uuid';
	import { PaneGroup, Pane, PaneResizer } from 'paneforge';

	import { onMount, getContext, onDestroy, tick } from 'svelte';
	import type { Writable } from 'svelte/store';
	import type { i18n as i18nType } from 'i18next';

	const i18n = getContext<Writable<i18nType>>('i18n');

	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		mobile,
		showSidebar,
		knowledge as _knowledge,
		config,
		user,
		settings,
		knowledgeDirectoryRevision,
		knowledgeDocumentRevision,
		activeKnowledgeDirectoryId
	} from '$lib/stores';

	import {
		updateFileDataContentById,
		uploadFile,
		deleteFileById,
		getFileById,
		renameFileById
	} from '$lib/apis/files';
	import {
		addFileToKnowledgeById,
		getKnowledgeById,
		getPendingKnowledgeFiles,
		removeFileFromKnowledgeById,
		resetKnowledgeById,
		updateFileFromKnowledgeById,
		updateKnowledgeById,
		updateKnowledgeAccessGrants,
		searchKnowledgeFilesById,
		createKnowledgeDirectory,
		updateKnowledgeDirectory,
		deleteKnowledgeDirectory,
		moveDocumentInKnowledge,
		moveFileInKnowledge,
		syncKnowledgeDiff,
		syncKnowledgeCleanup,
		testExternalKnowledgeRetrieval,
		getKnowledgeTags
	} from '$lib/apis/knowledge';
	import type { KnowledgeTag } from '$lib/apis/knowledge';
	import { processWeb, processYoutubeVideo } from '$lib/apis/retrieval';

	import { blobToFile, isYoutubeUrl } from '$lib/utils';
	import { computeFileHash } from '$lib/utils/hash';

	import Spinner from '$lib/components/common/Spinner.svelte';
	import Files from './KnowledgeBase/Files.svelte';
	import DocumentRegistry from './KnowledgeBase/DocumentRegistry.svelte';
	import TagChip from './KnowledgeBase/TagChip.svelte';

	// Tier membership never reaches the client, so "may review" is asked as a
	// permission — the seeded Мастер-эксперт group carries workspace.knowledge_review
	// and get_permissions() flattens it into the session payload. The backend
	// re-checks the same key, so this only hides buttons.
	$: canReviewVersions =
		$user?.role === 'admin' || ($user?.permissions?.workspace?.knowledge_review ?? false);
	import AddFilesPlaceholder from '$lib/components/AddFilesPlaceholder.svelte';

	import AddContentMenu from './KnowledgeBase/AddContentMenu.svelte';
	import AddTextContentModal from './KnowledgeBase/AddTextContentModal.svelte';
	import NewDirectoryModal from './KnowledgeBase/NewDirectoryModal.svelte';
	import NewFolderAlt from '$lib/components/icons/NewFolderAlt.svelte';
	import FolderOpen from '$lib/components/icons/FolderOpen.svelte';
	import KnowledgeBreadcrumbs from './KnowledgeBase/KnowledgeBreadcrumbs.svelte';

	import SyncConfirmDialog from '../../common/ConfirmDialog.svelte';
	import ConfirmDialog from '../../common/ConfirmDialog.svelte';
	import Drawer from '$lib/components/common/Drawer.svelte';
	import ChevronLeft from '$lib/components/icons/ChevronLeft.svelte';
	import LockClosed from '$lib/components/icons/LockClosed.svelte';
	import AccessControlModal from '../common/AccessControlModal.svelte';
	import Search from '$lib/components/icons/Search.svelte';
	import FilesOverlay from '$lib/components/chat/MessageInput/FilesOverlay.svelte';
	import DropdownOptions from '$lib/components/common/DropdownOptions.svelte';
	import Dropdown from '$lib/components/common/Dropdown.svelte';
	import Checkbox from '$lib/components/common/Checkbox.svelte';
	import AdjustmentsHorizontal from '$lib/components/icons/AdjustmentsHorizontal.svelte';
	import Pagination from '$lib/components/common/Pagination.svelte';
	import AttachWebpageModal from '$lib/components/chat/MessageInput/AttachWebpageModal.svelte';

	let largeScreen = true;

	let pane;
	let showSidepanel = true;

	let showAddWebpageModal = false;
	let showAddTextContentModal = false;
	let showNewDirectoryModal = false;

	let showSyncConfirmModal = false;
	let pendingSyncFiles: Array<{ path: string; filename: string; file: File }> | null = null;
	let syncing: string | null = null;
	// Covers the window `syncing` cannot: uploadDirectoryHandler awaits the native
	// picker and the whole tree walk before uploadDirectoryEntries sets `syncing`,
	// so the button would otherwise stay live through all of it. Two concurrent
	// runs race on createMissingDirectories: both read the same directory_map, both
	// try to create the same folders, and the loser's /dirs/create hits the
	// (knowledge_id, parent_id, name) constraint and aborts its whole upload.
	let pickingDirectory = false;
	let showAccessControlModal = false;
	let showResetConfirm = false;

	let minSize = 0;
	type DirectoryFileEntry = { path: string; filename: string; file: File };
	type DirectoryManifestEntry = DirectoryFileEntry & { checksum: string; size: number };
	// Folders are carried separately from files because the server cannot infer
	// them: POST /{id}/sync/diff derives its `mkdir` list from the paths of the
	// files in the manifest, so a folder holding no files anywhere below it is
	// invisible to it. `directories` is every folder the picker walked into.
	type DirectoryScan = { files: DirectoryFileEntry[]; directories: string[] };

	type Knowledge = {
		id: string;
		name: string;
		description: string;
		data: {
			file_ids: string[];
		};
		files: any[];
		access_grants?: any[];
		write_access?: boolean;
		meta?: any;
	};

	let id = null;
	let knowledge: Knowledge | null = null;
	let knowledgeId = null;
	let isExternalKnowledge = false;

	let selectedFileId = null;
	let selectedFile = null;
	let selectedFileContent = '';
	let loadingFileContent = false;

	let inputFiles = null;

	let query = '';
	let includeContent = false;
	let searchDebounceTimer: ReturnType<typeof setTimeout>;

	let viewOption = null;
	let sortKey = null;
	let direction = null;

	let currentPage = 1;
	let documentRegistry: { refresh: () => void } | null = null;
	let fileItems = null;
	let fileItemsTotal = null;
	// Reported by DocumentRegistry, which is the only caller of /documents and so
	// the only thing that knows the base-wide figure. Kept apart from
	// fileItemsTotal, which still gates the registry block below and still means
	// "published files at this level" — repurposing it would have hidden the whole
	// screen whenever the two disagreed.
	let documentsTotal: number | null = null;

	// Files still uploading, handed to the registry so it can show a row with a
	// spinner. Two sources already feed fileItems with status 'uploading': the
	// optimistic placeholder uploadFileHandler prepends, and the /files/pending
	// merge in getItemsPage (embedding still running). Both belong here.
	$: uploadingItems = (fileItems ?? []).filter((item) => item?.status === 'uploading');

	// Directory state
	let currentDirectoryId: string | null = null;
	let directoryItems = [];
	let breadcrumbs = [];

	let showDeleteDirectoryConfirm = false;
	let pendingDeleteDirectoryId: string | null = null;
	let deleteDirectoryContents = true;

	let pendingPollTimer: ReturnType<typeof setInterval> | null = null;
	let externalTestQuery = '';
	let externalTestResult: {
		documents?: string[];
		metadatas?: Record<string, any>[];
		distances?: number[];
	} | null = null;

	$: isExternalKnowledge = knowledge?.meta?.source === 'external';

	const reset = () => {
		currentPage = 1;
	};

	const init = async () => {
		reset();
		await getItemsPage();
		// getItemsPage() only refreshes the legacy /files list. The registry reads
		// /documents, which is the only source that includes revisions awaiting
		// review, so it has to be refreshed explicitly after every mutation.
		documentRegistry?.refresh();
		// And the sidebar tree, whose dots come from /dirs: a document uploaded or
		// deleted here changes a subtree's pending count. Safe to put in the shared
		// refresh path because init() is NOT part of mount — the tree fetches once
		// on its own there — so this fires per mutation, not per page load.
		knowledgeDirectoryRevision.update((n) => n + 1);
	};

	const handleSearchInput = () => {
		clearTimeout(searchDebounceTimer);

		searchDebounceTimer = setTimeout(() => {
			if (currentPage !== 1) {
				currentPage = 1;
			} else {
				getItemsPage();
			}
		}, 300);
	};

	// Immediate response to filter/pagination changes
	$: if (
		knowledgeId !== null &&
		viewOption !== undefined &&
		sortKey !== undefined &&
		direction !== undefined &&
		currentPage !== undefined &&
		includeContent !== undefined
	) {
		getItemsPage();
	}

	const getItemsPage = async () => {
		if (knowledgeId === null) return;

		fileItems = null;
		fileItemsTotal = null;

		if (sortKey === null) {
			direction = null;
		}

		const res = await searchKnowledgeFilesById(
			localStorage.token,
			knowledge.id,
			query,
			viewOption,
			sortKey,
			direction,
			currentPage,
			currentDirectoryId,
			includeContent
		).catch(() => {
			return null;
		});

		if (res) {
			fileItems = res.items;
			fileItemsTotal = res.total;
			directoryItems = res.directories ?? [];
			breadcrumbs = res.breadcrumbs ?? [];

			// Merge in-flight files not yet linked to the knowledge base
			try {
				const pendingFiles = await getPendingKnowledgeFiles(localStorage.token, knowledgeId);
				if (pendingFiles && pendingFiles.length > 0) {
					const existingIds = new Set(fileItems.map((f) => f.id));
					const newPending = pendingFiles
						.filter((f) => !existingIds.has(f.id))
						.map((f) => ({
							...f,
							name: f.meta?.name ?? f.filename,
							status: 'uploading'
						}));
					if (newPending.length > 0) {
						fileItems = [...newPending, ...fileItems];

						// Start polling for completion (if not already polling)
						if (!pendingPollTimer) {
							pendingPollTimer = setInterval(async () => {
								try {
									const still = await getPendingKnowledgeFiles(localStorage.token, knowledgeId);
									if (!still || still.length === 0) {
										clearInterval(pendingPollTimer);
										pendingPollTimer = null;
										init();
									}
								} catch {}
							}, 5000);
						}
					}
				}
			} catch (e) {
				console.warn('Failed to fetch pending files:', e);
			}
		}

		return res;
	};

	const fileSelectHandler = async (file) => {
		selectedFile = file;
		selectedFileContent = file?.data?.content ?? '';
		loadingFileContent = false;

		if (!file?.id || file?.data?.content !== undefined) {
			return;
		}

		loadingFileContent = true;
		try {
			const fileWithContent = await getFileById(localStorage.token, file.id);
			if (selectedFileId === file.id) {
				selectedFile = fileWithContent ?? file;
				selectedFileContent = fileWithContent?.data?.content ?? '';
			}
		} catch (e) {
			if (selectedFileId === file.id) {
				toast.error($i18n.t('Failed to load file content.'));
			}
		} finally {
			if (selectedFileId === file.id) {
				loadingFileContent = false;
			}
		}
	};

	const externalTestHandler = async () => {
		if (!isExternalKnowledge || !externalTestQuery.trim()) return;

		const external = knowledge?.meta?.external ?? {};
		const res = await testExternalKnowledgeRetrieval(localStorage.token, external.connection_id, {
			query: externalTestQuery,
			source: external.source,
			count: 5
		}).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			externalTestResult = res;
		}
	};

	const createFileFromText = (name, content) => {
		const blob = new Blob([content], { type: 'text/plain' });
		const file = blobToFile(blob, `${name}.txt`);

		console.log(file);
		return file;
	};

	const uploadWeb = async (urls) => {
		if (!Array.isArray(urls)) {
			urls = [urls];
		}

		const newFileItems = urls.map((url) => ({
			type: 'file',
			file: '',
			id: null,
			url: url,
			name: url,
			size: null,
			status: 'uploading',
			error: '',
			itemId: uuidv4()
		}));

		// Display all items at once
		fileItems = [...newFileItems, ...(fileItems ?? [])];

		for (const fileItem of newFileItems) {
			try {
				console.log(fileItem);
				const res = await processWeb(localStorage.token, '', fileItem.url, false).catch((e) => {
					console.error('Error processing web URL:', e);
					return null;
				});

				if (res) {
					console.log(res);
					const file = createFileFromText(
						// Use URL as filename, sanitized
						fileItem.url
							.replace(/[^a-z0-9]/gi, '_')
							.toLowerCase()
							.slice(0, 50),
						res.content
					);

					const uploadedFile = await uploadFile(localStorage.token, file, {
						knowledge_id: knowledge.id,
						directory_id: currentDirectoryId
					}).catch((e) => {
						toast.error(`${e}`);
						return null;
					});

					if (uploadedFile) {
						console.log(uploadedFile);
						fileItems = fileItems.map((item) => {
							if (item.itemId === fileItem.itemId) {
								item.id = uploadedFile.id;
							}
							return item;
						});

						if (uploadedFile.error) {
							console.warn('File upload warning:', uploadedFile.error);
							toast.warning(uploadedFile.error);
							fileItems = fileItems.filter((file) => file.id !== uploadedFile.id);
						} else {
							toast.success($i18n.t('File added successfully.'));
							init();
						}
					} else {
						toast.error($i18n.t('Failed to upload file.'));
					}
				} else {
					// remove the item from fileItems
					fileItems = fileItems.filter((item) => item.itemId !== fileItem.itemId);
					toast.error($i18n.t('Failed to process URL: {{url}}', { url: fileItem.url }));
				}
			} catch (e) {
				// remove the item from fileItems
				fileItems = fileItems.filter((item) => item.itemId !== fileItem.itemId);
				toast.error(`${e}`);
			}
		}
	};

	const uploadFileHandler = async (file) => {
		console.log(file);

		const fileItem = {
			type: 'file',
			file: '',
			id: null,
			url: '',
			name: file.name,
			size: file.size,
			status: 'uploading',
			error: '',
			itemId: uuidv4()
		};

		if (fileItem.size == 0) {
			toast.error($i18n.t('You cannot upload an empty file.'));
			return null;
		}

		if (
			($config?.file?.max_size ?? null) !== null &&
			file.size > ($config?.file?.max_size ?? 0) * 1024 * 1024
		) {
			console.log('File exceeds max size limit:', {
				fileSize: file.size,
				maxSize: ($config?.file?.max_size ?? 0) * 1024 * 1024
			});
			toast.error(
				$i18n.t(`File size should not exceed {{maxSize}} MB.`, {
					maxSize: $config?.file?.max_size
				})
			);
			return;
		}

		fileItems = [fileItem, ...(fileItems ?? [])];
		try {
			let metadata = {
				knowledge_id: knowledge.id,
				directory_id: currentDirectoryId,
				// If the file is an audio file, provide the language for STT.
				...((file.type.startsWith('audio/') || file.type.startsWith('video/')) &&
				$settings?.audio?.stt?.language
					? {
							language: $settings?.audio?.stt?.language
						}
					: {})
			};

			const uploadedFile = await uploadFile(localStorage.token, file, metadata).catch((e) => {
				toast.error(`${e}`);
				return null;
			});

			if (uploadedFile) {
				console.log(uploadedFile);
				fileItems = fileItems.map((item) => {
					if (item.itemId === fileItem.itemId) {
						item.id = uploadedFile.id;
					}
					return item;
				});

				if (uploadedFile.error) {
					console.warn('File upload warning:', uploadedFile.error);
					toast.warning(uploadedFile.error);
					fileItems = fileItems.filter((file) => file.id !== uploadedFile.id);
				} else {
					toast.success($i18n.t('File added successfully.'));
					init();
				}
			} else {
				toast.error($i18n.t('Failed to upload file.'));
			}
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	const uploadDirectoryHandler = async () => {
		const scan = await collectDirectoryFiles();
		// Folders on their own are a legitimate upload — recreating an empty tree
		// to file documents into afterwards is the main reason this button exists.
		if (scan?.files.length || scan?.directories.length) {
			await uploadDirectoryEntries(scan.files, scan.directories);
		}
	};

	// Helper function to check if a path contains hidden folders
	const hasHiddenFolder = (path) => {
		return path.split('/').some((part) => part.startsWith('.'));
	};

	// Error handler
	const handleUploadError = (error) => {
		if (error.name === 'AbortError') {
			toast.info($i18n.t('Directory selection was cancelled'));
		} else {
			toast.error($i18n.t('Error accessing directory'));
			console.error('Directory access error:', error);
		}
	};

	// Collect files from a directory without uploading.
	const collectDirectoryFiles = async (): Promise<DirectoryScan | null> => {
		const isFileSystemAccessSupported = 'showDirectoryPicker' in window;

		try {
			if (isFileSystemAccessSupported) {
				const dirHandle = await window.showDirectoryPicker();
				const files: DirectoryFileEntry[] = [];
				const directories: string[] = [];

				async function traverse(handle: FileSystemDirectoryHandle, dirPath = '') {
					for await (const entry of handle.values()) {
						if (entry.name.startsWith('.')) continue;
						const entryPath = dirPath ? `${dirPath}/${entry.name}` : entry.name;
						if (hasHiddenFolder(entryPath)) continue;

						if (entry.kind === 'file') {
							const file = await entry.getFile();
							files.push({ path: dirPath, filename: entry.name, file });
						} else if (entry.kind === 'directory') {
							directories.push(entryPath);
							await traverse(entry, entryPath);
						}
					}
				}

				// '' rather than dirHandle.name: the folder you pick is the one whose
				// CONTENTS are being uploaded, not a folder to recreate inside the base.
				// There is no multi-directory picker on the web, so picking the parent
				// and dropping it is how you upload several folders at once.
				await traverse(dirHandle, '');
				return { files, directories };
			} else {
				// Firefox fallback
				return new Promise((resolve, reject) => {
					const input = document.createElement('input');
					input.type = 'file';
					input.webkitdirectory = true;
					input.directory = true;
					input.multiple = true;
					input.style.display = 'none';
					document.body.appendChild(input);

					input.onchange = () => {
						try {
							const files = Array.from(input.files || []).filter(
								(file) => !hasHiddenFolder(file.webkitRelativePath) && !file.name.startsWith('.')
							);

							const collected = files.map((file) => {
								const parts = file.webkitRelativePath.split('/');
								const filename = parts.pop() || file.name;
								// slice(1) drops the picked folder's own name, which
								// webkitRelativePath always prefixes — same rule as the
								// showDirectoryPicker branch above.
								const path = parts.slice(1).join('/');
								return { path, filename, file };
							});

							document.body.removeChild(input);
							// No `directories`: a webkitdirectory input reports FILES only,
							// so an empty folder does not exist as far as this branch is
							// concerned. Folders implied by file paths still get created.
							resolve({ files: collected, directories: [] });
						} catch (error) {
							document.body.removeChild(input);
							reject(error);
						}
					};

					input.onerror = (error) => {
						document.body.removeChild(input);
						reject(error);
					};

					input.click();
				});
			}
		} catch (error) {
			handleUploadError(error);
			return null;
		}
	};

	const buildDirectoryManifest = async (
		entries: DirectoryFileEntry[]
	): Promise<DirectoryManifestEntry[]> => {
		return Promise.all(
			entries.map(async (entry) => ({
				...entry,
				checksum: await computeFileHash(entry.file),
				size: entry.file.size
			}))
		);
	};

	const createMissingDirectories = async (diff: any, scannedPaths: string[] = []) => {
		if (!knowledge) return {};

		const directoryIdByPath: Record<string, string> = { ...(diff.directory_map || {}) };

		// diff.mkdir is what the FILES imply; scannedPaths is every folder the picker
		// actually walked into, which is the only way an empty one gets here. Both are
		// full paths from the base root, so diff.directory_map decides what already
		// exists and re-uploading the same tree creates no FOLDER twice.
		//
		// Files are a different story and this does not make them idempotent: the diff
		// indexes existing files through get_files_with_directory_ids, which joins on
		// KnowledgeFile.file_id and so sees only PUBLISHED ones. Every document still
		// awaiting review is invisible to it, and a re-upload adds it again as a
		// second pending document.
		const wanted = [...diff.mkdir, ...scannedPaths.map(getDirectoryUploadPath)];
		const missing = [...new Set<string>(wanted)].filter((path) => path && !directoryIdByPath[path]);
		// Shallowest first — a folder cannot be created before its parent has an id.
		// The server already sorts diff.mkdir this way; merging in scannedPaths
		// requires re-sorting the union.
		missing.sort((a, b) => a.split('/').length - b.split('/').length);

		let created = 0;
		for (const dirPath of missing) {
			syncing = $i18n.t('Creating folders {{current}}/{{total}}', {
				current: ++created,
				total: missing.length
			});

			const segments = dirPath.split('/');
			const name = segments.at(-1)!;
			const parentPath = segments.slice(0, -1).join('/');
			const parentId = parentPath ? directoryIdByPath[parentPath] : null;

			const directory = await createKnowledgeDirectory(
				localStorage.token,
				knowledge.id,
				name,
				parentId
			);
			if (!directory) {
				// createKnowledgeDirectory resolves to null rather than throwing, so an
				// unchecked failure loses this folder AND everything below it to the base
				// root — silently. Abort instead; folders already made are found in
				// directory_map on the next attempt.
				throw new Error($i18n.t('Failed to create folder: {{path}}', { path: dirPath }));
			}
			directoryIdByPath[dirPath] = directory.id;
		}

		return directoryIdByPath;
	};

	const getDirectoryUploadPath = (path: string) => {
		const currentPath = breadcrumbs.map((crumb) => crumb.name).join('/');
		return currentPath && path ? `${currentPath}/${path}` : currentPath || path;
	};

	const uploadDirectoryEntries = async (
		entries: DirectoryFileEntry[],
		scannedPaths: string[] = []
	) => {
		if (!knowledge) return;

		try {
			syncing = $i18n.t('Computing checksums ({{count}} files)', { count: entries.length });
			const manifest = await buildDirectoryManifest(entries);

			syncing = $i18n.t('Comparing with knowledge base...');
			const diff = await syncKnowledgeDiff(
				localStorage.token,
				id,
				manifest.map(({ filename, path, checksum, size }) => ({
					filename,
					path: getDirectoryUploadPath(path),
					checksum,
					size
				}))
			);

			if (!diff) {
				toast.error($i18n.t('Failed to compare files.'));
				return;
			}

			// Passed even when the manifest is empty: the diff is what tells us which
			// folders the base ALREADY has (directory_map), which is the whole reason
			// to call it on a folders-only upload. Nothing here acts on diff.deleted
			// or diff.rmdir, so an empty manifest removes nothing.
			const directoryIdByPath = await createMissingDirectories(diff, scannedPaths);

			let uploadedCount = 0;
			for (const entry of manifest) {
				uploadedCount++;
				const displayPath = entry.path ? `${entry.path}/${entry.filename}` : entry.filename;
				syncing = $i18n.t('Uploading {{current}}/{{total}}: {{file}}', {
					current: uploadedCount,
					total: manifest.length,
					file: displayPath
				});

				const fileObject = new File([entry.file], entry.filename, { type: entry.file.type });
				await uploadFile(localStorage.token, fileObject, {
					knowledge_id: knowledge.id,
					file_hash: entry.checksum,
					directory_id: entry.path
						? directoryIdByPath[getDirectoryUploadPath(entry.path)]
						: currentDirectoryId
				}).catch((e) => {
					toast.error(`${e}`);
					return null;
				});
			}

			toast.success(
				manifest.length
					? $i18n.t('File uploaded successfully')
					: $i18n.t('Folders created successfully')
			);
			// The sidebar tree owns its own copy of the folder list, fetched from
			// /dirs — createMissingDirectories() went straight to the API rather
			// than through createDirectoryHandler, so nothing has told it that a
			// whole subtree appeared. init() only refreshes this screen.
			knowledgeDirectoryRevision.update((n) => n + 1);
			init();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			syncing = null;
		}
	};

	// Incremental sync: hash locally → diff on server → upload only what changed
	const syncDirectoryHandler = async () => {
		if (!pendingSyncFiles?.length) return;

		try {
			// ── 2. Compute checksums ──
			syncing = $i18n.t('Computing checksums ({{count}} files)', {
				count: pendingSyncFiles.length
			});
			const manifest = await buildDirectoryManifest(pendingSyncFiles);
			pendingSyncFiles = null;

			// ── 3. Diff against knowledge base ──
			syncing = $i18n.t('Comparing with knowledge base...');
			const diff = await syncKnowledgeDiff(
				localStorage.token,
				id,
				manifest.map(({ filename, path, checksum, size }) => ({ filename, path, checksum, size }))
			);

			if (!diff) {
				toast.error($i18n.t('Failed to compare files.'));
				return;
			}

			// ── 4. Cleanup — remove deleted + stale modified files first ──
			const staleFileIds = [
				...diff.deleted.map((d: any) => d.file_id),
				...diff.modified.map((m: any) => m.stale_file_id)
			];

			if (staleFileIds.length > 0 || diff.rmdir.length > 0) {
				syncing = $i18n.t('Removing {{count}} stale files...', { count: staleFileIds.length });
				await syncKnowledgeCleanup(localStorage.token, id, staleFileIds, diff.rmdir);
			}

			// ── 5. mkdir — create missing directories (parents first) ──
			const directoryIdByPath = await createMissingDirectories(diff);

			// ── 6. Upload added + modified files ──
			const filesToUpload = manifest.filter(
				(entry) =>
					diff.added.some((a: any) => a.filename === entry.filename && a.path === entry.path) ||
					diff.modified.some((m: any) => m.filename === entry.filename && m.path === entry.path)
			);

			let uploadedCount = 0;
			for (const entry of filesToUpload) {
				uploadedCount++;
				const displayPath = entry.path ? `${entry.path}/${entry.filename}` : entry.filename;
				syncing = $i18n.t('Uploading {{current}}/{{total}}: {{file}}', {
					current: uploadedCount,
					total: filesToUpload.length,
					file: displayPath
				});

				const fileObject = new File([entry.file], entry.filename, { type: entry.file.type });
				await uploadFile(localStorage.token, fileObject, {
					knowledge_id: knowledge.id,
					file_hash: entry.checksum,
					directory_id: entry.path ? directoryIdByPath[entry.path] : null
				}).catch(() => null);
			}

			// ── 7. Report ──
			toast.success(
				$i18n.t(
					'Sync complete: {{added}} added, {{modified}} modified, {{deleted}} deleted, {{unmodified}} unmodified',
					{
						added: diff.added.length,
						modified: diff.modified.length,
						deleted: diff.deleted.length,
						unmodified: diff.unmodified_count
					}
				)
			);
			init();
		} catch (e) {
			toast.error(`${e}`);
		} finally {
			syncing = null;
		}
	};

	const addFileHandler = async (fileId) => {
		const res = await addFileToKnowledgeById(
			localStorage.token,
			id,
			fileId,
			currentDirectoryId
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('File added successfully.'));
			init();
		} else {
			toast.error($i18n.t('Failed to add file.'));
			fileItems = fileItems.filter((file) => file.id !== fileId);
		}
	};

	// Directory handlers
	// ── Which folder is open ──────────────────────────────────────────────
	//
	// The URL is the single source of truth, not this component's state. Two
	// different things navigate — the folder rows in the registry and the sidebar
	// tree — and neither has a reference to the other; routing both through
	// ?dir=<id> is what lets them stay in step, and what makes a reload or a
	// shared link land in the same place.
	//
	// This used to be read once in onMount, which meant clicking a folder in the
	// sidebar while already on this screen changed the address bar and nothing
	// else: the component is not remounted for a query-string change.

	// Tags the registry is narrowed to. Owned here rather than in the registry so
	// the filter bar above the list and the chips inside it are one piece of
	// state — clicking a chip in a row and clearing it from the bar have to be
	// the same operation.
	let activeTagIds: string[] = [];
	let activeTags: KnowledgeTag[] = [];

	const toggleTagFilter = (tagId: string) => {
		activeTagIds = activeTagIds.includes(tagId)
			? activeTagIds.filter((id) => id !== tagId)
			: [...activeTagIds, tagId];
	};

	// The bar needs labels and descriptions, which a bare id does not carry.
	// Fetched once and looked up, rather than kept in sync with every row.
	let tagVocabulary: KnowledgeTag[] = [];
	$: activeTags = activeTagIds.map(
		(id) =>
			tagVocabulary.find((tag) => tag.id === id) ?? {
				id,
				label: id,
				created_at: 0,
				updated_at: 0
			}
	);

	const applyDirectory = (directoryId: string | null) => {
		currentDirectoryId = directoryId;
		currentPage = 1;
		selectedFileId = null;
		selectedFile = null;
		selectedFileContent = '';
		loadingFileContent = false;
		getItemsPage();
	};

	// The folder rows and the breadcrumbs call this. Same body the pre-registry
	// version had, plus two lines: publish to the store so the sidebar tree can
	// highlight, and keep the address bar honest.
	const navigateToDirectory = (directoryId: string | null) => {
		applyDirectory(directoryId);

		// set() is synchronous, so by the time the watcher below runs, the store and
		// currentDirectoryId already agree and it does nothing. That ordering is the
		// whole reason this is a store and not the URL.
		activeKnowledgeDirectoryId.set(directoryId);
		writeDirectoryToUrl(directoryId);
	};

	// Cosmetic ONLY. Nothing reads this back reactively — a reload or a shared link
	// picks it up once in onMount and that is all. The previous attempt made the URL
	// the source of truth via SvelteKit's replaceState, and $page.url lagged behind
	// the address bar, so the panel bounced back to the folder you had just left.
	const writeDirectoryToUrl = (directoryId: string | null) => {
		const url = new URL(window.location.href);
		if (directoryId) {
			url.searchParams.set('dir', directoryId);
		} else {
			url.searchParams.delete('dir');
		}
		history.replaceState(history.state, '', url);
	};

	// Navigation coming from OUTSIDE this component — the sidebar tree. Compared
	// against currentDirectoryId so our own navigateToDirectory cannot echo back.
	$: if (knowledge && $activeKnowledgeDirectoryId !== currentDirectoryId) {
		applyDirectory($activeKnowledgeDirectoryId);
		writeDirectoryToUrl($activeKnowledgeDirectoryId);
	}

	// A document moved. The single refresh path for it, wherever the move came
	// from: this screen's own ⋮ menu and drag-and-drop, or a drop onto the sidebar
	// tree, which is a different component tree entirely and can only signal.
	let appliedDocumentRevision = 0;
	$: if (knowledge && $knowledgeDocumentRevision !== appliedDocumentRevision) {
		appliedDocumentRevision = $knowledgeDocumentRevision;
		getItemsPage();
		documentRegistry?.refresh();
	}

	const createDirectoryHandler = async (name: string) => {
		const res = await createKnowledgeDirectory(
			localStorage.token,
			knowledge.id,
			name,
			currentDirectoryId
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Directory created.'));
			getItemsPage();
			documentRegistry?.refresh();
			// The sidebar tree reads /dirs and cannot see this any other way.
			knowledgeDirectoryRevision.update((n) => n + 1);
		}
	};

	const renameDirectoryHandler = async (dirId: string, name: string) => {
		const res = await updateKnowledgeDirectory(localStorage.token, knowledge.id, dirId, {
			name
		}).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Directory renamed.'));
			getItemsPage();
			documentRegistry?.refresh();
			// The sidebar tree reads /dirs and cannot see this any other way.
			knowledgeDirectoryRevision.update((n) => n + 1);
		}
	};

	const confirmDeleteDirectory = (dirId: string) => {
		pendingDeleteDirectoryId = dirId;
		showDeleteDirectoryConfirm = true;
	};

	const deleteDirectoryHandler = async (moveFiles: boolean) => {
		if (!pendingDeleteDirectoryId) return;

		const res = await deleteKnowledgeDirectory(
			localStorage.token,
			knowledge.id,
			pendingDeleteDirectoryId,
			moveFiles
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Directory deleted.'));
			getItemsPage();
			documentRegistry?.refresh();
			// The sidebar tree reads /dirs and cannot see this any other way.
			knowledgeDirectoryRevision.update((n) => n + 1);
		}
		pendingDeleteDirectoryId = null;
	};

	const moveFileToDirectoryHandler = async (fileId: string, directoryId: string | null) => {
		const res = await moveFileInKnowledge(
			localStorage.token,
			knowledge.id,
			fileId,
			directoryId
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('File moved.'));
			getItemsPage();
		}
	};

	// Keyed on the document, not its published file: moveFileToDirectoryHandler
	// cannot address a document whose only version is still awaiting review, which
	// is precisely the one an Эксперт has just uploaded and wants to file.
	const moveDocumentToDirectoryHandler = async (documentId: string, directoryId: string | null) => {
		const res = await moveDocumentInKnowledge(
			localStorage.token,
			knowledge.id,
			documentId,
			directoryId
		).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('File moved.'));
			// Refreshing is left to the knowledgeDocumentRevision watcher rather than
			// done here: a document dropped onto the sidebar tree is moved by the
			// sidebar, so that path has to exist anyway, and having one path means the
			// two cannot drift. Bumping it also keeps the server-computed folder
			// counts honest.
			knowledgeDocumentRevision.update((n) => n + 1);
			// The tree's dots are subtree counts, and this document just left one
			// subtree for another — two of them are now wrong.
			knowledgeDirectoryRevision.update((n) => n + 1);
		}
	};

	const moveDirectoryHandler = async (dirId: string, targetParentId: string | null) => {
		if (dirId === targetParentId) return;
		const res = await updateKnowledgeDirectory(localStorage.token, knowledge.id, dirId, {
			parent_id: targetParentId
		}).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			toast.success($i18n.t('Directory moved.'));
			getItemsPage();
			documentRegistry?.refresh();
			// The sidebar tree reads /dirs and cannot see this any other way.
			knowledgeDirectoryRevision.update((n) => n + 1);
		}
	};

	const deleteFileHandler = async (fileId) => {
		try {
			console.log('Starting file deletion process for:', fileId);

			// Remove from knowledge base only
			const res = await removeFileFromKnowledgeById(localStorage.token, id, fileId);
			console.log('Knowledge base updated:', res);

			if (res) {
				toast.success($i18n.t('File removed successfully.'));
				await init();
			}
		} catch (e) {
			console.error('Error in deleteFileHandler:', e);
			toast.error(`${e}`);
		}
	};

	const renameFileHandler = async (fileId: string, name: string) => {
		try {
			const res = await renameFileById(localStorage.token, fileId, name);
			if (res) {
				toast.success($i18n.t('File renamed.'));
				getItemsPage();
			}
		} catch (e) {
			toast.error(`${e}`);
		}
	};

	let debounceTimeout = null;
	let mediaQuery;

	let dragged = false;
	let isSaving = false;

	const updateFileContentHandler = async () => {
		if (isSaving || loadingFileContent || !selectedFile?.id) {
			return;
		}

		isSaving = true;

		try {
			const res = await updateFileDataContentById(
				localStorage.token,
				selectedFile.id,
				selectedFileContent
			).catch((e) => {
				toast.error(`${e}`);
				return null;
			});

			if (res) {
				toast.success($i18n.t('File content updated successfully.'));

				selectedFileId = null;
				selectedFile = null;
				selectedFileContent = '';

				await init();
			}
		} finally {
			isSaving = false;
		}
	};

	const changeDebounceHandler = () => {
		console.log('debounce');
		if (debounceTimeout) {
			clearTimeout(debounceTimeout);
		}

		debounceTimeout = setTimeout(async () => {
			if (knowledge.name.trim() === '' || knowledge.description.trim() === '') {
				toast.error($i18n.t('Please fill in all fields.'));
				return;
			}

			const res = await updateKnowledgeById(localStorage.token, id, {
				...knowledge,
				name: knowledge.name,
				description: knowledge.description,
				access_grants: knowledge.access_grants ?? []
			}).catch((e) => {
				toast.error(`${e}`);
			});

			if (res) {
				toast.success($i18n.t('Knowledge updated successfully'));
			}
		}, 1000);
	};

	const handleMediaQuery = async (e) => {
		if (e.matches) {
			largeScreen = true;
		} else {
			largeScreen = false;
		}
	};

	const readDirectoryEntries = async (reader: any) => {
		const entries: any[] = [];

		while (true) {
			const batch = await new Promise<any[]>((resolve, reject) => {
				reader.readEntries(resolve, reject);
			});

			if (batch.length === 0) {
				break;
			}

			entries.push(...batch);
		}

		return entries;
	};

	const collectDroppedEntryFiles = async (
		entry: any,
		entryPath = entry.name
	): Promise<DirectoryFileEntry[]> => {
		if (entry.name.startsWith('.') || hasHiddenFolder(entryPath)) {
			return [];
		}

		if (entry.isFile) {
			const file = await new Promise<File>((resolve, reject) => {
				entry.file(resolve, reject);
			});
			const parts = entryPath.split('/');
			const filename = parts.pop() || file.name;
			return [{ path: parts.join('/'), filename, file }];
		}

		if (entry.isDirectory) {
			const reader = entry.createReader();
			const entries = await readDirectoryEntries(reader);
			const nested = await Promise.all(
				entries.map((child) => collectDroppedEntryFiles(child, `${entryPath}/${child.name}`))
			);
			return nested.flat();
		}

		return [];
	};

	const onDragOver = (e) => {
		e.preventDefault();

		// Check if a file is being draggedOver.
		if (e.dataTransfer?.types?.includes('Files')) {
			dragged = true;
		} else {
			dragged = false;
		}
	};

	const onDragLeave = () => {
		dragged = false;
	};

	const onDrop = async (e) => {
		e.preventDefault();
		dragged = false;

		if (!knowledge?.write_access) {
			toast.error($i18n.t('You do not have permission to upload files to this knowledge base.'));
			return;
		}

		if (e.dataTransfer?.types?.includes('Files')) {
			if (e.dataTransfer?.files) {
				const inputItems = e.dataTransfer?.items;

				if (inputItems && inputItems.length > 0) {
					const directoryEntries: DirectoryFileEntry[] = [];
					const looseFiles: File[] = [];

					for (const rawItem of Array.from(inputItems)) {
						const item = rawItem as DataTransferItem & { webkitGetAsEntry?: () => any };
						const entry = item.webkitGetAsEntry?.();

						if (entry?.isDirectory) {
							directoryEntries.push(...(await collectDroppedEntryFiles(entry)));
						} else {
							const file = item.getAsFile();
							if (file) {
								looseFiles.push(file);
							}
						}
					}

					for (const file of looseFiles) {
						await uploadFileHandler(file);
					}

					if (directoryEntries.length > 0) {
						await uploadDirectoryEntries(directoryEntries);
					}
				} else {
					toast.error($i18n.t(`File not found.`));
				}
			}
		}
	};

	onMount(async () => {
		// The vocabulary, for the filter bar's labels and descriptions. Failure is
		// silent: chips still render their id, which is the readable part anyway.
		getKnowledgeTags(localStorage.token)
			.then((tags) => {
				tagVocabulary = tags;
			})
			.catch(() => {});

		// listen to resize 1024px
		mediaQuery = window.matchMedia('(min-width: 1024px)');

		mediaQuery.addEventListener('change', handleMediaQuery);
		handleMediaQuery(mediaQuery);

		// Select the container element you want to observe
		const container = document.getElementById('collection-container');

		// initialize the minSize based on the container width
		minSize = !largeScreen ? 100 : Math.floor((300 / container.clientWidth) * 100);

		// Create a new ResizeObserver instance
		const resizeObserver = new ResizeObserver((entries) => {
			for (let entry of entries) {
				const width = entry.contentRect.width;
				// calculate the percentage of 300
				const percentage = (300 / width) * 100;
				// set the minSize to the percentage, must be an integer
				minSize = !largeScreen ? 100 : Math.floor(percentage);

				if (showSidepanel) {
					if (pane && pane.isExpanded() && pane.getSize() < minSize) {
						pane.resize(minSize);
					}
				}
			}
		});

		// Start observing the container's size changes
		resizeObserver.observe(container);

		if (pane) {
			pane.expand();
		}

		id = $page.params.id;
		// The sidebar tree links to WELDING_KB_HREF?dir=<id>. Read it before the
		// first load so the screen opens inside the folder instead of at root and
		// then jumping — init() runs below and picks this up.
		currentDirectoryId = $page.url.searchParams.get('dir') || null;
		// Seed the store as well: the watcher above compares the two, so leaving it
		// at its default would pull a deep link straight back to the root.
		activeKnowledgeDirectoryId.set(currentDirectoryId);
		const res = await getKnowledgeById(localStorage.token, id).catch((e) => {
			toast.error(`${e}`);
			return null;
		});

		if (res) {
			knowledge = res;
			if (!Array.isArray(knowledge?.access_grants)) {
				knowledge.access_grants = [];
			}
			knowledgeId = knowledge?.id;
		} else {
			// Home, not '/workspace/knowledge': that route now bounces to
			// WELDING_KB_HREF, which is the base that just failed to load — the two
			// would ping-pong forever.
			goto('/');
		}

		const dropZone = document.querySelector('body');
		dropZone?.addEventListener('dragover', onDragOver);
		dropZone?.addEventListener('drop', onDrop);
		dropZone?.addEventListener('dragleave', onDragLeave);
	});

	onDestroy(() => {
		clearTimeout(searchDebounceTimer);
		if (pendingPollTimer) {
			clearInterval(pendingPollTimer);
			pendingPollTimer = null;
		}
		mediaQuery?.removeEventListener('change', handleMediaQuery);
		const dropZone = document.querySelector('body');
		dropZone?.removeEventListener('dragover', onDragOver);
		dropZone?.removeEventListener('drop', onDrop);
		dropZone?.removeEventListener('dragleave', onDragLeave);
	});

	const decodeString = (str: string) => {
		try {
			return decodeURIComponent(str);
		} catch (e) {
			return str;
		}
	};
</script>

<FilesOverlay show={dragged} />
<SyncConfirmDialog
	bind:show={showSyncConfirmModal}
	message={$i18n.t(
		'{{count}} files selected. Only new and modified files will be uploaded. Deleted files will be removed. The folder structure will be mirrored. Continue?',
		{ count: pendingSyncFiles?.length ?? 0 }
	)}
	on:confirm={() => {
		syncDirectoryHandler();
	}}
	on:cancel={() => {
		pendingSyncFiles = null;
	}}
/>

<AttachWebpageModal
	bind:show={showAddWebpageModal}
	onSubmit={async (e) => {
		uploadWeb(e.data);
	}}
/>

<AddTextContentModal
	bind:show={showAddTextContentModal}
	on:submit={(e) => {
		const file = createFileFromText(e.detail.name, e.detail.content);
		uploadFileHandler(file);
	}}
/>

<NewDirectoryModal
	bind:show={showNewDirectoryModal}
	on:submit={(e) => {
		createDirectoryHandler(e.detail.name);
	}}
/>

<!-- Single-file on purpose: one knowledge document is one file, and the picker is
     now reached straight from «Загрузить новый документ». Dropping several files
     still works and still makes one document each — the loop below is unchanged. -->
<input
	id="files-input"
	bind:files={inputFiles}
	type="file"
	hidden
	on:change={async () => {
		if (inputFiles && inputFiles.length > 0) {
			for (const file of inputFiles) {
				await uploadFileHandler(file);
			}

			inputFiles = null;
			const fileInputElement = document.getElementById('files-input');

			if (fileInputElement) {
				fileInputElement.value = '';
			}
		} else {
			toast.error($i18n.t(`File not found.`));
		}
	}}
/>

<div class="flex flex-col w-full h-full min-h-full" id="collection-container">
	{#if id && knowledge}
		<AccessControlModal
			bind:show={showAccessControlModal}
			bind:accessGrants={knowledge.access_grants}
			share={$user?.permissions?.sharing?.knowledge || $user?.role === 'admin'}
			sharePublic={$user?.permissions?.sharing?.public_knowledge || $user?.role === 'admin'}
			shareUsers={($user?.permissions?.access_grants?.allow_users ?? true) ||
				$user?.role === 'admin'}
			onChange={async () => {
				try {
					await updateKnowledgeAccessGrants(localStorage.token, id, knowledge.access_grants ?? []);
					toast.success($i18n.t('Saved'));
				} catch (error) {
					toast.error(`${error}`);
				}
			}}
			accessRoles={['read', 'write']}
		/>
		<div class="w-full px-2">
			<div class=" flex w-full">
				<div class="flex-1">
					<div class="flex items-center justify-between w-full">
						<div class="w-full flex justify-between items-center">
							<input
								type="text"
								class="text-left w-full text-lg bg-transparent outline-hidden flex-1"
								bind:value={knowledge.name}
								aria-label={$i18n.t('Knowledge Name')}
								placeholder={$i18n.t('Knowledge Name')}
								disabled={!knowledge?.write_access}
								on:input={() => {
									changeDebounceHandler();
								}}
							/>

							<div class="shrink-0 mr-2.5">
								<!-- The WHOLE base, subfolders and pending revisions included.
								     It used to be fileItemsTotal, i.e. the /files search — which
								     is published-only and scoped to the open folder, so standing
								     in a folder showed that folder's approved files and read as
								     the base having shrunk. `!== null` rather than a truthiness
								     test so an empty base says «0», not nothing. -->
								{#if documentsTotal !== null}
									<div class="text-xs text-gray-500">
										<!-- Lowercase `count`, not the upstream {{COUNT}}: i18next selects a
										     plural form from the `count` option specifically, so the
										     uppercase one rendered «1 файлов». -->
										{$i18n.t('{{count}} files', {
											count: documentsTotal
										})}
									</div>
								{/if}
							</div>
						</div>

						{#if knowledge?.write_access}
							<div class="self-center shrink-0">
								<button
									class="bg-gray-50 hover:bg-gray-100 text-black dark:bg-gray-850 dark:hover:bg-gray-800 dark:text-white transition px-2 py-1 rounded-full flex gap-1 items-center"
									type="button"
									on:click={() => {
										showAccessControlModal = true;
									}}
								>
									<LockClosed strokeWidth="2.5" className="size-3.5" />

									<div class="text-sm font-medium shrink-0">
										{$i18n.t('Access')}
									</div>
								</button>
							</div>
						{:else}
							<div class="text-xs shrink-0 text-gray-500">
								{$i18n.t('Read Only')}
							</div>
						{/if}
					</div>

					<div class="flex w-full items-center">
						<input
							type="text"
							class="text-left text-xs w-full text-gray-500 bg-transparent outline-hidden flex-1"
							bind:value={knowledge.description}
							aria-label={$i18n.t('Knowledge Description')}
							placeholder={$i18n.t('Knowledge Description')}
							disabled={!knowledge?.write_access}
							on:input={() => {
								changeDebounceHandler();
							}}
						/>
					</div>
				</div>
			</div>
		</div>

		<div
			class="mt-2 mb-2.5 py-2 -mx-0 bg-white dark:bg-gray-900 rounded-3xl border border-gray-100/30 dark:border-gray-850/30 flex-1"
		>
			{#if isExternalKnowledge}
				<div class="p-5 flex flex-col gap-4">
					<div class="flex flex-wrap gap-2 text-xs">
						<div class="px-2 py-1 rounded-lg bg-gray-50 dark:bg-gray-850">
							{$i18n.t('Connected')}
						</div>
						<div class="px-2 py-1 rounded-lg bg-gray-50 dark:bg-gray-850">
							{$i18n.t('Read Only')}
						</div>
						<div class="px-2 py-1 rounded-lg bg-gray-50 dark:bg-gray-850">
							{knowledge?.meta?.external?.provider ?? $i18n.t('Provider')}
						</div>
						<div class="px-2 py-1 rounded-lg bg-gray-50 dark:bg-gray-850">
							{$i18n.t('Service Account')}
						</div>
					</div>

					<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
						<div>
							<div class="text-xs text-gray-500 mb-1">{$i18n.t('Mapped Source')}</div>
							<div class="rounded-xl bg-gray-50 dark:bg-gray-850 px-3 py-2">
								{knowledge?.meta?.external?.source?.name ?? $i18n.t('Not configured')}
							</div>
						</div>
						<div>
							<div class="text-xs text-gray-500 mb-1">{$i18n.t('Auth Mode')}</div>
							<div class="rounded-xl bg-gray-50 dark:bg-gray-850 px-3 py-2">
								{$i18n.t('Admin-managed service account')}
							</div>
						</div>
					</div>

					<div class="text-xs text-gray-500">
						{$i18n.t(
							'This knowledge base retrieves from a connected source. Open WebUI can query it, but cannot upload, sync, edit, delete, reset, or reindex its source data.'
						)}
					</div>

					<div class="flex flex-col gap-2">
						<div class="font-medium text-sm">{$i18n.t('Test Query')}</div>
						<div class="flex gap-2">
							<input
								class="w-full text-sm rounded-xl bg-gray-50 dark:bg-gray-850 px-3 py-2 outline-hidden"
								bind:value={externalTestQuery}
								placeholder={$i18n.t('Ask this knowledge source a test question')}
							/>
							<button
								class="px-3 py-2 rounded-xl bg-black text-white dark:bg-white dark:text-black text-sm"
								on:click={externalTestHandler}
							>
								{$i18n.t('Test')}
							</button>
						</div>
					</div>

					{#if externalTestResult}
						<div class="rounded-xl bg-gray-50 dark:bg-gray-850 p-3 text-xs">
							<div class="font-medium mb-2">{$i18n.t('Preview')}</div>
							{#each externalTestResult.documents ?? [] as document, idx}
								<div class="border-t border-gray-100 dark:border-gray-800 py-2">
									<div class="line-clamp-4">{document}</div>
									<div class="text-gray-500 mt-1">
										{externalTestResult.metadatas?.[idx]?.source ?? ''}
									</div>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{:else}
				<div class="px-3.5 flex flex-1 items-center w-full space-x-2 py-0.5 pb-2">
					<div class="flex flex-1 items-center">
						<div class=" self-center ml-1 mr-3">
							<Search className="size-3.5" />
						</div>
						<input
							class=" w-full text-sm pr-4 py-1 rounded-r-xl outline-hidden bg-transparent"
							bind:value={query}
							on:input={handleSearchInput}
							aria-label={$i18n.t('Search Documents')}
							placeholder={$i18n.t('Search Documents')}
							on:focus={() => {
								selectedFileId = null;
								selectedFile = null;
								selectedFileContent = '';
								loadingFileContent = false;
							}}
						/>

						<!-- «Содержимое файла» search toggle hidden in this build: the registry is a
						     flat document list, and matching inside file text produced hits with no row
						     to attach them to. The block below is LEFT IN PLACE and still compiles — the
						     `includeContent` flag it drives is still sent with every search, just always
						     false. To bring it back, change the {#if false} to {#if true}. -->
						{#if false}
							<Dropdown align="end">
								<button
									class="p-1.5 mr-1 rounded-xl text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition"
									type="button"
								>
									<AdjustmentsHorizontal className="size-3.5" strokeWidth="2" />
								</button>

								<div slot="content">
									<div
										class="min-w-[180px] rounded-2xl px-1 py-1 border border-gray-100 dark:border-gray-800 z-50 bg-white dark:bg-gray-850 dark:text-white shadow-lg"
									>
										<button
											class="select-none flex gap-2 items-center px-3 py-1.5 text-sm cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 rounded-xl w-full"
											type="button"
											on:click={() => {
												includeContent = !includeContent;
											}}
										>
											<Checkbox
												state={includeContent ? 'checked' : 'unchecked'}
												on:change={(e) => {
													includeContent = e.detail === 'checked';
												}}
											/>
											{$i18n.t('File content')}
										</button>
									</div>
								</div>
							</Dropdown>
						{/if}

						{#if knowledge?.write_access}
							<div>
								<AddContentMenu
									onUpload={(data) => {
										if (data.type === 'directory') {
											uploadDirectoryHandler();
										} else if (data.type === 'new_directory') {
											showNewDirectoryModal = true;
										} else if (data.type === 'web') {
											showAddWebpageModal = true;
										} else if (data.type === 'text') {
											showAddTextContentModal = true;
										} else {
											document.getElementById('files-input').click();
										}
									}}
									onSync={async () => {
										pendingSyncFiles = (await collectDirectoryFiles())?.files ?? null;
										if (pendingSyncFiles?.length) {
											showSyncConfirmModal = true;
										}
									}}
									onReset={() => {
										showResetConfirm = true;
									}}
								/>
							</div>

							<!-- Secondary to «Загрузить новый документ» on purpose: uploading is
							     the everyday action, foldering is occasional. It creates the folder
							     inside whichever one is open, so the button follows the breadcrumb. -->
							<button
								class="px-3 py-1.5 rounded-xl border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-850 transition font-medium text-sm flex items-center gap-1.5 shrink-0"
								type="button"
								on:click={() => {
									showNewDirectoryModal = true;
								}}
							>
								<NewFolderAlt className="size-4" />
								{$i18n.t('Create folder')}
							</button>

							<!-- Admin-only, and cosmetically so — like every other gate in this
							     tree. It drives the pre-existing uploadDirectoryHandler(), which
							     reaches POST /{id}/dirs/create (gated by
							     _verify_knowledge_write_access) and POST /files/ (whose
							     knowledge auto-link gates on the same write grant), so an
							     Эксперт could still do all of this over HTTP. The restriction is
							     about who should be reshaping the folder tree wholesale, not
							     about what the server will accept.

							     Empty folders included — the picker reports them and they are
							     sent alongside the files, because the server derives folders
							     from file paths alone and cannot see one that holds nothing.
							     The exception is Firefox, whose webkitdirectory fallback
							     reports files only. -->
							{#if $user?.role === 'admin'}
								<button
									class="px-3 py-1.5 rounded-xl border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-850 transition font-medium text-sm flex items-center gap-1.5 shrink-0 disabled:opacity-50"
									type="button"
									disabled={!!syncing || pickingDirectory}
									on:click={async () => {
										pickingDirectory = true;
										try {
											await uploadDirectoryHandler();
										} finally {
											pickingDirectory = false;
										}
									}}
								>
									<FolderOpen className="size-4" strokeWidth="2" />
									{$i18n.t('Upload directory')}
								</button>
							{/if}
						{/if}
					</div>
				</div>

				<div class="px-3 flex justify-between">
					<div
						class="flex w-full bg-transparent overflow-x-auto scrollbar-none"
						on:wheel={(e) => {
							if (e.deltaY !== 0) {
								e.preventDefault();
								e.currentTarget.scrollLeft += e.deltaY;
							}
						}}
					>
						<div
							class="flex gap-3 w-fit text-center text-sm rounded-full bg-transparent px-0.5 whitespace-nowrap"
						>
							<DropdownOptions
								align="start"
								className="flex shrink-0 items-center gap-2 px-3 py-1.5 text-sm bg-gray-50 dark:bg-gray-850 rounded-xl placeholder-gray-400 outline-hidden focus:outline-hidden"
								bind:value={viewOption}
								items={[
									{ value: null, label: $i18n.t('All') },
									{ value: 'created', label: $i18n.t('Created by you') },
									{ value: 'shared', label: $i18n.t('Shared with you') }
								]}
								onChange={(value) => {
									if (value) {
										localStorage.workspaceViewOption = value;
									} else {
										delete localStorage.workspaceViewOption;
									}
								}}
							/>

							<DropdownOptions
								align="start"
								bind:value={sortKey}
								placeholder={$i18n.t('Sort')}
								items={[
									{ value: 'name', label: $i18n.t('Name') },
									{ value: 'created_at', label: $i18n.t('Created At') },
									{ value: 'updated_at', label: $i18n.t('Updated At') }
								]}
							/>

							{#if sortKey}
								<DropdownOptions
									align="start"
									bind:value={direction}
									items={[
										{ value: 'asc', label: $i18n.t('Asc') },
										{ value: null, label: $i18n.t('Desc') }
									]}
								/>
							{/if}
						</div>
					</div>
				</div>

				{#if activeTagIds.length > 0}
					<!-- Only rendered when something is active: an always-present empty
					     bar would push the list down for the majority of visits, and the
					     chips in each row are how a filter gets started. -->
					<div class="px-5 mt-2 flex flex-wrap items-center gap-1.5">
						<span class="text-xs text-gray-500">{$i18n.t('Filtered by')}:</span>
						{#each activeTags as tag (tag.id)}
							<TagChip {tag} active onRemove={(t) => toggleTagFilter(t.id)} />
						{/each}
						<button
							type="button"
							class="text-xs text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition"
							on:click={() => (activeTagIds = [])}
						>
							{$i18n.t('Clear')}
						</button>
					</div>
				{/if}

				<!-- Drawn at the root too, where `breadcrumbs` is empty and the bar is
				     just the base's own name. A path that appears only once you are
				     one level deep leaves the root looking like a different screen,
				     and there is nothing to click your way back to.

				     Hidden while a SEARCH is running: results are gathered from the whole
				     base, so the folder scoping is dropped and the API returns no
				     path — a bar reading «База знаний по сварке» over hits from
				     «ГОСТы» and «Учебники» alike would be a claim about where you
				     are that is no longer true. Clearing the search brings it back
				     one debounce later, which is the only visible seam.

				     A tag filter is hidden for the same reason: it flattens the
				     listing exactly as a search does, so the API returns no path
				     and the bar would collapse to a bare base name over hits from
				     every folder. -->
				{#if (query ?? '').trim().length === 0 && activeTagIds.length === 0}
					<div class="px-5 mt-2">
						<KnowledgeBreadcrumbs
							rootLabel={knowledge.name}
							{breadcrumbs}
							onNavigate={(dirId) => navigateToDirectory(dirId)}
							onMoveFile={(documentId, dirId) => moveDocumentToDirectoryHandler(documentId, dirId)}
							onMoveDir={(dirId, targetId) => moveDirectoryHandler(dirId, targetId)}
						/>
					</div>
				{/if}

				{#if syncing}
					<div class="mx-2.5 mt-2.5 -mb-0.5">
						<div class="flex items-center gap-2.5 rounded-xl py-2 px-3 bg-gray-50 dark:bg-gray-850">
							<Spinner className="size-3.5 shrink-0" />
							<div class="text-xs text-gray-500 dark:text-gray-400 truncate">
								{syncing}
							</div>
						</div>
					</div>
				{/if}

				{#if fileItems !== null && fileItemsTotal !== null}
					<div class="flex flex-row flex-1 gap-3 px-2.5 mt-2">
						<div class="flex-1 flex">
							<div class=" flex flex-col w-full space-x-2 rounded-lg h-full">
								<div class="w-full h-full flex flex-col min-h-full">
									{#if true}
										<!-- Flat document registry. Files.svelte (the folder view) is
										     left in place and can be swapped back in — nothing about the
										     knowledge_directory schema was removed. -->
										<div class=" flex overflow-y-auto h-full w-full scrollbar-hidden text-xs">
											<DocumentRegistry
												bind:this={documentRegistry}
												knowledgeId={knowledge.id}
												canReview={canReviewVersions}
												canUpload={knowledge?.write_access ?? false}
												writeAccess={knowledge?.write_access ?? false}
												directoryId={currentDirectoryId}
												{query}
												uploading={uploadingItems}
												onNavigate={(dirId) => navigateToDirectory(dirId)}
												onRenameDirectory={(dirId, name) => renameDirectoryHandler(dirId, name)}
												onDeleteDirectory={(dirId) => confirmDeleteDirectory(dirId)}
												onMoveDirectory={(dirId, targetId) => moveDirectoryHandler(dirId, targetId)}
												onMoveDocument={(documentId, targetId) =>
													moveDocumentToDirectoryHandler(documentId, targetId)}
												{activeTagIds}
												canTagDocuments={canReviewVersions}
												canCurateTags={$user?.role === 'admin'}
												onToggleTag={(tagId) => toggleTagFilter(tagId)}
												onTree={(crumbs) => {
													breadcrumbs = crumbs;
												}}
												onTotal={(totalAll) => {
													documentsTotal = totalAll;
												}}
											/>
										</div>
									{:else}
										<div
											class="my-3 flex flex-col justify-center text-center text-gray-500 text-xs"
										>
											<div>
												{$i18n.t('No content found')}
											</div>
										</div>
									{/if}
								</div>
							</div>
						</div>

						{#if selectedFileId !== null}
							<Drawer
								className="h-full"
								show={selectedFileId !== null}
								onClose={() => {
									selectedFileId = null;
									selectedFile = null;
									selectedFileContent = '';
									loadingFileContent = false;
								}}
							>
								<div class="flex flex-col justify-start h-full max-h-full">
									<div class=" flex flex-col w-full h-full max-h-full">
										<div class="shrink-0 flex items-center p-2">
											<div class="mr-2">
												<button
													class="w-full text-left text-sm p-1.5 rounded-lg dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-gray-850"
													aria-label={$i18n.t('Close')}
													on:click={() => {
														selectedFileId = null;
														selectedFile = null;
														selectedFileContent = '';
														loadingFileContent = false;
													}}
												>
													<ChevronLeft strokeWidth="2.5" />
												</button>
											</div>
											<div class=" flex-1 text-lg line-clamp-1">
												{selectedFile?.meta?.name}
											</div>

											{#if knowledge?.write_access}
												<div>
													<button
														class="flex self-center w-fit text-sm py-1 px-2.5 dark:text-gray-300 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
														disabled={isSaving || loadingFileContent}
														on:click={() => {
															updateFileContentHandler();
														}}
													>
														{$i18n.t('Save')}
														{#if isSaving}
															<div class="ml-2 self-center">
																<Spinner />
															</div>
														{/if}
													</button>
												</div>
											{/if}
										</div>

										{#key selectedFile?.id}
											<textarea
												class="w-full h-full text-sm outline-none resize-none px-3 py-2"
												bind:value={selectedFileContent}
												disabled={!knowledge?.write_access || loadingFileContent}
												aria-label={$i18n.t('File content')}
												placeholder={$i18n.t('Add content here')}
											></textarea>
										{/key}
									</div>
								</div>
							</Drawer>
						{/if}
					</div>
				{:else}
					<div class="my-10">
						<Spinner className="size-4" />
					</div>
				{/if}
			{/if}
		</div>
	{:else}
		<Spinner className="size-5" />
	{/if}
</div>

<ConfirmDialog
	bind:show={showDeleteDirectoryConfirm}
	title={$i18n.t('Delete directory?')}
	on:confirm={() => {
		deleteDirectoryHandler(!deleteDirectoryContents);
	}}
	on:cancel={() => {
		pendingDeleteDirectoryId = null;
	}}
>
	<div class="text-sm text-gray-700 dark:text-gray-300 flex-1 line-clamp-3 mb-2">
		{$i18n.t(`Are you sure you want to delete this directory?`)}
	</div>

	<div class="flex items-center gap-1.5">
		<input type="checkbox" bind:checked={deleteDirectoryContents} />

		<div class="text-xs text-gray-500">
			{$i18n.t('Delete all contents inside this directory')}
		</div>
	</div>
</ConfirmDialog>

<ConfirmDialog
	bind:show={showResetConfirm}
	title={$i18n.t('Reset knowledge base?')}
	on:confirm={async () => {
		await resetKnowledgeById(localStorage.token, id);
		toast.success($i18n.t('Knowledge base has been reset'));
		init();
	}}
>
	<div class="text-sm text-gray-700 dark:text-gray-300 flex-1 line-clamp-3">
		{$i18n.t(
			'This will remove all files and directories from this knowledge base. This action cannot be undone.'
		)}
	</div>
</ConfirmDialog>
