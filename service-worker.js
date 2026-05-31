const CACHE_VERSION = "conlecta-pwa-v2";
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/qr-display.html",
  "/manifest.webmanifest",
  "/styles.css",
  "/theme-pack.css",
  "/theme-engine.js",
  "/app.js",
  "/qr-display.js",
  "/qris-frame.js",
  "/pwa.js",
  "/assets/ConlectaTabLogo.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
      .catch(() => null),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key)),
      ))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/assets/videos/")) return;
  if (url.pathname.startsWith("/assets/Brand/")) return;
  if (url.pathname.startsWith("/assets/Payment/")) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;
      return fetch(request)
        .then((response) => {
          if (!response || response.status !== 200 || response.type !== "basic") return response;
          const copy = response.clone();
          caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy)).catch(() => null);
          return response;
        })
        .catch(() => cached);
    }),
  );
});
