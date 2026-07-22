// MediaShelf service worker — app-shell caching only (PWA installability).
//
// Scope: the whole app (served from the dist root). Caches the static shell
// (HTML / hashed JS+CSS / fonts / icons) for instant repeat loads and offline
// shell rendering. It NEVER caches API responses: /api/* passes straight to the
// network so catalog, settings, and playback data always stay live.

const CACHE = "mediashelf-shell-v1";

// Precache the shell entry so the app can boot offline. Hashed assets referenced
// by index.html are cached lazily on first fetch (see below).
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.add("/")));
  self.skipWaiting();
});

// Drop caches from older versions, then take control of open clients.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GETs. Cross-origin and non-GET pass through.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;

  // Live data and the SW itself are never cached.
  if (url.pathname.startsWith("/api/") || url.pathname === "/sw.js") return;

  // Navigations: network-first so a new deploy wins online; fall back to the
  // cached shell (index.html) when offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/", { ignoreSearch: true })),
    );
    return;
  }

  // Static assets (hashed /assets/*, icons, fonts): cache-first, filling the
  // cache on first fetch. Content-hashed names make stale entries harmless.
  event.respondWith(
    caches.match(request).then(
      (hit) =>
        hit ||
        fetch(request).then((res) => {
          if (res.ok && res.type === "basic") {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy));
          }
          return res;
        }),
    ),
  );
});
