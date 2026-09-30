// Minimal offline shell cache; GET requests fall back to cache when offline.
const C = "skynex-v1";
self.addEventListener("install", e => e.waitUntil(caches.open(C).then(c => c.addAll(["/"]))));
self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  e.respondWith(fetch(e.request).then(r => { const x = r.clone(); caches.open(C).then(c => c.put(e.request, x)); return r; })
    .catch(() => caches.match(e.request)));
});
