#!/usr/bin/env python3
"""src/body.html + データ を配布用のファイルにまとめる。

出力:
  index.html     ... 単体で開ける完全な HTML（AirDrop してオフラインで使う用）
  artifact.html  ... Artifact 公開用（doctype / html / head / body タグなし）
  docs/          ... GitHub Pages 用の PWA 一式
                     index.html / manifest.webmanifest / sw.js / アイコン

データの再取得:
  python3 fetch_data.py
"""
import hashlib, io, json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
DIST = os.path.join(HERE, "docs")   # GitHub Pages の "main / docs" 公開に合わせる
DATA = os.path.join(SRC, "godata.json")

TITLE = "レイド捕獲CP検索 | Pokémon GO"
SHORT = "レイドCP"
DESC = "ポケモンGOのレイド報酬ポケモンの捕獲CP範囲・個体値逆引き・おぼえる技をすぐ引ける早見アプリ"
THEME = "#0d1017"
FAVICON = "⚡"  # ⚡

body = io.open(os.path.join(SRC, "body.html"), encoding="utf-8").read()
data = io.open(DATA, encoding="utf-8").read().strip()

if "__DATA__" not in body:
    sys.exit("src/body.html に __DATA__ プレースホルダがありません")
# JSON を <script> に埋めるので、閉じタグだけエスケープしておく
page = body.replace("__DATA__", data.replace("</", "<\\/"))

# --- Artifact 用（body の中身だけ） -----------------------------------------
io.open(os.path.join(HERE, "artifact.html"), "w", encoding="utf-8").write(
    "<title>" + TITLE + "</title>\n" + page)

# --- HTML の組み立て --------------------------------------------------------
EMOJI_ICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E"
    "%3Ctext y='.9em' font-size='90'%3E" + FAVICON + "%3C/text%3E%3C/svg%3E"
)


def html(head_extra, body_extra=""):
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{DESC}">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="{THEME}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{SHORT}">
<title>{TITLE}</title>
{head_extra}
<style>html,body{{margin:0;padding:0}}</style>
</head>
<body>
{page}
{body_extra}
</body>
</html>
"""


# --- 単体 HTML（file:// で開く用。外部ファイルを一切参照しない） --------------
standalone = html(f'<link rel="icon" href="{EMOJI_ICON}">\n'
                  f'<link rel="apple-touch-icon" href="{EMOJI_ICON}">')
io.open(os.path.join(HERE, "index.html"), "w", encoding="utf-8").write(standalone)

# --- PWA（docs/） -----------------------------------------------------------
ICONS = [("icon-180.png", "icon.svg", 180),
         ("icon-192.png", "icon.svg", 192),
         ("icon-512.png", "icon.svg", 512),
         ("icon-maskable-512.png", "icon-maskable.svg", 512)]

if os.path.isdir(DIST):
    shutil.rmtree(DIST)
os.makedirs(DIST)

for name, svg, size in ICONS:
    out = os.path.join(DIST, name)
    subprocess.run(["sips", "-s", "format", "png", os.path.join(SRC, svg), "--out", out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sips", "-z", str(size), str(size), out],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

pwa_head = """<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon-192.png">
<link rel="apple-touch-icon" href="icon-180.png">"""

pwa_body = """<script>
// 初回だけ通信して端末にキャッシュし、以降はオフラインで動かす。
// file:// で開いたときは Service Worker を使えないので黙って諦める。
if ("serviceWorker" in navigator && location.protocol.indexOf("http") === 0) {
  // すでに Service Worker に載っているページだけ、入れ替わりを見張る。
  // 初回訪問時は controller が無く、claim されるだけで載せ替えではないので何もしない。
  if (navigator.serviceWorker.controller) {
    var reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", function () {
      // 新しい版が有効になった時点で読み直す。これをしないと、内容を更新しても
      // 次に開いたときはまだ古いキャッシュが表示されてしまう。
      if (reloading) return;
      reloading = true;
      location.reload();
    });
  }
  addEventListener("load", function () {
    navigator.serviceWorker.register("sw.js").catch(function () {});
  });
}
</script>"""

pwa_html = html(pwa_head, pwa_body)
io.open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(pwa_html)

# キャッシュ名は配信する HTML そのもののハッシュから作る。アプリ本体だけでなく
# SW 登録スクリプトなどラッパー側を直したときも必ず変わるようにしておく
# （sw.js 自身はハッシュの対象に入らないので循環しない）。
version = hashlib.sha256(pwa_html.encode("utf-8")).hexdigest()[:12]

manifest = {
    "name": TITLE,
    "short_name": SHORT,
    "description": DESC,
    "start_url": ".",
    "scope": ".",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": THEME,
    "theme_color": THEME,
    "lang": "ja",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
         "purpose": "maskable"},
    ],
}
json.dump(manifest, io.open(os.path.join(DIST, "manifest.webmanifest"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

sw = """// build.py が生成。手で編集しても次のビルドで上書きされる。
var CACHE = "raidcp-%s";
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
""" % version
io.open(os.path.join(DIST, "sw.js"), "w", encoding="utf-8").write(sw)

# GitHub Pages に Jekyll 処理をさせない
io.open(os.path.join(DIST, ".nojekyll"), "w", encoding="utf-8").write("")

d = json.loads(data)
print("index.html   ", f"{os.path.getsize(os.path.join(HERE, 'index.html')):,} bytes")
print("artifact.html", f"{os.path.getsize(os.path.join(HERE, 'artifact.html')):,} bytes")
print("docs/         ", ", ".join(sorted(os.listdir(DIST))))
print("キャッシュ版:", version, "/ ポケモン", len(d["pokemon"]), "種 /", len(d["moves"]), "技")
