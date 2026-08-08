// build.py が生成。手で編集しても次のビルドで上書きされる。
var CACHE = "raidcp-87ef86451149";
var ASSETS = ["./", "./index.html", "./manifest.webmanifest",
              "./icon-180.png", "./icon-192.png", "./icon-512.png",
              "./icon-maskable-512.png"];

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE)
    .then(function (c) { return c.addAll(ASSETS); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  // 古いバージョンのキャッシュを捨てる
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.map(function (k) {
      return k === CACHE ? null : caches.delete(k);
    }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener("fetch", function (e) {
  if (e.request.method !== "GET") return;
  // 中身は完全に静的なので、キャッシュがあればそれを返す
  e.respondWith(caches.match(e.request).then(function (hit) {
    return hit || fetch(e.request);
  }));
});
