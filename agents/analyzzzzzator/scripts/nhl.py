#!/usr/bin/env python3
"""NHL: локальная база всех матчей (1917 → сейчас) и анализ тоталов. Только stdlib.

Источники: api.nhle.com/stats/rest (все матчи и счёт), api-web.nhle.com (протоколы, расписание).
База: data/nhl.sqlite (пересобирается командой sync).

Команды:
  sync        обновить базу: справочники, текущий и прошлый сезоны (+ --history: все сезоны с 1917, + --details: броски и голы по периодам)
  league      базовые частоты лиги: средний тотал, % 6+, % ≤4, распределение
  team        профиль тоталов команды: дом/выезд, 6+/≤4, over/under 5.5/6.5, форма, броски
  h2h         история противостояний (все сезоны, по франшизам), с поправкой на эпоху
  match       модель матча (гость @ хозяин): λ, вероятности 6+/≤4, over/under, честные коэффициенты, value по коэффициентам
  slate       все матчи дня с моделью, сортировка по потенциалу 6+ или ≤4
  backtest    проверка модели v2 на сезоне walk-forward: Brier против константы, калибровка
  calibrate   обучить калибровку модели v2 на последних сезонах (раз в неделю)
"""
import argparse
import datetime as dt
import json
import math
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "data", "nhl.sqlite")
STATS = "https://api.nhle.com/stats/rest/en"
WEB = "https://api-web.nhle.com/v1"
GT = {2: "RS", 3: "PO"}


# ---------------- infra ----------------
def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "analyzzzzzator/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript("""
    CREATE TABLE IF NOT EXISTS teams(id INTEGER PRIMARY KEY, franchise_id INTEGER, tricode TEXT, name TEXT);
    CREATE TABLE IF NOT EXISTS franchises(id INTEGER PRIMARY KEY, name TEXT);
    CREATE TABLE IF NOT EXISTS games(
      id INTEGER PRIMARY KEY, season INTEGER, game_type INTEGER, date TEXT, start_et TEXT,
      home_id INTEGER, away_id INTEGER, home_score INTEGER, away_score INTEGER,
      last_period INTEGER, state INTEGER);
    CREATE INDEX IF NOT EXISTS g_season ON games(season);
    CREATE INDEX IF NOT EXISTS g_teams ON games(home_id, away_id);
    CREATE INDEX IF NOT EXISTS g_date ON games(date);
    CREATE TABLE IF NOT EXISTS details(
      game_id INTEGER PRIMARY KEY, home_sog INTEGER, away_sog INTEGER,
      h1 INTEGER, a1 INTEGER, h2 INTEGER, a2 INTEGER, h3 INTEGER, a3 INTEGER, hot INTEGER, aot INTEGER);
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS box(game_id INTEGER PRIMARY KEY, home_sog INTEGER, away_sog INTEGER);
    CREATE TABLE IF NOT EXISTS goalies(game_id INTEGER, team_id INTEGER, player_id INTEGER, name TEXT, starter INTEGER,
      toi INTEGER, sa INTEGER, sv INTEGER, ga INTEGER, PRIMARY KEY(game_id, player_id));
    CREATE INDEX IF NOT EXISTS gk_team ON goalies(team_id);
    """)
    return c


def current_season(today=None):
    d = today or dt.date.today()
    y = d.year if d.month >= 8 else d.year - 1
    return y * 10000 + y + 1


def prev_season(s):
    y = s // 10000 - 1
    return y * 10000 + y + 1


def season_label(s):
    return f"{s // 10000}/{str(s % 10000)[2:]}"


# ------------- derived scores -------------
def finished(g):
    return g["state"] == 7 and g["home_score"] is not None


def reg_scores(g):
    """Голы основного времени. OT/SO-победа даёт +1 победителю; старые ничьи — без изменений."""
    h, a, p = g["home_score"], g["away_score"], g["last_period"] or 3
    if p >= 4 and h != a:
        m = min(h, a)
        return m, m
    return h, a


def totals(g):
    h, a = g["home_score"], g["away_score"]
    rh, ra = reg_scores(g)
    return h + a, rh + ra


def result_tag(g):
    p = g["last_period"] or 3
    if g["home_score"] == g["away_score"]:
        return "ничья"
    if p == 5 and g["game_type"] == 2:
        return "Б"
    if p >= 4:
        return "ОТ"
    return ""


# ------------------ sync ------------------
def sync_refs(c):
    teams = get(f"{STATS}/team")["data"]
    c.executemany("INSERT OR REPLACE INTO teams VALUES(?,?,?,?)",
                  [(t["id"], t["franchiseId"], t["triCode"], t["fullName"]) for t in teams])
    fr = get(f"{STATS}/franchise")["data"]
    c.executemany("INSERT OR REPLACE INTO franchises VALUES(?,?)", [(f["id"], f["fullName"]) for f in fr])


def sync_season(c, season):
    q = urllib.parse.quote(f"season={season} and (gameType=2 or gameType=3)")
    data = get(f"{STATS}/game?cayenneExp={q}&limit=-1")["data"]
    rows = [(g["id"], g["season"], g["gameType"], g["gameDate"], g.get("easternStartTime"),
             g["homeTeamId"], g["visitingTeamId"],
             g.get("homeScore") if g.get("gameStateId") == 7 else None,
             g.get("visitingScore") if g.get("gameStateId") == 7 else None,
             g.get("period"), g.get("gameStateId")) for g in data]
    c.executemany("INSERT OR REPLACE INTO games VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def sync_details(c, season, limit=None):
    ids = [r[0] for r in c.execute(
        "SELECT g.id FROM games g LEFT JOIN details d ON d.game_id=g.id WHERE g.season=? AND g.state=7 AND d.game_id IS NULL",
        (season,))]
    if limit:
        ids = ids[:limit]
    for i, gid in enumerate(ids, 1):
        try:
            d = get(f"{WEB}/gamecenter/{gid}/landing")
        except Exception as e:  # noqa
            print(f"  ! {gid}: {e}", file=sys.stderr)
            continue
        per = {(1, True): 0, (1, False): 0, (2, True): 0, (2, False): 0, (3, True): 0, (3, False): 0, ("OT", True): 0, ("OT", False): 0}
        for p in d.get("summary", {}).get("scoring", []):
            pd = p["periodDescriptor"]
            key = pd["number"] if pd.get("periodType") == "REG" else ("OT" if pd.get("periodType") == "OT" else None)
            if key is None:
                continue
            for gl in p["goals"]:
                per[(key, bool(gl.get("isHome")))] += 1
        c.execute("INSERT OR REPLACE INTO details VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (gid, d["homeTeam"].get("sog"), d["awayTeam"].get("sog"),
                   per[(1, True)], per[(1, False)], per[(2, True)], per[(2, False)],
                   per[(3, True)], per[(3, False)], per[("OT", True)], per[("OT", False)]))
        if i % 50 == 0:
            c.commit()
            print(f"  протоколы: {i}/{len(ids)}", file=sys.stderr)
    return len(ids)


def toi_sec(t):
    try:
        m, sec = t.split(":")
        return int(m) * 60 + int(sec)
    except Exception:  # noqa
        return 0


def sync_box(c, season, workers=8):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ids = [r[0] for r in c.execute(
        "SELECT g.id FROM games g LEFT JOIN box b ON b.game_id=g.id WHERE g.season=? AND g.state=7 AND b.game_id IS NULL ORDER BY g.date",
        (season,))]
    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(get, f"{WEB}/gamecenter/{gid}/boxscore"): gid for gid in ids}
        for f in as_completed(futs):
            gid = futs[f]
            try:
                d = f.result()
            except Exception as e:  # noqa
                print(f"  ! {gid}: {e}", file=sys.stderr)
                continue
            c.execute("INSERT OR REPLACE INTO box VALUES(?,?,?)", (gid, d["homeTeam"].get("sog"), d["awayTeam"].get("sog")))
            for side in ("homeTeam", "awayTeam"):
                tid = d[side]["id"]
                for gk in d.get("playerByGameStats", {}).get(side, {}).get("goalies", []):
                    c.execute("INSERT OR REPLACE INTO goalies VALUES(?,?,?,?,?,?,?,?,?)",
                              (gid, tid, gk["playerId"], gk["name"]["default"], 1 if gk.get("starter") else 0,
                               toi_sec(gk.get("toi", "0:0")), gk.get("shotsAgainst") or 0, gk.get("saves") or 0, gk.get("goalsAgainst") or 0))
            done += 1
            if done % 200 == 0:
                c.commit()
                print(f"  {season_label(season)} протоколы: {done}/{len(ids)} ({time.time() - t0:.0f} с)", file=sys.stderr, flush=True)
    c.commit()
    return done


def cmd_sync(a):
    c = db()
    sync_refs(c)
    cur = a.season or current_season()
    seasons = [cur, prev_season(cur)]
    if a.history:
        seasons = [y * 10000 + y + 1 for y in range(1917, cur // 10000 + 1)]
    tot = 0
    for s in seasons:
        n = sync_season(c, s)
        tot += n
        if a.history and n:
            print(f"  {season_label(s)}: {n}", file=sys.stderr)
    c.commit()
    nd = 0
    if a.details:
        nd = sync_details(c, cur)
        c.commit()
    for bs in (a.boxscores or []):
        nd += sync_box(c, bs if bs > 10000 else cur)
    c.execute("INSERT OR REPLACE INTO meta VALUES('synced_at', ?)", (dt.datetime.now().isoformat(timespec="seconds"),))
    c.commit()
    n_all = c.execute("SELECT COUNT(*), MIN(season), MAX(season) FROM games WHERE state=7").fetchone()
    print(f"Синхронизировано матчей: {tot}; протоколов: {nd}. В базе сыгранных: {n_all[0]:,} (сезоны {season_label(n_all[1])}–{season_label(n_all[2])})")


# ---------------- helpers ----------------
def team_by_code(c, code, season=None):
    code = code.upper()
    season = season or current_season()
    r = c.execute("""SELECT t.* FROM teams t JOIN games g ON (g.home_id=t.id OR g.away_id=t.id)
                     WHERE t.tricode=? AND g.season=? LIMIT 1""", (code, season)).fetchone()
    if not r:
        r = c.execute("SELECT * FROM teams WHERE tricode=? ORDER BY id DESC LIMIT 1", (code,)).fetchone()
    if not r:
        raise SystemExit(f"Команда '{code}' не найдена. Коды: " + ", ".join(sorted({x['tricode'] for x in c.execute(
            'SELECT DISTINCT t.tricode FROM teams t JOIN games g ON g.home_id=t.id WHERE g.season=?', (season,))})))
    return r


def code_of(c, tid, cache={}):
    if tid not in cache:
        r = c.execute("SELECT tricode FROM teams WHERE id=?", (tid,)).fetchone()
        cache[tid] = r[0] if r else str(tid)
    return cache[tid]


def games(c, where="1=1", params=(), order="date"):
    return [dict(r) for r in c.execute(f"SELECT * FROM games WHERE state=7 AND {where} ORDER BY {order}", params)]


def pct(n, d):
    return f"{n / d:.0%}" if d else "—"


def total_profile(gs, high, low):
    n = len(gs)
    if not n:
        return None
    ft = [totals(g)[0] for g in gs]
    rt = [totals(g)[1] for g in gs]
    return {
        "n": n, "avg": sum(ft) / n, "avg_reg": sum(rt) / n,
        "high": sum(t >= high for t in ft), "low": sum(t <= low for t in ft),
        "o55": sum(t > 5.5 for t in ft), "o65": sum(t > 6.5 for t in ft),
        "high_reg": sum(t >= high for t in rt), "low_reg": sum(t <= low for t in rt),
        "ot": sum((g["last_period"] or 3) >= 4 for g in gs),
    }


def fmt_profile(p, high, low, label=""):
    if not p:
        return f"{label}нет матчей"
    n = p["n"]
    return (f"{label}{n} матчей · тотал {p['avg']:.2f} (осн. время {p['avg_reg']:.2f}) · "
            f"{high}+: {pct(p['high'], n)} · ≤{low}: {pct(p['low'], n)} · ТБ5.5: {pct(p['o55'], n)} · ТБ6.5: {pct(p['o65'], n)} · "
            f"ОТ/Б: {pct(p['ot'], n)}")


# ---------------- league ----------------
def cmd_league(a):
    c = db()
    s = a.season or current_season()
    gs = games(c, "season=? AND game_type=2", (s,))
    p = total_profile(gs, a.high, a.low)
    print(f"НХЛ {season_label(s)}, регулярка: " + fmt_profile(p, a.high, a.low))
    if gs:
        h = sum(g["home_score"] for g in gs) / len(gs)
        aw = sum(g["away_score"] for g in gs) / len(gs)
        print(f"Голы за матч: хозяева {h:.2f}, гости {aw:.2f}")
        dist = {}
        for g in gs:
            t = totals(g)[0]
            dist[t] = dist.get(t, 0) + 1
        print("Распределение тотала (с ОТ/Б): " + "  ".join(f"{k}:{dist[k]}" for k in sorted(dist)))
    if a.trend:
        print("\nТренд по сезонам (регулярка):")
        for (ss,) in c.execute("SELECT DISTINCT season FROM games WHERE state=7 AND game_type=2 ORDER BY season DESC LIMIT ?", (a.trend,)):
            pp = total_profile(games(c, "season=? AND game_type=2", (ss,)), a.high, a.low)
            print(f"  {season_label(ss)}: тотал {pp['avg']:.2f}, {a.high}+ {pct(pp['high'], pp['n'])}, ≤{a.low} {pct(pp['low'], pp['n'])} ({pp['n']} матчей)")


# ---------------- team ----------------
def cmd_team(a):
    c = db()
    s = a.season or current_season()
    t = team_by_code(c, a.team, s)
    gs = games(c, "season=? AND game_type=2 AND (home_id=? OR away_id=?)", (s, t["id"], t["id"]))
    print(f"{t['name']} ({t['tricode']}), {season_label(s)}")
    print(fmt_profile(total_profile(gs, a.high, a.low), a.high, a.low, "Всего: "))
    home = [g for g in gs if g["home_id"] == t["id"]]
    away = [g for g in gs if g["away_id"] == t["id"]]
    print(fmt_profile(total_profile(home, a.high, a.low), a.high, a.low, "Дома:  "))
    print(fmt_profile(total_profile(away, a.high, a.low), a.high, a.low, "В гостях: "))
    if gs:
        gf = sum(g["home_score"] if g["home_id"] == t["id"] else g["away_score"] for g in gs) / len(gs)
        ga = sum(g["away_score"] if g["home_id"] == t["id"] else g["home_score"] for g in gs) / len(gs)
        rgf = sum(reg_scores(g)[0] if g["home_id"] == t["id"] else reg_scores(g)[1] for g in gs) / len(gs)
        rga = sum(reg_scores(g)[1] if g["home_id"] == t["id"] else reg_scores(g)[0] for g in gs) / len(gs)
        print(f"Забивает {gf:.2f} / пропускает {ga:.2f} за матч (в осн. время {rgf:.2f} / {rga:.2f})")
        det = [dict(r) for r in c.execute(
            f"SELECT d.*, g.home_id FROM details d JOIN games g ON g.id=d.game_id WHERE g.id IN ({','.join(str(g['id']) for g in gs)})")]
        if det:
            sf = sum(d["home_sog"] if d["home_id"] == t["id"] else d["away_sog"] for d in det) / len(det)
            sa = sum(d["away_sog"] if d["home_id"] == t["id"] else d["home_sog"] for d in det) / len(det)
            p1 = sum(d["h1"] + d["a1"] for d in det) / len(det)
            print(f"Броски: {sf:.1f} / {sa:.1f} за матч; голов в 1-м периоде (обе команды): {p1:.2f}  [протоколов: {len(det)}]")
    last = gs[-a.last:]
    if last:
        print(f"\nПоследние {len(last)}:")
        for g in last:
            ishome = g["home_id"] == t["id"]
            opp = code_of(c, g["away_id"] if ishome else g["home_id"])
            gf_, ga_ = (g["home_score"], g["away_score"]) if ishome else (g["away_score"], g["home_score"])
            ft, rt = totals(g)
            tag = result_tag(g)
            print(f"  {g['date']} {'vs' if ishome else ' @'} {opp}  {gf_}:{ga_} {tag:<3} тотал {ft}" + (f" (осн. {rt})" if rt != ft else ""))
        pl = total_profile(last, a.high, a.low)
        print(fmt_profile(pl, a.high, a.low, "Форма: "))


# ---------------- h2h ----------------
def league_avg_by_season(c):
    out = {}
    for r in c.execute("SELECT season, AVG(home_score+away_score) FROM games WHERE state=7 AND game_type=2 GROUP BY season"):
        out[r[0]] = r[1]
    return out


def h2h_games(c, A, B, by_team=False, since=None, playoffs=True, seasons=None):
    if by_team:
        ida, idb = [A["id"]], [B["id"]]
    else:
        ida = [r[0] for r in c.execute("SELECT id FROM teams WHERE franchise_id=?", (A["franchise_id"],))]
        idb = [r[0] for r in c.execute("SELECT id FROM teams WHERE franchise_id=?", (B["franchise_id"],))]
    qa, qb = ",".join(map(str, ida)), ",".join(map(str, idb))
    where = f"((home_id IN ({qa}) AND away_id IN ({qb})) OR (home_id IN ({qb}) AND away_id IN ({qa})))"
    where += "" if playoffs else " AND game_type=2"
    params = ()
    if since:
        where += " AND season>=?"
        params = (since * 10000 + since + 1,)
    elif seasons:
        first = current_season() - 10001 * (seasons - 1)
        where += " AND season>=?"
        params = (first,)
    return games(c, where, params), set(ida), set(idb)


def cmd_h2h(a):
    c = db()
    A, B = team_by_code(c, a.team_a), team_by_code(c, a.team_b)
    seasons = None if (a.all or a.since) else a.seasons
    gs, ida, idb = h2h_games(c, A, B, a.by_team, a.since, not a.no_playoffs, seasons)
    scope = "команде" if a.by_team else "франшизам (вкл. прежние названия)"
    period = f"с {a.since}" if a.since else ("вся история с 1917" if a.all else f"последние {a.seasons} сезона ({season_label(current_season() - 10001 * (a.seasons - 1))}–{season_label(current_season())})")
    print(f"История: {A['tricode']} — {B['tricode']} · по {scope} · {period}")
    if not gs:
        print("Встреч нет.")
        return
    wa = sum((g["home_score"] > g["away_score"]) == (g["home_id"] in ida) and g["home_score"] != g["away_score"] for g in gs)
    ties = sum(g["home_score"] == g["away_score"] for g in gs)
    print(f"{len(gs)} матчей ({gs[0]['date'][:4]}–{gs[-1]['date'][:4]}): победы {A['tricode']} {wa}, {B['tricode']} {len(gs) - wa - ties}, ничьи {ties}; "
          f"плей-офф: {sum(g['game_type'] == 3 for g in gs)}")
    print(fmt_profile(total_profile(gs, a.high, a.low), a.high, a.low, "Все встречи: "))
    lav = league_avg_by_season(c)
    rel = [totals(g)[0] / lav[g["season"]] for g in gs if lav.get(g["season"])]
    if rel:
        print(f"Тотал относительно лиги в те же сезоны: ×{sum(rel) / len(rel):.2f} (1.00 = как в среднем по лиге; учитывает эпохи)")
    cur = current_season()
    recent = [g for g in gs if g["season"] >= cur - 50005] if (a.all or a.since) else gs
    if a.all or a.since:
        print(fmt_profile(total_profile(recent, a.high, a.low), a.high, a.low, "Последние 5 сезонов: "))
    for side, ids in ((A, ida), (B, idb)):
        hs = [g for g in recent if g["home_id"] in ids]
        print(fmt_profile(total_profile(hs, a.high, a.low), a.high, a.low, f"  на площадке {side['tricode']}: "))
    print(f"\nПоследние {min(a.last, len(gs))} встреч:")
    for g in gs[-a.last:]:
        ft, rt = totals(g)
        print(f"  {g['date']} {GT.get(g['game_type'], '')} {code_of(c, g['away_id'])} {g['away_score']} @ {code_of(c, g['home_id'])} {g['home_score']} "
              f"{result_tag(g):<5} тотал {ft}" + (f" (осн. {rt})" if rt != ft else ""))


# ---------------- model ----------------
def fit(c, season, before=None, k=12.0, prior_w=0.5, iters=6):
    """Рейтинги атаки/обороны по голам основного времени, с поправкой на соперника, дом/выезд,
    байесовским сжатием к прошлому сезону (prior_w — доля «памяти» о прошлом сезоне)."""
    where, params = "season=? AND game_type=2", [season]
    if before:
        where += " AND date<?"
        params.append(before)
    gs = games(c, where, tuple(params))
    prev = games(c, "season=? AND game_type=2", (prev_season(season),))
    base_gs = gs if len(gs) >= 150 else gs + prev
    if not base_gs:
        raise SystemExit("Нет данных — запустите: python3 scripts/nhl.py sync")
    mh = sum(reg_scores(g)[0] for g in base_gs) / len(base_gs)
    ma = sum(reg_scores(g)[1] for g in base_gs) / len(base_gs)
    tie = sum(reg_scores(g)[0] == reg_scores(g)[1] for g in base_gs) / len(base_gs)

    def solve(gl, prior=None):
        teams = {x for g in gl for x in (g["home_id"], g["away_id"])}
        att = {t: 1.0 for t in teams}
        de = {t: 1.0 for t in teams}
        for _ in range(iters):
            gf = {t: 0.0 for t in teams}; ef = {t: 0.0 for t in teams}
            ga = {t: 0.0 for t in teams}; ea = {t: 0.0 for t in teams}
            for g in gl:
                h, a_ = g["home_id"], g["away_id"]
                rh, ra = reg_scores(g)
                gf[h] += rh; ef[h] += mh * de[a_]
                gf[a_] += ra; ef[a_] += ma * de[h]
                ga[h] += ra; ea[h] += ma * att[a_]
                ga[a_] += rh; ea[a_] += mh * att[h]
            b = (mh + ma) / 2
            for t in teams:
                pa = 1.0 if not prior or t not in prior[0] else 1 + prior_w * (prior[0][t] - 1)
                pd = 1.0 if not prior or t not in prior[1] else 1 + prior_w * (prior[1][t] - 1)
                att[t] = (gf[t] + k * b * pa) / (ef[t] + k * b)
                de[t] = (ga[t] + k * b * pd) / (ea[t] + k * b)
        return att, de

    prior = solve(prev) if prev else None
    att, de = solve(gs, prior) if gs else prior
    ngp = {}
    for g in gs:
        for x in (g["home_id"], g["away_id"]):
            ngp[x] = ngp.get(x, 0) + 1
    return {"att": att, "def": de, "mh": mh, "ma": ma, "tie_base": tie, "n": len(gs), "gp": ngp}


def pois(l, kmax=16):
    p = [math.exp(-l)]
    for k in range(1, kmax + 1):
        p.append(p[-1] * l / k)
    return p


def predict(m, home, away):
    lh = m["mh"] * m["att"].get(home, 1) * m["def"].get(away, 1)
    la = m["ma"] * m["att"].get(away, 1) * m["def"].get(home, 1)
    ph, pa = pois(lh), pois(la)
    reg = [0.0] * 34
    tie = 0.0
    tie_k = [0.0] * 34
    for i, x in enumerate(ph):
        for j, y in enumerate(pa):
            reg[i + j] += x * y
            if i == j:
                tie += x * y
                tie_k[i + j] += x * y
    fin = [0.0] * 35
    for k in range(34):
        fin[k] += reg[k] - tie_k[k]
        fin[k + 1] += tie_k[k]
    win_h = sum(x * y for i, x in enumerate(ph) for j, y in enumerate(pa) if i > j)
    return {"lh": lh, "la": la, "reg": reg, "fin": fin, "tie": tie, "win_h_reg": win_h, "win_a_reg": 1 - win_h - tie}


def cum(dist, cond):
    return sum(p for k, p in enumerate(dist) if cond(k))


def fair(p):
    return f"{1 / p:.2f}" if p > 0.001 else "—"


def parse_odds(items):
    out = {}
    for it in items or []:
        k, v = it.split("=")
        out[k.strip().lower()] = float(v)
    return out


def played_yesterday(c, team_id, date):
    y = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    return c.execute("SELECT 1 FROM games WHERE date=? AND (home_id=? OR away_id=?) AND game_type IN (2,3)", (y, team_id, team_id)).fetchone() is not None


def predict_v2(c, season, home, away, date, home_goalie=None, away_goalie=None):
    import nhl_model as M
    cal = M.load_calibration(c)
    if not cal:
        return None
    M.P.update(cal.get("params", {}))
    m = M.fit(c, season, before=date)
    if not m:
        return None
    if home_goalie:
        gh, gh_name = M.goalie_by_name(c, home, home_goalie); gh_src = "указан"
    else:
        gh, gh_name = M.likely_starter(c, home, season, date); gh_src = "вероятный"
    if away_goalie:
        ga, ga_name = M.goalie_by_name(c, away, away_goalie); ga_src = "указан"
    else:
        ga, ga_name = M.likely_starter(c, away, season, date); ga_src = "вероятный"
    b2h, b2a = played_yesterday(c, home, date), played_yesterday(c, away, date)
    lh, la, sh, sa = M.lambdas(m, home, away, gh, ga, b2h, b2a, tuple(cal["b2b"]))
    reg, fin = M.dist(cal, lh + la)
    tie = sum(reg[k] * float(cal["tie"].get(str(k), 0)) for k in range(len(reg)))
    gsv = lambda pid: 1 - (1 - (1 - m["conv_h"] / 1)) if False else None
    return dict(lh=lh, la=la, sh=sh, sa=sa, reg=reg + [0.0] * 14, fin=fin + [0.0] * 14, tie=tie, n=m["n"],
                goalies=((gh_name, gh_src, m["gfac"].get(gh)), (ga_name, ga_src, m["gfac"].get(ga))), b2b=(b2h, b2a), model="v2")


def cmd_match(a):
    c = db()
    s = current_season()
    A = team_by_code(c, a.away, s)   # гость
    H = team_by_code(c, a.home, s)   # хозяин
    date = a.date or dt.date.today().isoformat()
    m = fit(c, s, k=a.prior_games)
    p = None if a.v1 else predict_v2(c, s, H["id"], A["id"], date, a.home_goalie, a.away_goalie)
    if p is None:
        p = predict(m, H["id"], A["id"])
        p["model"] = "v1 (голы, пуассон; нет калибровки — запустите calibrate)"
    fin, reg = p["fin"], p["reg"]
    hi, lo = a.high, a.low
    print(f"{A['tricode']} @ {H['tricode']} · {date} · модель {p['model']} · сезон {season_label(s)} "
          f"(сыграно: {A['tricode']} {m['gp'].get(A['id'], 0)}, {H['tricode']} {m['gp'].get(H['id'], 0)})")
    if p["model"] == "v2":
        (hn, hs_, hf), (an, as_, af) = p["goalies"]
        fmt_g = lambda n_, s_, f_: f"{n_ or '?'} ({s_}{', пропускает ×%.2f к среднему' % f_ if f_ else ''})"
        print(f"Вратари: {H['tricode']} — {fmt_g(hn, hs_, hf)}; {A['tricode']} — {fmt_g(an, as_, af)}")
        print(f"Back-to-back: {H['tricode']} {'да' if p['b2b'][0] else 'нет'}, {A['tricode']} {'да' if p['b2b'][1] else 'нет'}; "
              f"ожидаемые броски {H['tricode']} {p['sh']:.1f} — {A['tricode']} {p['sa']:.1f}")
    print(f"Ожидаемые голы (осн. время): {H['tricode']} {p['lh']:.2f} — {A['tricode']} {p['la']:.2f}; тотал {p['lh'] + p['la']:.2f}; "
          f"P(ничья в осн. время → ОТ/Б) {p['tie']:.0%}")
    rows = [
        (f"Много: {hi}+ (вкл. ОТ/Б)", cum(fin, lambda k: k >= hi)),
        (f"Мало: ≤{lo} (вкл. ОТ/Б)", cum(fin, lambda k: k <= lo)),
        ("ТБ 5.5", cum(fin, lambda k: k > 5.5)), ("ТМ 5.5", cum(fin, lambda k: k < 5.5)),
        ("ТБ 6.5", cum(fin, lambda k: k > 6.5)), ("ТМ 6.5", cum(fin, lambda k: k < 6.5)),
        ("ТБ 4.5", cum(fin, lambda k: k > 4.5)), ("ТМ 4.5", cum(fin, lambda k: k < 4.5)),
        (f"{hi}+ в осн. время", cum(reg, lambda k: k >= hi)), (f"≤{lo} в осн. время", cum(reg, lambda k: k <= lo)),
    ]
    odds = parse_odds(a.odds)
    keymap = {"tb5.5": "ТБ 5.5", "tm5.5": "ТМ 5.5", "tb6.5": "ТБ 6.5", "tm6.5": "ТМ 6.5", "tb4.5": "ТБ 4.5", "tm4.5": "ТМ 4.5",
              "o5.5": "ТБ 5.5", "u5.5": "ТМ 5.5", "o6.5": "ТБ 6.5", "u6.5": "ТМ 6.5", "o4.5": "ТБ 4.5", "u4.5": "ТМ 4.5"}
    inv = {}
    for k, v in odds.items():
        if k in keymap:
            inv[keymap[k]] = v
    print(f"\n{'Рынок':<26}{'Вероятность':>12}{'Честный кф':>12}" + (f"{'Кф БК':>9}{'EV':>8}{'¼ Келли':>9}" if inv else ""))
    for name, pr in rows:
        line = f"{name:<26}{pr:>11.1%}{fair(pr):>12}"
        if name in inv:
            o = inv[name]
            ev = pr * o - 1
            kel = max(0.0, (pr * o - 1) / (o - 1)) / 4 if o > 1 else 0
            line += f"{o:>9.2f}{ev:>+8.1%}{kel:>8.1%}" + ("  ✅ value" if ev > a.min_edge else "")
        print(line)
    if len({"ТБ 5.5", "ТМ 5.5"} & set(inv)) == 2:
        o1, o2 = inv["ТБ 5.5"], inv["ТМ 5.5"]
        marg = 1 / o1 + 1 / o2 - 1
        print(f"Маржа БК на линии 5.5: {marg:.1%}; без маржи: ТБ {1 / o1 / (1 + marg):.1%} / ТМ {1 / o2 / (1 + marg):.1%}")
    print("\nРаспределение тотала (вкл. ОТ/Б): " + "  ".join(f"{k}:{fin[k]:.0%}" for k in range(0, 11)))
    # context
    print()
    for t in (A, H):
        gs = games(c, "season=? AND game_type=2 AND (home_id=? OR away_id=?)", (s, t["id"], t["id"]))
        print(fmt_profile(total_profile(gs, hi, lo), hi, lo, f"{t['tricode']} в сезоне: "))
        print(fmt_profile(total_profile(gs[-10:], hi, lo), hi, lo, f"{t['tricode']} последние 10: "))
    gs, _, _ = h2h_games(c, A, H, seasons=2)
    print(fmt_profile(total_profile(gs, hi, lo), hi, lo, "Очные, 2 сезона: "))
    for g in gs[-5:]:
        print(f"    {g['date']} {code_of(c, g['away_id'])} {g['away_score']} @ {code_of(c, g['home_id'])} {g['home_score']} {result_tag(g)}")
    small = min(m['gp'].get(A['id'], 0), m['gp'].get(H['id'], 0))
    if small < 15:
        print(f"⚠ Ранний сезон ({small} игр у одной из команд): рейтинги сильно опираются на прошлый сезон.")
    if p["model"] == "v2" and ("вероятный" in (p["goalies"][0][1], p["goalies"][1][1])):
        print("⚠ Вратари не подтверждены — уточните через news-scout и перезапустите с --home-goalie/--away-goalie.")
    cal = None
    try:
        import nhl_model as M
        cal = M.load_calibration(c)
    except Exception:  # noqa
        pass
    if cal and cal.get("holdout"):
        print(f"Точность модели (бэктест): {cal['holdout']}")
    print("Правила рынка: у большинства БК тотал НХЛ — с учётом ОТ и буллитов (победный буллит = +1 гол). Сверьте правила своей БК.")


def cmd_slate(a):
    c = db()
    s = current_season()
    d = a.date or dt.date.today().isoformat()
    gl = [dict(r) for r in c.execute("SELECT * FROM games WHERE date=? AND season=? ORDER BY start_et", (d, s))]
    if not gl:
        print(f"Матчей на {d} в базе нет (обновите: python3 scripts/nhl.py sync)")
        return
    m = fit(c, s, before=d, k=a.prior_games)
    rows = []
    for g in gl:
        p = predict_v2(c, s, g["home_id"], g["away_id"], d) or predict(m, g["home_id"], g["away_id"])
        rows.append((g, p, cum(p["fin"], lambda k: k >= a.high), cum(p["fin"], lambda k: k <= a.low)))
    key = 2 if a.sort == "high" else 3
    rows.sort(key=lambda r: -r[key])
    print(f"НХЛ, {d}: {len(rows)} матчей (сортировка по {'6+' if a.sort == 'high' else 'мало'}). Время — восточное (ET).")
    print(f"{'Матч':<14}{'Время':>7}{'λ тотал':>9}{'P(' + str(a.high) + '+)':>9}{'P(≤' + str(a.low) + ')':>9}{'ТБ5.5':>8}{'ТМ5.5':>8}{'ОТ':>6}  Вратари (вероятные), b2b, счёт")
    for g, p, ph, pl in rows:
        tb = cum(p["fin"], lambda k: k > 5.5)
        sc = f"{g['away_score']}:{g['home_score']} {result_tag(g)}" if g["state"] == 7 else ""
        t = (g["start_et"] or "")[11:16]
        extra = ""
        if p.get("model") == "v2":
            (hn, _, _), (an, _, _) = p["goalies"]
            b2 = ("b2b:" + "".join(x for x, f in ((code_of(c, g['home_id']), p['b2b'][0]), (code_of(c, g['away_id']), p['b2b'][1])) if f)) if any(p["b2b"]) else ""
            extra = f"{an or '?'} / {hn or '?'} {b2}"
        print(f"{code_of(c, g['away_id']) + ' @ ' + code_of(c, g['home_id']):<14}{t:>7}{p['lh'] + p['la']:>9.2f}{ph:>9.0%}{pl:>9.0%}{tb:>8.0%}{1 - tb:>8.0%}{p['tie']:>6.0%}  {extra} {sc}")


def cmd_backtest(a):
    c = db()
    s = a.season or prev_season(current_season())
    gl = games(c, "season=? AND game_type=2", (s,))
    if not gl:
        raise SystemExit("Нет матчей сезона — sync (для старых сезонов: sync --history)")
    prev = games(c, "season=? AND game_type=2", (prev_season(s),))
    base_hi = sum(totals(g)[0] >= a.high for g in prev) / len(prev) if prev else 0.4
    base_lo = sum(totals(g)[0] <= a.low for g in prev) / len(prev) if prev else 0.4
    dates = sorted({g["date"] for g in gl})
    preds = []
    m = None
    for i, d in enumerate(dates):
        if m is None or i % a.refit_days == 0:
            m = fit(c, s, before=d, k=a.prior_games)
        for g in (x for x in gl if x["date"] == d):
            p = predict(m, g["home_id"], g["away_id"])
            ft = totals(g)[0]
            preds.append((cum(p["fin"], lambda k: k >= a.high), ft >= a.high, cum(p["fin"], lambda k: k <= a.low), ft <= a.low,
                          cum(p["fin"], lambda k: k > 5.5), ft > 5.5))
    n = len(preds)

    def brier(ix, base):
        bm = sum((x[ix] - x[ix + 1]) ** 2 for x in preds) / n
        bb = sum((base - x[ix + 1]) ** 2 for x in preds) / n
        return bm, bb

    print(f"Бэктест walk-forward, сезон {season_label(s)}: {n} матчей (рейтинги — только по матчам до даты игры)")
    for name, ix, base in ((f"{a.high}+", 0, base_hi), (f"≤{a.low}", 2, base_lo), ("ТБ5.5", 4, base_hi)):
        bm, bb = brier(ix, base)
        print(f"  {name:<6} факт {sum(x[ix + 1] for x in preds) / n:.1%}; Brier модель {bm:.4f} против константы {bb:.4f} "
              f"→ {'лучше' if bm < bb else 'не лучше'} на {abs(1 - bm / bb):.1%}")
    print(f"\nКалибровка P({a.high}+):")
    bins = [(0, .3), (.3, .4), (.4, .5), (.5, .6), (.6, 1.01)]
    for lo_, hi_ in bins:
        sel = [x for x in preds if lo_ <= x[0] < hi_]
        if sel:
            print(f"  прогноз {lo_:.0%}–{min(hi_, 1):.0%}: {len(sel):>4} матчей, средний прогноз {sum(x[0] for x in sel) / len(sel):.1%}, факт {sum(x[1] for x in sel) / len(sel):.1%}")
    print("Модель полезна, если Brier ниже константы и факт в корзинах близок к прогнозу. Это не гарантия прибыли против линии БК.")


def cmd_calibrate(a):
    import nhl_model as M
    c = db()
    cur = current_season()
    if a.params:
        M.P.update(json.loads(a.params))
    seasons = [s_ for s_ in (cur - 10001 * i for i in range(a.seasons, 0, -1))
               if c.execute("SELECT COUNT(*) FROM box b JOIN games g ON g.id=b.game_id WHERE g.season=?", (s_,)).fetchone()[0] > 500]
    rows = []
    for s_ in seasons:
        rows += M.walk_forward(c, s_)
    cal0 = M.build_calibration(rows)
    gf, ga = cal0["b2b"]
    for x in rows:
        lh, la = x["lh"], x["la"]
        if x["b2bh"]:
            lh *= gf; la *= ga
        if x["b2ba"]:
            la *= gf; lh *= ga
        x["lam"] = lh + la
    cal = M.build_calibration(rows)
    cal["b2b"] = (gf, ga)
    cal["params"] = dict(M.P)
    cal["holdout"] = a.holdout_note
    M.save_calibration(c, cal, seasons)
    print(f"Калибровка: {len(rows)} матчей сезонов {', '.join(season_label(x) for x in seasons)}; "
          f"b2b: свои голы ×{gf:.3f}, пропущенные ×{ga:.3f}; база 6+ {cal['base6']:.1%}, ≤4 {cal['base4']:.1%}")


def cmd_backtest2(a):
    import nhl_model as M
    c = db()
    s = a.season or prev_season(current_season())
    stored = M.load_calibration(c)
    if stored:
        M.P.update(stored.get("params", {}))
    train = []
    for s_ in (s - 30003, s - 20002, s - 10001):
        train += M.walk_forward(c, s_)
    if not train:
        raise SystemExit("Нет протоколов для обучения (sync --boxscores <сезоны>)")
    cal0 = M.build_calibration(train)
    gf, ga = cal0["b2b"]
    def adj(x):
        lh, la = x["lh"], x["la"]
        if x["b2bh"]:
            lh *= gf; la *= ga
        if x["b2ba"]:
            la *= gf; lh *= ga
        return lh + la
    for x in train:
        x["lam"] = adj(x)
    cal = M.build_calibration(train)
    test = M.walk_forward(c, s, use_actual_goalies=not a.likely_goalies)
    for x in test:
        x["lam"] = adj(x)
    print(f"Бэктест v2, сезон {season_label(s)}: {len(test)} матчей; обучение на 3 предыдущих сезонах; вратари: {'вероятные' if a.likely_goalies else 'фактические стартеры'}")
    for name, f, y, base in ((f"{a.high}+", lambda F: sum(F[a.high:]), lambda x: x["fin"] >= a.high, cal["base6"]),
                             (f"≤{a.low}", lambda F: sum(F[:a.low + 1]), lambda x: x["fin"] <= a.low, cal["base4"])):
        bm = bb = 0
        preds = []
        for x in test:
            pr = f(M.dist(cal, x["lam"])[1]); yy = y(x)
            bm += (pr - yy) ** 2; bb += (base - yy) ** 2; preds.append((pr, yy))
        print(f"  {name:<4} факт {sum(p_[1] for p_ in preds) / len(preds):.1%}; Brier {bm / len(test):.4f} против константы {bb / len(test):.4f} → {1 - bm / bb:+.2%}")
        for lo_, hi_ in ((0, .45), (.45, .52), (.52, .58), (.58, .65), (.65, 1)) if name.endswith("+") else ((0, .14), (.14, .18), (.18, .22), (.22, .28), (.28, 1)):
            sel = [p_ for p_ in preds if lo_ <= p_[0] < hi_]
            if sel:
                print(f"      прогноз {lo_:.0%}–{min(hi_, 1):.0%}: {len(sel):>4} игр, ср. прогноз {sum(p_[0] for p_ in sel) / len(sel):.1%}, факт {sum(p_[1] for p_ in sel) / len(sel):.1%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def th(p):
        p.add_argument("--high", type=int, default=6, help="порог «много шайб» (по умолчанию 6+)")
        p.add_argument("--low", type=int, default=4, help="порог «мало шайб» (по умолчанию ≤4)")

    p = sub.add_parser("sync"); p.add_argument("--history", action="store_true"); p.add_argument("--details", action="store_true")
    p.add_argument("--boxscores", type=int, nargs="*", help="сезоны для загрузки протоколов (броски, вратари), напр. 20252026; 0 = текущий")
    p.add_argument("--season", type=int); p.set_defaults(f=cmd_sync)
    p = sub.add_parser("league"); th(p); p.add_argument("--season", type=int); p.add_argument("--trend", type=int, default=0); p.set_defaults(f=cmd_league)
    p = sub.add_parser("team"); th(p); p.add_argument("team"); p.add_argument("--season", type=int); p.add_argument("--last", type=int, default=10); p.set_defaults(f=cmd_team)
    p = sub.add_parser("h2h"); th(p); p.add_argument("team_a"); p.add_argument("team_b"); p.add_argument("--since", type=int)
    p.add_argument("--by-team", action="store_true", help="только эта команда, без прежних названий франшизы")
    p.add_argument("--no-playoffs", action="store_true"); p.add_argument("--last", type=int, default=10)
    p.add_argument("--seasons", type=int, default=2, help="сколько последних сезонов (по умолчанию 2)")
    p.add_argument("--all", action="store_true", help="вся история с 1917"); p.set_defaults(f=cmd_h2h)
    p = sub.add_parser("match"); th(p); p.add_argument("away", help="гости"); p.add_argument("home", help="хозяева")
    p.add_argument("--date", help="дата матча (по умолчанию сегодня)"); p.add_argument("--v1", action="store_true", help="старая модель только по голам")
    p.add_argument("--home-goalie"); p.add_argument("--away-goalie")
    p.add_argument("--odds", nargs="*", help="коэффициенты БК: tb5.5=1.90 tm5.5=1.95 tb6.5=2.60 ...")
    p.add_argument("--min-edge", type=float, default=0.03); p.add_argument("--prior-games", type=float, default=12); p.set_defaults(f=cmd_match)
    p = sub.add_parser("slate"); th(p); p.add_argument("--date"); p.add_argument("--sort", choices=["high", "low"], default="high")
    p.add_argument("--prior-games", type=float, default=12); p.set_defaults(f=cmd_slate)
    p = sub.add_parser("backtest"); th(p); p.add_argument("--season", type=int); p.add_argument("--likely-goalies", action="store_true")
    p.set_defaults(f=cmd_backtest2)
    p = sub.add_parser("backtest-v1"); th(p); p.add_argument("--season", type=int); p.add_argument("--refit-days", type=int, default=7)
    p.add_argument("--prior-games", type=float, default=12); p.set_defaults(f=cmd_backtest)
    p = sub.add_parser("calibrate"); p.add_argument("--seasons", type=int, default=3); p.add_argument("--params")
    p.add_argument("--holdout-note", default=""); p.set_defaults(f=cmd_calibrate)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
