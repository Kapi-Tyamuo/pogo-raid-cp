#!/usr/bin/env python3
"""公開データを取得して src/godata.json（アプリに埋め込むコンパクトJSON）を作る。

  python3 fetch_data.py           # ダウンロードして再生成
  python3 fetch_data.py --cache   # .cache/ の既存ファイルを使う

出典:
  pokedex.json ... https://pokemon-go-api.github.io/pokemon-go-api/  (種族値・技・多言語名・世代)
  game_master  ... https://github.com/PokeMiners/game_masters        (CPM表・専用技・メガ)

実装済みかどうかは、ゲームマスターの pokemonSettings に 3Dモデルの設定
(modelScaleV2) があるかで判定する。Niantic は未実装のポケモンの数値も
先行して配信しているが、モデル設定は実際にゲームへ入るまで付かない。
（pogoapi.net の released_pokemon.json は古く、ミミッキュやアルセウスを
未実装としてしまうため使わない。pvpoke の released は PvP 対象かどうかの
意味なのでこれも使えない。）
"""
import collections, io, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, ".cache")
OUT = os.path.join(HERE, "src", "godata.json")

SOURCES = {
    "pokedex.json": "https://pokemon-go-api.github.io/pokemon-go-api/api/pokedex.json",
    "gm.json": "https://raw.githubusercontent.com/PokeMiners/game_masters/master/latest/latest.json",
    # 専用技は pokedex.json に載らないことがあり、その場合ゲームマスターから
    # 拾うことになるが、あちらに日本語名は入っていないのでこれで補う。
    "i18n_ja.json": "https://raw.githubusercontent.com/PokeMiners/pogo_assets/master/Texts/Latest%20APK/JSON/i18n_japanese.json",
}


def load(name, use_cache):
    path = os.path.join(CACHE, name)
    if not (use_cache and os.path.exists(path)):
        os.makedirs(CACHE, exist_ok=True)
        print("downloading", name, "...")
        # pogoapi.net は Python の既定 User-Agent を 403 で弾くので名乗っておく
        req = urllib.request.Request(SOURCES[name], headers={"User-Agent": "pogo-raid-cp/1.0"})
        with urllib.request.urlopen(req) as r, io.open(path, "wb") as f:
            f.write(r.read())
    return json.load(io.open(path, encoding="utf-8"))


use_cache = "--cache" in sys.argv
dex = load("pokedex.json", use_cache)
gm = load("gm.json", use_cache)

# ["キー", "訳", "キー", "訳", ...] の平坦な配列で来る
_i18n_raw = load("i18n_ja.json", use_cache)["data"]
I18N = dict(zip(_i18n_raw[0::2], _i18n_raw[1::2]))

# 3Dモデルの設定を持つ形態＝ゲームに入っている、とみなす。
# ニドラン♀♂は formId が共通なので、種のid でも引けるようにしておく。
modeled = set()
for _e in gm:
    _ps = _e.get("data", {}).get("pokemonSettings")
    if _ps and _ps.get("modelScaleV2") is not None:
        modeled.add(_ps["pokemonId"])
        if _ps.get("form"):
            modeled.add(_ps["form"])


def is_released(form_id, species_id):
    return 1 if (form_id in modeled or species_id in modeled) else 0

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


# --- 専用技 ------------------------------------------------------------------
# ガリョウテンセイやきょじゅうざんのような専用技は pokedex.json の技リストに
# 入っておらず、ゲームマスター側の別の場所に散らばっている。
#   nonTmCinematicMoves                     … わざマシンで覚えられない技（レックウザ）
#   formChange[].moveReassignment           … フォルム変更時の技の入れ替え
#     existingMoves    … そのテンプレート自身が持つ技
#     replacementMoves … 変更先のフォルムが得る技
GM_MOVES = {}          # 技id -> (番号, moveSettings)
for _e in gm:
    _ms = _e.get("data", {}).get("moveSettings")
    if _ms:
        _num = _e["templateId"].split("_")[0].lstrip("V")
        GM_MOVES[_ms["movementId"]] = (_num, _ms)

signature = collections.defaultdict(set)   # formId -> 技idの集合
for _e in gm:
    ps = _e.get("data", {}).get("pokemonSettings")
    if not ps:
        continue
    me = ps.get("form") or ps["pokemonId"]
    for mv in (ps.get("nonTmCinematicMoves") or []):
        signature[me].add(mv)
    for fc in (ps.get("formChange") or []):
        for pair in ((fc.get("moveReassignment") or {}).get("cinematicMoves") or []):
            for mv in pair.get("existingMoves") or []:
                signature[me].add(mv)
            for other in (fc.get("availableForm") or []):
                for mv in pair.get("replacementMoves") or []:
                    signature[other].add(mv)

# ときのほうこう・あくうせつだんはゲームマスターのどのポケモンにも紐づいていないが、
# 技の定義（冒険効果つき）は入っていて、ゲームにも実装されている。
# データ側の抜けなので、ここで補う。
signature["DIALGA_ORIGIN"].add("ROAR_OF_TIME")
signature["PALKIA_ORIGIN"].add("SPACIAL_REND")


def gm_move_idx(move_id):
    """ゲームマスターの技を技テーブルに登録して添字を返す。日本語名は i18n から。"""
    if move_id in move_index:
        return move_index[move_id]
    got = GM_MOVES.get(move_id)
    if not got:
        return None
    num, ms = got
    name = I18N.get("move_name_" + num)
    if not name:
        return None
    move_index[move_id] = len(move_ids)
    move_ids.append(move_id)
    moves[move_id] = [
        name,
        type_index.get(ms.get("pokemonType"), -1),
        int(ms.get("power") or 0),
        int(ms.get("energyDelta") or 0),
        int(ms.get("durationMs") or 0),
    ]
    return move_index[move_id]


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
        p.get("generation") or 0,
        is_released(p["formId"], p["id"]),
        0,   # メガシンカ種別（0=通常 / 1=メガシンカ / 2=ゲンシカイキ）
        [],  # 専用技（あとで埋める）
    ]


# --- メガシンカ・ゲンシカイキ -----------------------------------------------
# ゲームマスターでは pokemonSettings.tempEvoOverrides（種族値・タイプ）に入っている。
#
# 実装状況は判定しない。使えそうな材料は temporaryEvolutionSettings の
# assetBundleValue だけだが、ゲームマスターが2026-04で止まっているため、
# それ以降に来たメガ（メガミュウツーX/Y、メガライチュウX/Y など）を
# 未実装と誤判定してしまう。Z-A のメガでも早期に来たメガカイリュー・
# メガウツボット・メガカラマネロは判定できるので、単に情報が古いだけ。
# 誤ったバッジを出すより出さない方がましなので、メガは一律で実装済み扱いにする。
# （通常フォームの判定は pokemonSettings.modelScaleV2 を見ており、こちらは有効。
#  tempEvoOverrides の modelScaleV2 は基準と違う拡大率のときだけ付くので使えない。）
def mega_entry(base, m, base_moves):
    """メガは技を持たない（元の姿の技をそのまま使う）ので、技は base から借りる。"""
    st = m.get("stats")
    if not st:
        return None
    mid = m["id"]
    kind = 2 if mid.endswith("_PRIMAL") else 1
    return [
        mid, m["names"]["Japanese"], m["names"]["English"], base["dexNr"],
        st["attack"], st["defense"], st["stamina"],
        type_idx(m["primaryType"]), type_idx(m["secondaryType"]),
        CLASS_MAP.get(base.get("pokemonClass"), 0),
        base_moves[0], base_moves[1], base_moves[2], base_moves[3],
        base.get("generation") or 0,
        1,      # 上のとおり、メガは実装状況を判定しない
        kind,
        [],     # 専用技（メガは元の姿のものを下で引き継ぐ）
    ]


# 素の ZACIAN / ZAMAZENTA は「れきせんのゆうしゃ」の種族値・技に「けんのおう／
# たてのおう」のタイプが付いたテンプレート行で、ゲームには存在しない姿。
# 残すとタブが「基本」と「れきせんのゆうしゃ」に分かれてしまうので落とす。
DROP_FORMS = {"ZACIAN", "ZAMAZENTA"}

# レイドで捕まえるのはこの姿なので、一覧の代表とタブの先頭に置く
# （名前に括弧が付いているため、そのままだと五十音順で「けんのおう」が先になる）。
PREFERRED_FIRST = {"ZACIAN_HERO", "ZAMAZENTA_HERO"}

pokemon, seen = [], set()
megas = []        # メガは整理処理の対象外なので別に持っておく
species_of = {}   # formId -> 種のid（DARMANITAN_GALARIAN_ZEN -> DARMANITAN）
for p in dex:
    for cand in [p] + list((p.get("regionForms") or {}).values()):
        e = entry(cand)
        if e and e[0] not in seen and e[0] not in DROP_FORMS:
            seen.add(e[0])
            species_of[e[0]] = cand["id"]
            pokemon.append(e)
    base_e = entry(p)
    if base_e:
        for m in (p.get("megaEvolutions") or {}).values():
            me = mega_entry(p, m, (base_e[10], base_e[11], base_e[12], base_e[13]))
            if me and me[0] not in seen:
                seen.add(me[0])
                megas.append(me)

# --- 元データで日本語のフォーム名が抜けているものを補う ----------------------
# メテノは「りゅうせいのすがた（種族値 116/194/155）」と「コアのすがた（218/131/155）」で
# CP が変わるが、元データはコアの色違い7種のうち一部しか名前を付けていない。
# 色はCPに影響しないので、すがた単位の名前に揃えて下の統合処理でまとめる。
NAME_OVERRIDE = {"MINIOR": "メテノ (りゅうせいのすがた)"}
for c in ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "INDIGO", "VIOLET"]:
    NAME_OVERRIDE["MINIOR_" + c] = "メテノ (コアのすがた)"

# 元データは基本フォルムだけ素の名前にしている。他のフォルムと並ぶと
# 詳細画面のタブが「基本」になってしまうので、実際の呼び名を入れておく。
# ヒスイ・ガラルなどは「基本」で意味が通るのでそのままにする。
NAME_OVERRIDE.update({
    "DEOXYS": "デオキシス (ノーマルフォルム)",
    "ARCEUS": "アルセウス (ノーマルタイプ)",
    "SILVALLY": "シルヴァディ (タイプ：ノーマル)",
    "ROTOM": "ロトム (ノーマルロトム)",
    "CASTFORM": "ポワルン (ノーマルのすがた)",
    "MEOWSTIC": "ニャオニクス (オス)",
    "OINKOLOGNE": "パフュートン (オスのすがた)",
})

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
before_merge = len(pokemon)
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
            if a[15] and not b[15]:
                continue  # 実装済みの基本形を、未実装のフォームのために捨てない（ウッウなど）
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

# --- 専用技を割り当てる ------------------------------------------------------
# すでに通常技・スペシャル技・レガシーに入っているものは除く。
# （ザシアンの formChange には IRON_HEAD も出てくるが、これは普通の技）
sig_count = 0
for e in pokemon:
    known = set(e[10]) | set(e[11]) | set(e[12]) | set(e[13])
    got = []
    for mv in sorted(signature.get(e[0], ())):
        mi = gm_move_idx(mv)
        if mi is not None and mi not in known:
            got.append(mi)
    e[17] = got
    sig_count += len(got)

# メガは技を持たないので、元の姿の専用技をそのまま引き継ぐ（メガレックウザの
# ガリョウテンセイなど）。base_moves と同じ考え方。
_sig_by_form = {e[0]: e[17] for e in pokemon}
for e in megas:
    for suf in ("_MEGA_X", "_MEGA_Y", "_PRIMAL", "_MEGA"):
        if e[0].endswith(suf):
            e[17] = list(_sig_by_form.get(e[0][:-len(suf)], []))
            break

# メガは整理処理（統合・テンプレート削除・フォーム名の補完）を通さずに足す。
# 名前が重複しないうえ、通常フォームと混ぜて判定すると意味が変わってしまうため。
pokemon += megas

# 図鑑番号順。メガは同じ番号の中でいちばん後ろに置いて、タブの末尾に出す。
pokemon.sort(key=lambda e: (e[3], 1 if e[16] else 0,
                            0 if e[0] in PREFERRED_FIRST else 1, e[0]))

# --- 強化コスト --------------------------------------------------------------
# POKEMON_UPGRADE_SETTINGS。配列は「レベルの整数部 - 1」で引く。
# upgradesPerLevel=2 なので、1段階＝0.5レベル。同じレベル内の2回は同額。
#   stardustCost[floor(L)-1]  … そのレベルからの1段階に要るほしのすな
#   candyCost[floor(L)-1]     … 同じくアメ（Lv40以上は0で、代わりにXLアメ）
#   xlCandyCost[floor(L)-40]  … Lv40以上の1段階に要るXLアメ
upgrade = None
for e in gm:
    u = e.get("data", {}).get("pokemonUpgrades")
    if u and "OVERRIDE" not in e["templateId"]:
        upgrade = {
            "dust": u["stardustCost"],
            "candy": u["candyCost"],
            "xl": u["xlCandyCost"],
            "xlFrom": u["xlCandyMinPokemonLevel"],
            "maxLevel": u["maxNormalUpgradeLevel"],
            "perLevel": u["upgradesPerLevel"],
            "shadowDust": u["shadowStardustMultiplier"],
            "shadowCandy": u["shadowCandyMultiplier"],
            "purifiedDust": u["purifiedStardustMultiplier"],
            "purifiedCandy": u["purifiedCandyMultiplier"],
        }
        break

# キラはほしのすなだけ割引（アメは変わらない）
for e in gm:
    lp = e.get("data", {}).get("luckyPokemonSettings")
    if lp:
        upgrade["luckyDust"] = lp["powerUpStardustDiscountPercent"]
        break
if not upgrade:
    sys.exit("game_master から強化コストが取れませんでした")

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
     "moveIds": move_ids, "pokemon": pokemon, "cpm": cpm, "upgrade": upgrade},
    io.open(OUT, "w", encoding="utf-8"),
    ensure_ascii=False, separators=(",", ":"),
)
print("src/godata.json", f"{os.path.getsize(OUT):,} bytes /",
      len(pokemon), "種 /", len(move_ids), "技 / CPM Lv20 =", cpm[19])
print("  CPが同じフォームを統合:", before_merge - len(merged), "件 /",
      "テンプレート行を削除:", len(redundant), "件 /",
      "専用技:", sig_count, "件")
