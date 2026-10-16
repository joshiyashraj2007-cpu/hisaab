// Keeps the app shell on the phone. API calls and audio always go to the laptop.
const CACHE = "hisaab-v2";
const SHELL = ["/", "/index.html", "/style.css", "/app.js", "/verify.html", "/claim.html",
               "/manifest.json", "/icon-192.png", "/icon-512.png"];

self.addEventListener("install", e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname.startsWith("/audio/")) return;
  // Network first, so code changes show at once; cached copy when the laptop is unreachable.
  e.respondWith(fetch(e.request)
    .then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; })
    .catch(() => caches.match(e.request)));
});
