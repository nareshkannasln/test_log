// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * The tester's local database.
 *
 * Every entry is written here before anything is sent to the site, and only removed
 * once the server has confirmed a Test Log for it. That ordering is what makes the
 * widget safe to use offline, on a flaky connection, or with the tab closed mid-send —
 * the queue is the record, the upload is just a chore that gets retried.
 *
 * Screenshots and recordings are stored as Blobs alongside the entry, so a queued
 * entry survives a browser restart with its evidence attached.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.store) return;

	const DB_NAME = "test_log_tester";
	const DB_VERSION = 1;
	const QUEUE = "queue";
	const META = "meta";

	let dbPromise = null;
	const memory = { queue: new Map(), meta: new Map() };
	let usingMemory = false;

	function openDatabase() {
		if (dbPromise) return dbPromise;

		dbPromise = new Promise((resolve, reject) => {
			if (!window.indexedDB) {
				reject(new Error("IndexedDB unavailable"));
				return;
			}

			const request = window.indexedDB.open(DB_NAME, DB_VERSION);

			request.onupgradeneeded = () => {
				const db = request.result;
				if (!db.objectStoreNames.contains(QUEUE)) {
					db.createObjectStore(QUEUE, { keyPath: "client_id" }).createIndex(
						"created_at",
						"created_at"
					);
				}
				if (!db.objectStoreNames.contains(META)) {
					db.createObjectStore(META, { keyPath: "key" });
				}
			};

			request.onsuccess = () => resolve(request.result);
			request.onerror = () => reject(request.error);
			request.onblocked = () => reject(new Error("IndexedDB blocked"));
		}).catch((error) => {
			// Private windows and locked-down browsers land here. Keep working in memory —
			// the queue then lives only as long as the tab, which we surface in the panel.
			usingMemory = true;
			console.warn("[test log] falling back to in-memory queue:", error.message);
			return null;
		});

		return dbPromise;
	}

	function transact(storeName, mode, work) {
		return openDatabase().then(
			(db) =>
				new Promise((resolve, reject) => {
					if (!db) {
						resolve(null);
						return;
					}

					const tx = db.transaction(storeName, mode);
					const store = tx.objectStore(storeName);
					let result;

					try {
						result = work(store);
					} catch (error) {
						reject(error);
						return;
					}

					tx.oncomplete = () => resolve(result && result.__box ? result.value : result);
					tx.onerror = () => reject(tx.error);
					tx.onabort = () => reject(tx.error);
				})
		);
	}

	/** IndexedDB hands results to callbacks, not promises — park one until the tx commits. */
	function wrap(request) {
		const box = { __box: true, value: undefined };
		request.onsuccess = () => (box.value = request.result);
		return box;
	}

	// ---------------------------------------------------------------- queue

	async function put(entry) {
		if (usingMemory || !(await openDatabase())) {
			memory.queue.set(entry.client_id, entry);
			return entry;
		}

		await transact(QUEUE, "readwrite", (store) => store.put(entry));
		return entry;
	}

	async function all() {
		if (usingMemory || !(await openDatabase())) {
			return [...memory.queue.values()].sort((a, b) => a.created_at - b.created_at);
		}

		const rows = await transact(QUEUE, "readonly", (store) => wrap(store.getAll()));
		return (rows || []).sort((a, b) => a.created_at - b.created_at);
	}

	async function get(clientId) {
		if (usingMemory || !(await openDatabase())) return memory.queue.get(clientId) || null;

		return (await transact(QUEUE, "readonly", (store) => wrap(store.get(clientId)))) || null;
	}

	async function patch(clientId, changes) {
		const entry = await get(clientId);
		if (!entry) return null;

		return put(Object.assign(entry, changes));
	}

	async function remove(clientId) {
		if (usingMemory || !(await openDatabase())) {
			memory.queue.delete(clientId);
			return;
		}

		await transact(QUEUE, "readwrite", (store) => store.delete(clientId));
	}

	async function count() {
		if (usingMemory || !(await openDatabase())) return memory.queue.size;

		return (await transact(QUEUE, "readonly", (store) => wrap(store.count()))) || 0;
	}

	// ---------------------------------------------------------------- meta (config cache, drafts)

	async function getMeta(key, fallback = null) {
		if (usingMemory || !(await openDatabase())) {
			return memory.meta.has(key) ? memory.meta.get(key) : fallback;
		}

		const row = await transact(META, "readonly", (store) => wrap(store.get(key)));
		return row ? row.value : fallback;
	}

	async function setMeta(key, value) {
		if (usingMemory || !(await openDatabase())) {
			memory.meta.set(key, value);
			return;
		}

		await transact(META, "readwrite", (store) => store.put({ key, value }));
	}

	NS.store = {
		put,
		get,
		all,
		patch,
		remove,
		count,
		getMeta,
		setMeta,
		isDurable: () => !usingMemory,
		ready: () => openDatabase(),
	};
})();
