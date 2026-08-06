#!/usr/bin/env python3
"""公開データを取得して src/godata.json（アプリに埋め込むコンパクトJSON）を作る。

  python3 fetch_data.py           # ダウンロードして再生成
  python3 fetch_data.py --cache   # .cache/ の既存ファイルを使う

出典:
  pokedex.json ... https://pokemon-go-api.github.io/pokemon-go-api/  (種族値・技・多言語名)
  game_master  ... https://github.com/PokeMiners/game_masters        (CPM表)
"""
import collections, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(HERE, "src", "godata.json")

SOURCES = {
    "pokedex.json": "https://pokemon-go-api.github.io/pokemon-go-api/api/pokedex.json",
    "gm.json": "https://raw.githubusercontent.com/PokeMiners/game_masters/master/latest/latest.json",
}


def load(name, use_cache):
    path = os.path.join(CACHE, name)
    if not (use_cache and os.path.exists(path)):
        os.makedirs(CACHE, exist_ok=True)
        print("downloading", name, "...")
        urllib.request.urlretrieve(SOURCES[name], path)
    return json.load(io.open(path, encoding="utf-8"))


use_cache = "--cache" in sys.argv
dex = load("pokedex.json", use_cache)
gm = load("gm.json", use_cache)

types, type_index = [], {}
moves, move_ids, move_index = {}, [], {}


def type_idx(t):
    if not t:
        return -1
    key = t["type"]
    if key not in type_index:
        type_index[key] = len(types)
        types.append(t["names"]["Japanese"])
    return type_index[key]


def move_idx(m):
    mid = m["id"]
    if mid not in move_index:
        move_index[mid] = len(move_ids)
        move_ids.append(mid)
        moves[mid] = [
            m["names"]["Japanese"],
            type_idx(m["type"]),
            m.get("power") or 0,
            m.get("energy") or 0,
            m.get("durationMs") or 0,
        ]
    return move_index[mid]


CLASS_MAP = {
    None: 0,
    "POKEMON_CLASS_LEGENDARY": 1,
    "POKEMON_CLASS_MYTHIC": 2,
    "POKEMON_CLASS_ULTRA_BEAST": 3,
}


def entry(p):
    st = p.get("stats")
    if not st:
        return None
    def ids(key):
        return sorted(move_idx(m) for m in (p.get(key) or {}).values())
    return [
        p["formId"], p["names"]["Japanese"], p["names"]["English"], p["dexNr"],
        st["attack"], st["defense"], st["stamina"],
        type_idx(p["primaryType"]), type_idx(p["secondaryType"]),
        CLASS_MAP.get(p.get("pokemonClass"), 0),
        ids("quickMoves"), ids("cinematicMoves"),
        ids("eliteQuickMoves"), ids("eliteCinematicMoves"),
    ]


pokemon, seen = [], set()
species_of = {}   # formId -> 種のid（DARMANITAN_GALARIAN_ZEN -> DARMANITAN）
for p in dex:
    for cand in [p] + list((p.get("regionForms") or {}).values()):
        e = entry(cand)
        if e and e[0] not in seen:
            seen.add(e[0])
            species_of[e[0]] = cand["id"]
            pokemon.append(e)

# --- 元データで日本語のフォーム名が抜けているものを補う ----------------------
# メテノは「りゅうせいのすがた（種族値 116/194/155）」と「コアのすがた（218/131/155）」で
# CP が変わるが、元データはコアの色違い7種のうち一部しか名前を付けていない。
# 色はCPに影響しないので、すがた単位の名前に揃えて下の統合処理でまとめる。
NAME_OVERRIDE = {"MINIOR": "メテノ (りゅうせいのすがた)"}
for c in ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "INDIGO", "VIOLET"]:
    NAME_OVERRIDE["MINIOR_" + c] = "メテノ (コアのすがた)"

for e in pokemon:
    if e[0] in NAME_OVERRIDE:
        e[1] = NAME_OVERRIDE[e[0]]

# --- 見た目だけのフォームを統合する -----------------------------------------
# ゲームデータには RAIKOU / RAIKOU_S、UNOWN_A〜Z、メテノの色違いなど、
# 種族値もタイプも同じで CP がまったく変わらないフォームが並んでいる。
# CP を引くアプリでは区別できないので 1 件にまとめる。
# 代表はデータが最も充実したもの（覚える技が多いもの）を採用する。
def cp_signature(e):
    return (e[1], e[3], e[4], e[5], e[6], e[7], e[8], e[9])  # 名前/図鑑No/種族値/タイプ/分類


merged = {}
for e in pokemon:
    key = cp_signature(e)
    cur = merged.get(key)
    if cur is None or (len(e[10]) + len(e[11]) + len(e[12]) + len(e[13])) > \
                      (len(cur[10]) + len(cur[11]) + len(cur[12]) + len(cur[13])):
        merged[key] = e
pokemon = list(merged.values())

# --- ゲームデータのテンプレート行を落とす -----------------------------------
# 「DARMANITAN」と「DARMANITAN_STANDARD（ノーマルモード）」のように、
# 素の formId とその既定フォームが同じ内容で二重に入っていることがある。
# 種族値・タイプ・分類が一致し、技も既定フォーム側に全部含まれるときだけ素の方を捨てる。
bydex = {}
for e in pokemon:
    bydex.setdefault(e[3], []).append(e)

redundant = set()
for group in bydex.values():
    for a in group:
        for b in group:
            if a is b or not b[0].startswith(a[0] + "_"):
                continue
            if (a[4], a[5], a[6], a[7], a[8], a[9]) != (b[4], b[5], b[6], b[7], b[8], b[9]):
                continue
            if all(set(a[k]) <= set(b[k]) for k in (10, 11, 12, 13)):
                redundant.add(a[0])
                break
pokemon = [e for e in pokemon if e[0] not in redundant]

# --- 残った同名フォームに日本語のフォーム名を付ける --------------------------
# 元データはギラティナ（オリジンフォルム）のように括弧付きで名前が入っている
# ことが多いが、ヒスイ・パルデアなど一部は素の名前のままで区別が付かない。
FORM_LABEL = {
    "ALOLA": "アローラのすがた",
    "GALARIAN": "ガラルのすがた",
    "GALARIAN_STANDARD": "ガラルのすがた",
    "GALARIAN_ZEN": "ガラルのすがた・ダルマモード",
    "HISUIAN": "ヒスイのすがた",
    "PALDEA": "パルデアのすがた",
    "ICE_RIDER": "はくばじょうのすがた",
    "SHADOW_RIDER": "こくばじょうのすがた",
    "PLANT": "くさきのミノ",
    "SANDY": "すながちのミノ",
    "TRASH": "ゴミのミノ",
}

groups = {}
for e in pokemon:
    groups.setdefault((e[1], e[3]), []).append(e)

unlabeled = set()
for (name, _dex), members in groups.items():
    if len(members) < 2:
        continue
    for m in members:
        # formId から種のid を取り除いた残りがフォーム名にあたる
        base_id = species_of[m[0]]
        suffix = m[0][len(base_id):].lstrip("_") if m[0].startswith(base_id) else m[0]
        if not suffix:
            continue  # 素のフォームはそのままの名前にしておく
        label = FORM_LABEL.get(suffix)
        if label is None:
            label = suffix
            unlabeled.add(suffix)
        m[1] = name + " (" + label + ")"

if unlabeled:
    print("!! 日本語フォーム名が未登録:", sorted(unlabeled), "→ FORM_LABEL に追加してください")

# 統合とラベル付けのあとで名前が衝突していないか確認する
dupe = [k for k, v in collections.Counter((e[1], e[3]) for e in pokemon).items() if v > 1]
if dupe:
    sys.exit("同名のエントリが残っています: %r" % dupe)

pokemon.sort(key=lambda e: (e[3], e[0]))

cpm = None
for e in gm:
    d = e.get("data", {})
    if "playerLevel" in d:
        cpm = d["playerLevel"]["cpMultiplier"]
        break
if not cpm:
    sys.exit("game_master から cpMultiplier が取れませんでした")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(
    {"types": types, "moves": [moves[m] for m in move_ids],
     "moveIds": move_ids, "pokemon": pokemon, "cpm": cpm},
    io.open(OUT, "w", encoding="utf-8"),
    ensure_ascii=False, separators=(",", ":"),
)
print("src/godata.json", f"{os.path.getsize(OUT):,} bytes /",
      len(pokemon), "種 /", len(move_ids), "技 / CPM Lv20 =", cpm[19])
print("  CPが同じフォームを統合:", len(seen) - len(merged), "件 /",
      "テンプレート行を削除:", len(redundant), "件")
