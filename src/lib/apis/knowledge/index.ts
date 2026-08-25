import { WEBUI_API_BASE_URL } from '$lib/constants';

export const createNewKnowledge = async (
	token: string,
	name: string,
	description: string,
	accessGrants: object[]
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			name: name,
			description: description,
			access_grants: accessGrants
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getExternalKnowledgeConnections = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/connections`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createExternalKnowledgeConnection = async (token: string, connection: object) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/connections`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(connection)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateExternalKnowledgeConnection = async (
	token: string,
	id: string,
	connection: object
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/connections/${id}`, {
		method: 'PATCH',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(connection)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteExternalKnowledgeConnection = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/connections/${id}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const testExternalKnowledgeConnection = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/connections/${id}/test`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const testExternalKnowledgeRetrieval = async (
	token: string,
	id: string,
	payload: object
) => {
	let error = null;

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/external/connections/${id}/retrieve-test`,
		{
			method: 'POST',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			},
			body: JSON.stringify(payload)
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const testExternalKnowledgeSource = async (token: string, payload: object) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/source/test`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createExternalKnowledgeSource = async (token: string, payload: object) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/source/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateExternalKnowledgeSource = async (token: string, id: string, payload: object) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/source/${id}`, {
		method: 'PATCH',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const createExternalKnowledge = async (token: string, payload: object) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/external/knowledge/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(payload)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getKnowledgeBases = async (token: string = '', page: number | null = null) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (page) searchParams.append('page', page.toString());

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const searchKnowledgeBases = async (
	token: string = '',
	query: string | null = null,
	viewOption: string | null = null,
	page: number | null = null,
	source: string | null = null
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (query) searchParams.append('query', query);
	if (viewOption) searchParams.append('view_option', viewOption);
	if (source) searchParams.append('source', source);
	if (page) searchParams.append('page', page.toString());

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/search?${searchParams.toString()}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const searchKnowledgeFiles = async (
	token: string,
	query?: string | null,
	viewOption?: string | null,
	orderBy?: string | null,
	direction?: string | null,
	page: number = 1,
	includeContent: boolean = false
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (query) searchParams.append('query', query);
	if (viewOption) searchParams.append('view_option', viewOption);
	if (orderBy) searchParams.append('order_by', orderBy);
	if (direction) searchParams.append('direction', direction);
	searchParams.append('page', page.toString());
	if (includeContent) searchParams.append('include_content', 'true');

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/search/files?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getKnowledgeById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const searchKnowledgeFilesById = async (
	token: string,
	id: string,
	query?: string | null,
	viewOption?: string | null,
	orderBy?: string | null,
	direction?: string | null,
	page: number = 1,
	directoryId?: string | null,
	includeContent: boolean = false
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (query) searchParams.append('query', query);
	if (viewOption) searchParams.append('view_option', viewOption);
	if (orderBy) searchParams.append('order_by', orderBy);
	if (direction) searchParams.append('direction', direction);
	searchParams.append('page', page.toString());
	// directoryId: undefined = don't filter, null = root, string = specific dir
	if (directoryId !== undefined) {
		searchParams.append('directory_id', directoryId ?? '');
	}
	if (includeContent) searchParams.append('include_content', 'true');

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/${id}/files?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getPendingKnowledgeFiles = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/files/pending`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return [];
		});

	if (error) {
		throw error;
	}

	return res;
};

export const streamPendingKnowledgeFiles = async (token: string, id: string) => {
	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/files/pending?stream=true`, {
		method: 'GET',
		headers: {
			Accept: 'text/event-stream',
			authorization: `Bearer ${token}`
		}
	});

	if (!res.ok) {
		throw new Error('Failed to stream pending files');
	}

	return res;
};

type KnowledgeUpdateForm = {
	name?: string;
	description?: string;
	data?: object;
	access_grants?: object[];
};

export const updateKnowledgeById = async (token: string, id: string, form: KnowledgeUpdateForm) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			name: form?.name ? form.name : undefined,
			description: form?.description ? form.description : undefined,
			data: form?.data ? form.data : undefined,
			access_grants: form.access_grants
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateKnowledgeAccessGrants = async (
	token: string,
	id: string,
	accessGrants: any[]
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/access/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ access_grants: accessGrants })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * Attach an already-uploaded file to a knowledge base as a version awaiting review.
 *
 * Pass `documentId` to record the file as the next version of an existing document
 * instead of creating a new one; the backend rejects a document belonging to another
 * knowledge base. Either way the version is `pending` and reaches neither the vector
 * store nor the model until a Мастер-эксперт approves it.
 */
export const addFileToKnowledgeById = async (
	token: string,
	id: string,
	fileId: string,
	directoryId?: string | null,
	opts?: { documentId?: string | null; comment?: string | null }
) => {
	let error = null;

	const body: Record<string, string> = { file_id: fileId };
	if (directoryId) body.directory_id = directoryId;
	if (opts?.documentId) body.document_id = opts.documentId;
	if (opts?.comment) body.comment = opts.comment;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/file/add`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(body)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateFileFromKnowledgeById = async (token: string, id: string, fileId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/file/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			file_id: fileId
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const removeFileFromKnowledgeById = async (token: string, id: string, fileId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/file/remove`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			file_id: fileId
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const resetKnowledgeById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/reset`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const syncKnowledgeDiff = async (
	token: string,
	id: string,
	manifest: Array<{ filename: string; path: string; checksum: string; size: number }>
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/sync/diff`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ manifest })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const syncKnowledgeCleanup = async (
	token: string,
	id: string,
	fileIds: string[],
	dirIds: string[] = []
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/sync/cleanup`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ file_ids: fileIds, dir_ids: dirIds })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteKnowledgeById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/delete`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.then((json) => {
			return json;
		})
		.catch((err) => {
			error = err.detail;

			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const reindexKnowledgeFiles = async (token: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/reindex`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const exportKnowledgeById = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/export`, {
		method: 'GET',
		headers: {
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.blob();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

// ── Directory API ───────────────────────────────────────────────────

export const createKnowledgeDirectory = async (
	token: string,
	id: string,
	name: string,
	parentId?: string | null
) => {
	let error = null;

	const body: Record<string, string | null> = { name };
	if (parentId) body.parent_id = parentId;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/dirs/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(body)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const updateKnowledgeDirectory = async (
	token: string,
	id: string,
	dirId: string,
	form: { name?: string; parent_id?: string | null }
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/dirs/${dirId}/update`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(form)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const deleteKnowledgeDirectory = async (
	token: string,
	id: string,
	dirId: string,
	moveFiles: boolean = true
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	searchParams.append('move_files', moveFiles.toString());

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/${id}/dirs/${dirId}/delete?${searchParams.toString()}`,
		{
			method: 'DELETE',
			headers: {
				Accept: 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * Move a DOCUMENT into a directory.
 *
 * Separate from moveFileInKnowledge because that one keys on the published
 * file_id, and a document awaiting its first approval has none — knowledge_file.file_id
 * is NULL until a version is published, so the file-keyed route 404s on exactly
 * the documents an Эксперт most wants to file away. Same endpoint, different key.
 */
/**
 * The whole directory tree of a knowledge base, flat, each row carrying parent_id.
 *
 * Not the same as the `directories` on getKnowledgeDocuments — that is one level
 * and only on page 1, which is right for the registry and useless for a tree.
 */
export const getKnowledgeDirectories = async (token: string, id: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/dirs`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const moveDocumentInKnowledge = async (
	token: string,
	id: string,
	documentId: string,
	directoryId?: string | null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/file/move`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			document_id: documentId,
			directory_id: directoryId ?? null
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const moveFileInKnowledge = async (
	token: string,
	id: string,
	fileId: string,
	directoryId?: string | null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/file/move`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({
			file_id: fileId,
			directory_id: directoryId ?? null
		})
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

// ── Document registry & review ────────────────────────────────────────
//
// These target /knowledge/{id}/documents rather than /files. The two differ on
// purpose: /files answers "what is published" (and is what the model's
// search_knowledge tool uses), while /documents is the human-facing registry and
// includes revisions still awaiting review.

type KnowledgeDocumentQuery = {
	query?: string;
	status?: string;
	directoryId?: string | null;
	// Repeated, not comma-joined: a tag id may itself contain '/', and FastAPI
	// reads a repeated query param straight into list[str].
	tagIds?: string[];
	page?: number;
};

export const getKnowledgeDocuments = async (
	token: string,
	id: string,
	{ query, status, directoryId, tagIds, page }: KnowledgeDocumentQuery = {}
) => {
	let error = null;

	const searchParams = new URLSearchParams();
	if (query) searchParams.append('query', query);
	if (status) searchParams.append('status', status);
	// Only sent when scoping to a folder — omitted gives the flat list.
	if (directoryId !== undefined && directoryId !== null) {
		searchParams.append('directory_id', directoryId);
	}
	for (const tagId of tagIds ?? []) searchParams.append('tag_ids', tagId);
	if (page !== undefined) searchParams.append('page', `${page}`);

	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/${id}/documents?${searchParams.toString()}`,
		{
			method: 'GET',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			}
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

/**
 * Delete a document and its entire version history.
 *
 * Not the same as removing a file: this reaches documents that were never
 * approved, and it takes every revision with it. The backend allows it for the
 * document's creator, a Мастер-эксперт, or an admin.
 */
export const deleteKnowledgeDocument = async (token: string, id: string, documentId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/document/${documentId}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

/**
 * Delete a single revision, leaving the rest of the history in place.
 *
 * Allowed for the version's own author (an Эксперт withdrawing what they
 * proposed), a Мастер-эксперт, or an admin. The published version is refused —
 * use deleteKnowledgeDocument for that. Resolves to `{ deleted_document }`,
 * true when that was the document's last remaining version.
 */
export const deleteKnowledgeVersion = async (token: string, id: string, versionId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/version/${versionId}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) {
		throw error;
	}

	return res;
};

export const getDocumentVersions = async (token: string, id: string, documentId: string) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/document/${documentId}/versions`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

const reviewVersion = async (
	token: string,
	id: string,
	versionId: string,
	action: 'approve' | 'reject',
	reviewNote?: string | null
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/${id}/version/${versionId}/${action}`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify({ review_note: reviewNote ?? null })
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

export const approveVersion = (
	token: string,
	id: string,
	versionId: string,
	note?: string | null
) => reviewVersion(token, id, versionId, 'approve', note);

export const rejectVersion = (token: string, id: string, versionId: string, note?: string | null) =>
	reviewVersion(token, id, versionId, 'reject', note);

// ── Tags ──────────────────────────────────────────────────────────────
//
// The vocabulary is shared across the whole deployment rather than scoped to a
// knowledge base, so these live at /knowledge/tags rather than under an id.

export type KnowledgeTag = {
	id: string;
	label: string;
	description?: string | null;
	user_id?: string | null;
	// `aliases` / `code` / `deprecated` come from the canonical registry and are
	// carried for tag-aware retrieval; nothing in the UI reads them yet.
	meta?: {
		system?: boolean;
		group?: string;
		group_order?: number;
		code?: string;
		aliases?: string[];
		deprecated?: string[];
	} | null;
	created_at: number;
	updated_at: number;
	count?: number;
};

export const getKnowledgeTags = async (token: string): Promise<KnowledgeTag[]> => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/tags`, {
		method: 'GET',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

export const createKnowledgeTag = async (
	token: string,
	form: { label: string; id?: string; description?: string }
) => {
	let error = null;

	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/tags/create`, {
		method: 'POST',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		},
		body: JSON.stringify(form)
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

export const deleteKnowledgeTag = async (token: string, tagId: string) => {
	let error = null;

	// NOT encodeURIComponent: a tag id contains '/' as a real path separator and
	// the route is declared as {tag_id:path}. Encoding the slashes would send
	// %2F, which never matches.
	const res = await fetch(`${WEBUI_API_BASE_URL}/knowledge/tags/${tagId}`, {
		method: 'DELETE',
		headers: {
			Accept: 'application/json',
			'Content-Type': 'application/json',
			authorization: `Bearer ${token}`
		}
	})
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};

export const setKnowledgeDocumentTags = async (
	token: string,
	knowledgeId: string,
	documentId: string,
	tagIds: string[]
): Promise<KnowledgeTag[]> => {
	let error = null;

	// The complete set, not a delta — see DocumentTagsForm on the backend.
	const res = await fetch(
		`${WEBUI_API_BASE_URL}/knowledge/${knowledgeId}/document/${documentId}/tags`,
		{
			method: 'POST',
			headers: {
				Accept: 'application/json',
				'Content-Type': 'application/json',
				authorization: `Bearer ${token}`
			},
			body: JSON.stringify({ tag_ids: tagIds })
		}
	)
		.then(async (res) => {
			if (!res.ok) throw await res.json();
			return res.json();
		})
		.catch((err) => {
			error = err.detail;
			console.error(err);
			return null;
		});

	if (error) throw error;
	return res;
};
