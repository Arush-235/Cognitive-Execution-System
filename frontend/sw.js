const CACHE = 'ces-v1';
const ASSETS = ['/', '/style.css', '/app.js', '/manifest.json'];

self.addEventListener('install', (e) => {
    e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)));
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    const url = new URL(e.request.url);
    // Don't cache API calls
    if (url.pathname.startsWith('/ingest') ||
        url.pathname.startsWith('/approve') ||
        url.pathname.startsWith('/next') ||
        url.pathname.startsWith('/complete') ||
        url.pathname.startsWith('/override') ||
        url.pathname.startsWith('/plan') ||
        url.pathname.startsWith('/inbox')) {
        return;
    }
    e.respondWith(
        caches.match(e.request).then(r => r || fetch(e.request))
    );
});
