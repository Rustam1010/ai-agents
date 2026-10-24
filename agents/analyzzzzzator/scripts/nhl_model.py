"""Модель v2 тоталов НХЛ: броски × реализация × вратарь соперника × усталость (back-to-back),
плюс эмпирическая калибровка распределения голов и ничьих на истории (хоккей не пуассоновский:
разброс тотала ~0.9 от пуассона, ничьих в осн. время ~21–25% против ~17%)."""
import datetime as dt
import json
import math

import nhl

P = dict(k_shots=40.0, prior_w=0.6, k_fin=800.0, k_goalie=2500.0, prev_goalie_w=0.5, nb=8, alpha=40)  # подобрано бэктестом


def _date(s):
    return dt.date.fromisoformat(s)


def load_season(c, season, before=None):
    q = """SELECT g.*, b.home_sog, b.away_sog FROM games g JOIN box b ON b.game_id=g.id
           WHERE g.season=? AND g.game_type=2 AND g.state=7""" + (" AND g.date<?" if before else "") + " ORDER BY g.date"
    return [dict(r) for r in c.execute(q, (season, before) if before else (season,))]


def starters(c, game_ids):
    out = {}
    if not game_ids:
        return out
    for r in c.execute(f"SELECT game_id, team_id, player_id, name FROM goalies WHERE starter=1 AND game_id IN ({','.join(map(str, game_ids))})"):
        out[(r[0], r[1])] = (r[2], r[3])
    return out


def goalie_table(c, season, before=None):
    """Сейвы/броски вратарей: текущий сезон до даты + прошлый сезон с весом prev_goalie_w."""
    tab = {}
    for s, w in ((season, 1.0), (nhl.prev_season(season), P["prev_goalie_w"])):
        q = """SELECT k.player_id, k.name, SUM(k.sa), SUM(k.sv) FROM goalies k JOIN games g ON g.id=k.game_id
               WHERE g.season=? AND g.game_type=2""" + (" AND g.date<?" if (before and s == season) else "") + " GROUP BY k.player_id"
        for pid, name, sa, sv in c.execute(q, (s, before) if (before and s == season) else (s,)):
            t = tab.setdefault(pid, [name, 0.0, 0.0])
            t[1] += w * (sa or 0)
            t[2] += w * (sv or 0)
    return tab


def rest_flags(c, season):
    """team_id, date -> True если играл накануне."""
    last = {}
    flags = {}
    for r in c.execute("SELECT date, home_id, away_id FROM games WHERE season=? AND game_type=2 ORDER BY date", (season,)):
        d = _date(r[0])
        for t in (r[1], r[2]):
            if t in last and (d - last[t]).days == 1:
                flags[(t, r[0])] = True
            last[t] = d
    return flags


def _ratings(gl, mh, ma, k, prior=None, pw=0.0, key=("home_sog", "away_sog"), iters=6):
    teams = {x for g in gl for x in (g["home_id"], g["away_id"])}
    att = {t: 1.0 for t in teams}
    de = {t: 1.0 for t in teams}
    hk, ak = key
    b = (mh + ma) / 2
    for _ in range(iters):
        sf = {t: 0.0 for t in teams}; ef = {t: 0.0 for t in teams}
        sa = {t: 0.0 for t in teams}; ea = {t: 0.0 for t in teams}
        for g in gl:
            h, a = g["home_id"], g["away_id"]
            sf[h] += g[hk]; ef[h] += mh * de[a]
            sf[a] += g[ak]; ef[a] += ma * de[h]
            sa[h] += g[ak]; ea[h] += ma * att[a]
            sa[a] += g[hk]; ea[a] += mh * att[h]
        for t in teams:
            pa = 1 + pw * (prior[0].get(t, 1) - 1) if prior else 1.0
            pd = 1 + pw * (prior[1].get(t, 1) - 1) if prior else 1.0
            att[t] = (sf[t] + k * b * pa) / (ef[t] + k * b)
            de[t] = (sa[t] + k * b * pd) / (ea[t] + k * b)
    return att, de


def fit(c, season, before=None):
    gl = load_season(c, season, before)
    prev = load_season(c, nhl.prev_season(season))
    base = gl if len(gl) >= 200 else gl + prev
    if not base:
        return None
    n = len(base)
    msh = sum(g["home_sog"] for g in base) / n
    msa = sum(g["away_sog"] for g in base) / n
    gh = sum(nhl.reg_scores(g)[0] for g in base) / n
    ga = sum(nhl.reg_scores(g)[1] for g in base) / n
    conv_h, conv_a = gh / msh, ga / msa
    prior = _ratings(prev, msh, msa, P["k_shots"]) if prev else None
    if gl:
        att, de = _ratings(gl, msh, msa, P["k_shots"], prior, P["prior_w"])
    else:
        att, de = prior
    # реализация команды (голы/броски), сильно сжатая к лиге
    conv = (gh + ga) / (msh + msa)
    gf, sf = {}, {}
    for gg, w in ((gl, 1.0), (prev, 0.5)):
        for g in gg:
            rh, ra = nhl.reg_scores(g)
            for t, goals, shots in ((g["home_id"], rh, g["home_sog"]), (g["away_id"], ra, g["away_sog"])):
                gf[t] = gf.get(t, 0) + w * goals
                sf[t] = sf.get(t, 0) + w * shots
    fin = {t: ((gf[t] + P["k_fin"] * conv) / (sf[t] + P["k_fin"])) / conv for t in gf}
    gk = goalie_table(c, season, before)
    sv_lg = 1 - conv
    gfac = {pid: (1 - (sv + P["k_goalie"] * sv_lg) / (sa + P["k_goalie"])) / (1 - sv_lg) for pid, (_, sa, sv) in gk.items()}
    names = {pid: v[0] for pid, v in gk.items()}
    return dict(att=att, de=de, msh=msh, msa=msa, conv_h=conv_h, conv_a=conv_a, fin=fin, gfac=gfac, gnames=names, n=len(gl))


def likely_starter(c, team_id, season, before=None, last=6):
    q = """SELECT k.player_id, k.name FROM goalies k JOIN games g ON g.id=k.game_id
           WHERE k.team_id=? AND k.starter=1 AND g.season=?""" + (" AND g.date<?" if before else "") + " ORDER BY g.date DESC LIMIT ?"
    rows = list(c.execute(q, (team_id, season, before, last) if before else (team_id, season, last)))
    if not rows:
        return None, None
    cnt = {}
    for pid, name in rows:
        cnt[(pid, name)] = cnt.get((pid, name), 0) + 1
    (pid, name), _ = max(cnt.items(), key=lambda x: x[1])
    return pid, name


def goalie_by_name(c, team_id, name):
    r = c.execute("SELECT player_id, name FROM goalies WHERE team_id=? AND name LIKE ? ORDER BY game_id DESC LIMIT 1",
                  (team_id, f"%{name}%")).fetchone()
    if not r:
        r = c.execute("SELECT player_id, name FROM goalies WHERE name LIKE ? ORDER BY game_id DESC LIMIT 1", (f"%{name}%",)).fetchone()
    return (r[0], r[1]) if r else (None, None)


def lambdas(m, home, away, g_home=None, g_away=None, b2b_home=False, b2b_away=False, b2b=(1.0, 1.0)):
    sh = m["msh"] * m["att"].get(home, 1) * m["de"].get(away, 1)
    sa = m["msa"] * m["att"].get(away, 1) * m["de"].get(home, 1)
    lh = sh * m["conv_h"] * m["fin"].get(home, 1) * m["gfac"].get(g_away, 1.0)
    la = sa * m["conv_a"] * m["fin"].get(away, 1) * m["gfac"].get(g_home, 1.0)
    gf_mult, ga_mult = b2b
    if b2b_home:
        lh *= gf_mult; la *= ga_mult
    if b2b_away:
        la *= gf_mult; lh *= ga_mult
    return lh, la, sh, sa


# ---------------- calibration ----------------
def walk_forward(c, season, refit=7, use_actual_goalies=True):
    gl = load_season(c, season)
    if not gl:
        return []
    st = starters(c, [g["id"] for g in gl])
    rest = rest_flags(c, season)
    dates = sorted({g["date"] for g in gl})
    out, m = [], None
    for i, d in enumerate(dates):
        if m is None or i % refit == 0:
            m = fit(c, season, before=d)
        if m is None:
            continue
        for g in (x for x in gl if x["date"] == d):
            if use_actual_goalies:
                gh_, ga_ = st.get((g["id"], g["home_id"]), (None,))[0], st.get((g["id"], g["away_id"]), (None,))[0]
            else:
                gh_, ga_ = likely_starter(c, g["home_id"], season, d)[0], likely_starter(c, g["away_id"], season, d)[0]
            lh, la, _, _ = lambdas(m, g["home_id"], g["away_id"], gh_, ga_)
            rh, ra = nhl.reg_scores(g)
            out.append(dict(lam=lh + la, lh=lh, la=la, reg=rh + ra, tie=rh == ra, fin=nhl.totals(g)[0],
                            b2bh=rest.get((g["home_id"], d), False), b2ba=rest.get((g["away_id"], d), False), rh=rh, ra=ra))
    return out


def build_calibration(rows):
    nb, alpha = P["nb"], P["alpha"]
    lams = sorted(x["lam"] for x in rows)
    edges = [lams[int(len(lams) * q / nb)] for q in range(1, nb)]
    bucket = lambda l: sum(l > e for e in edges)
    allc = [0] * 20
    for x in rows:
        allc[min(x["reg"], 19)] += 1
    cnt = [[0] * 20 for _ in range(nb)]
    cen = [[] for _ in range(nb)]
    for x in rows:
        b = bucket(x["lam"])
        cnt[b][min(x["reg"], 19)] += 1
        cen[b].append(x["lam"])
    dists = []
    for i in range(nb):
        n = sum(cnt[i])
        dists.append([(cnt[i][k] + alpha * allc[k] / len(rows)) / (n + alpha) for k in range(20)])
    centers = [sum(v) / len(v) for v in cen]
    tie = {}
    for k in range(0, 20, 2):
        sel = [x for x in rows if x["reg"] == k]
        tie[k] = (sum(x["tie"] for x in sel) + 1) / (len(sel) + 3) if sel else 0.3
    # усталость: голы команды на b2b относительно модели
    def ratio(sel_for, sel_against):
        f = sum(x[0] for x in sel_for) / max(sum(x[1] for x in sel_for), 1e-9)
        a = sum(x[0] for x in sel_against) / max(sum(x[1] for x in sel_against), 1e-9)
        return f, a
    sf = [(x["rh"], x["lh"]) for x in rows if x["b2bh"]] + [(x["ra"], x["la"]) for x in rows if x["b2ba"]]
    sa = [(x["ra"], x["la"]) for x in rows if x["b2bh"]] + [(x["rh"], x["lh"]) for x in rows if x["b2ba"]]
    b2b = ratio(sf, sa) if sf else (1.0, 1.0)
    return dict(centers=centers, dists=dists, tie={str(k): v for k, v in tie.items()}, b2b=b2b, n=len(rows),
                base6=sum(x["fin"] >= 6 for x in rows) / len(rows), base4=sum(x["fin"] <= 4 for x in rows) / len(rows))


def dist(cal, lam):
    centers, dists = cal["centers"], cal["dists"]
    if lam <= centers[0]:
        d = dists[0]
    elif lam >= centers[-1]:
        d = dists[-1]
    else:
        for i in range(len(centers) - 1):
            if centers[i] <= lam <= centers[i + 1]:
                w = (lam - centers[i]) / (centers[i + 1] - centers[i])
                d = [(1 - w) * a + w * b for a, b in zip(dists[i], dists[i + 1])]
                break
    fin = [0.0] * 21
    tie = {int(k): v for k, v in cal["tie"].items()}
    for k, p in enumerate(d):
        t = tie.get(k, 0.0)
        fin[k] += p * (1 - t)
        fin[k + 1] += p * t
    return d, fin


def save_calibration(c, cal, seasons):
    cal["seasons"] = seasons
    c.execute("INSERT OR REPLACE INTO meta VALUES('calibration', ?)", (json.dumps(cal),))
    c.commit()


def load_calibration(c):
    r = c.execute("SELECT v FROM meta WHERE k='calibration'").fetchone()
    return json.loads(r[0]) if r else None
