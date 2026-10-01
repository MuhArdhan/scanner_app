/* Service Worker – Scan Delivery Note PWA
   Strategy: Cache-first for app shell, Network-only for API calls.
*/

const CACHE_NAME = 'scan-dn-v1';
const APP_SHELL = [
	'/scan-dn',
	'/scan-dn/',
	'/scan-dn/index.html',
	'/assets/scanner_app/scan-dn/manifest.json',
	'/assets/scanner_app/scan-dn/icon-192.png',
	'/assets/scanner_app/scan-dn/icon-512.png',
];

/* ── Install: pre-cache app shell ── */
self.addEventListener('install', event => {
	self.skipWaiting();
	event.waitUntil(
		caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL))
	);
});

/* ── Activate: remove old caches ── */
self.addEventListener('activate', event => {
	event.waitUntil(
		caches.keys().then(keys =>
			Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
		).then(() => self.clients.claim())
	);
});

/* ── Fetch ── */
self.addEventListener('fetch', event => {
	const url = new URL(event.request.url);

	// Always network for API calls
	if (url.pathname.startsWith('/api/')) {
		event.respondWith(fetch(event.request));
		return;
	}

	// Cache-first for app shell
	event.respondWith(
		caches.match(event.request).then(cached => {
			if (cached) return cached;
			return fetch(event.request).then(response => {
				// Cache successful GET responses for app shell URLs
				if (response.ok && event.request.method === 'GET') {
					const clone = response.clone();
					caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
				}
				return response;
			}).catch(() => caches.match('/scan-dn'));
		})
	);
});
