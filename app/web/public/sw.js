// MediaShelf service worker.
//
// Scope: the whole app (served from the dist root). Two caches:
//   • SHELL — the static shell (HTML / hashed JS+CSS / fonts / icons) for
//     instant repeat loads and offline shell rendering.
//   • API   — read-only catalog responses (network-first) so the shelf, title
//     pages, services, and settings show LAST-KNOWN data when offline.
// Short-lived tokens, OAuth URLs, and downloads are never cached (see below),
// and mutations (POST/PUT/DELETE) are never touched — data stays live online.

const SHELL = "mediashelf-shell-v2";
const API = "mediashelf-api-v2";
const CURRENT = [SHELL, API];
const API_CACHE_LIMIT = 80;

// Requests whose responses must never be cached — they're volatile or sensitive.
function isUncacheableApi(pathname) {
  return (
    pathname.startsWith("/api/playback/") || // short-lived access tokens
    pathname.startsWith("/api/connect") || // OAuth authorize URLs
    pathname.startsWith("/api/backup/") || // DB export/import downloads
    pathname.includes("/opml/") // OPML file downloads
  );
}

// Precache the shell entry so the app can boot offline. Hashed assets referenced
// by index.html are cached lazily on first fetch (see below).
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.add("/")));
  self.skipWaiting();
});

// Drop caches from older versions, then take control of open clients.
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !CURRENT.includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

// Trim the API cache to a soft cap (oldest-first) so it can't grow unbounded.
async function trimApiCache() {
  const cache = await caches.open(API);
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - API_CACHE_LIMIT; i++) await cache.delete(keys[i]);
}

// Network-first: fresh online, last-known when the network fails.
async function apiNetworkFirst(request) {
  try {
    const res = await fetch(request);
    if (res.ok) {
      const copy = res.clone();
      const cache = await caches.open(API);
      await cache.put(request, copy);
      void trimApiCache();
    }
    return res;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ detail: "offline" }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin GETs. Cross-origin and non-GET (mutations) pass through.
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname === "/sw.js") return;

  // Read-only catalog API: network-first with an offline cache fallback, except
  // the volatile/sensitive endpoints, which always go straight to the network.
  if (url.pathname.startsWith("/api/")) {
    if (isUncacheableApi(url.pathname)) return;
    event.respondWith(apiNetworkFirst(request));
    return;
  }

  // Navigations: network-first so a new deploy wins online; fall back to the
  // cached shell (index.html) when offline.
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match("/", { ignoreSearch: true })));
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
            caches.open(SHELL).then((c) => c.put(request, copy));
          }
          return res;
        }),
    ),
  );
});
