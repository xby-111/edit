(function(global) {
    const DB_NAME = 'mobile_offline_drafts';
    const STORE_NAME = 'drafts';
    const INDEXEDDB_SUPPORTED = !!window.indexedDB;
    let db = null;

    function openDb() {
        return new Promise((resolve, reject) => {
            if (!INDEXEDDB_SUPPORTED) return resolve(null);
            const req = window.indexedDB.open(DB_NAME, 1);
            req.onerror = () => resolve(null);
            req.onsuccess = () => resolve(req.result);
            req.onupgradeneeded = (event) => {
                const database = event.target.result;
                if (!database.objectStoreNames.contains(STORE_NAME)) {
                    database.createObjectStore(STORE_NAME, { keyPath: 'key' });
                }
            };
        });
    }

    async function ensureDb() {
        if (db !== null) return db;
        db = await openDb();
        return db;
    }

    async function saveDraft(key, payload) {
        const database = await ensureDb();
        if (database) {
            return new Promise((resolve) => {
                const tx = database.transaction([STORE_NAME], 'readwrite');
                tx.objectStore(STORE_NAME).put({ ...payload, key });
                tx.oncomplete = () => resolve(true);
                tx.onerror = () => resolve(false);
            });
        }
        localStorage.setItem(key, JSON.stringify(payload));
        return true;
    }

    async function loadDraft(key) {
        const database = await ensureDb();
        if (database) {
            return new Promise((resolve) => {
                const tx = database.transaction([STORE_NAME], 'readonly');
                const req = tx.objectStore(STORE_NAME).get(key);
                req.onsuccess = () => resolve(req.result || null);
                req.onerror = () => resolve(null);
            });
        }
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : null;
    }

    async function deleteDraft(key) {
        const database = await ensureDb();
        if (database) {
            return new Promise((resolve) => {
                const tx = database.transaction([STORE_NAME], 'readwrite');
                tx.objectStore(STORE_NAME).delete(key);
                tx.oncomplete = () => resolve(true);
                tx.onerror = () => resolve(false);
            });
        }
        localStorage.removeItem(key);
        return true;
    }

    async function listDraftsByUser(userId) {
        const database = await ensureDb();
        const drafts = [];
        if (database) {
            return new Promise((resolve) => {
                const tx = database.transaction([STORE_NAME], 'readonly');
                const req = tx.objectStore(STORE_NAME).openCursor();
                req.onsuccess = (event) => {
                    const cursor = event.target.result;
                    if (cursor) {
                        if (cursor.value.user_id === userId) drafts.push(cursor.value);
                        cursor.continue();
                    } else {
                        resolve(drafts);
                    }
                };
                req.onerror = () => resolve(drafts);
            });
        }
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (!key.startsWith('offline_draft_')) continue;
            const data = JSON.parse(localStorage.getItem(key));
            if (data && data.user_id === userId) drafts.push(data);
        }
        return drafts;
    }

    global.OfflineDrafts = {
        saveDraft,
        loadDraft,
        deleteDraft,
        listDraftsByUser,
    };
})(window);
