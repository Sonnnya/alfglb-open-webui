// One definition of what a knowledge-base drag carries, shared by every producer
// and every drop target.
//
// It used to be three hand-rolled copies of the same JSON.parse + try/catch — one
// in DirectoryRow, one in KnowledgeBreadcrumbs, one inline in DocumentRegistry —
// which is why adding the sidebar tree as a drop target would otherwise have
// meant a fourth. Drop targets now only decide *where* the thing lands; what is
// being dragged is read here.
//
// The mime strings are unchanged: components on both ends already agree on them,
// and renaming them buys nothing.

export const KB_DOCUMENT_MIME = 'application/x-kb-file-move';
export const KB_DIRECTORY_MIME = 'application/x-kb-dir-move';

/**
 * The payload key is `fileId` for history: the registry used to drag published
 * file ids. It now drags DOCUMENT ids — a document awaiting its first approval
 * has no published file, and filing one away is the single most likely thing an
 * Эксперт does. Readers below hand back a document id whatever the key is called.
 */
type DocumentPayload = { fileId?: string; documentId?: string };
type DirectoryPayload = { dirId?: string };

const read = <T>(dataTransfer: DataTransfer | null | undefined, mime: string): T | null => {
	const raw = dataTransfer?.getData(mime);
	if (!raw) return null;
	try {
		return JSON.parse(raw) as T;
	} catch {
		return null;
	}
};

export const setDocumentDrag = (dataTransfer: DataTransfer | null, documentId: string) => {
	dataTransfer?.setData(KB_DOCUMENT_MIME, JSON.stringify({ fileId: documentId }));
};

export const setDirectoryDrag = (dataTransfer: DataTransfer | null, directoryId: string) => {
	dataTransfer?.setData(KB_DIRECTORY_MIME, JSON.stringify({ dirId: directoryId }));
};

export const readDocumentDrag = (dataTransfer: DataTransfer | null | undefined): string | null =>
	read<DocumentPayload>(dataTransfer, KB_DOCUMENT_MIME)?.fileId ??
	read<DocumentPayload>(dataTransfer, KB_DOCUMENT_MIME)?.documentId ??
	null;

export const readDirectoryDrag = (dataTransfer: DataTransfer | null | undefined): string | null =>
	read<DirectoryPayload>(dataTransfer, KB_DIRECTORY_MIME)?.dirId ?? null;

/**
 * Whether this drag is one of ours, from `types` alone.
 *
 * Must be answerable during `dragover`, where getData() returns '' by spec —
 * the payload is only readable on drop. Every drop target needs this to decide
 * whether to preventDefault (i.e. whether to accept the drop at all).
 */
export const isKnowledgeDrag = (dataTransfer: DataTransfer | null | undefined): boolean =>
	!!dataTransfer &&
	(dataTransfer.types.includes(KB_DOCUMENT_MIME) || dataTransfer.types.includes(KB_DIRECTORY_MIME));
