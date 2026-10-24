#!/usr/bin/env python3
"""Анализ сырых данных A/B-теста из CSV (одна строка = одна единица рандомизации, обычно пользователь).
Методы — из Trustworthy Online Controlled Experiments (гл. 17–21). Только stdlib.

Команды:
  summary   SRM, средние, Δ, Δ% (delta method), p-value, skewness/355·s²; опционально --cap и --pre (CUPED)
  ratio     ratio-метрика (CTR = Σклики/Σпросмотры) с правильной дисперсией delta method vs наивной
  aa        симуляция A/A перемешиванием: доля значимых, равномерность p-values (KS), диагноз провала
  segments  SRM по сегментам (отладка SRM: день, браузер, платформа, новые/старые)
"""
import argparse
import csv
import math
import random
from statistics import NormalDist

N = NormalDist()


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def stats(xs):
    n = len(xs)
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    skew = (sum((x - m) ** 3 for x in xs) / n) / sd ** 3 if sd > 0 else 0.0
    return n, m, var, skew


def chi2_sf_df1(x):
    return 2 * (1 - N.cdf(math.sqrt(x))) if x > 0 else 1.0


def chi2_sf(x, k):
    if k == 1:
        return chi2_sf_df1(x)
    s, xx = k / 2.0, x / 2.0
    if xx <= 0:
        return 1.0
    if xx < s + 1:
        term = total = 1.0 / s
        n = s
        while abs(term) > 1e-15 * abs(total):
            n += 1
            term *= xx / n
            total += term
        return max(0.0, 1.0 - total * math.exp(-xx + s * math.log(xx) - math.lgamma(s)))
    b = xx + 1 - s
    c, d = 1e300, 1 / b
    h = d
    for i in range(1, 10000):
        an = -i * (i - s)
        b += 2
        d = an * d + b
        d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c
        c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d
        h *= d * c
        if abs(d * c - 1) < 1e-15:
            break
    return h * math.exp(-xx + s * math.log(xx) - math.lgamma(s))


def srm(counts, ratios=None):
    ratios = ratios or [1.0] * len(counts)
    tot, rs = sum(counts), sum(ratios)
    exp = [tot * r / rs for r in ratios]
    chi = sum((o - e) ** 2 / e for o, e in zip(counts, exp))
    return chi, chi2_sf(chi, len(counts) - 1)


def compare(mt, vt, nt, mc, vc, nc):
    se_t2, se_c2 = vt / nt, vc / nc
    d = mt - mc
    se = math.sqrt(se_t2 + se_c2)
    p = 2 * (1 - N.cdf(abs(d / se))) if se > 0 else 1.0
    pct = d / mc if mc else float("nan")
    se_pct = math.sqrt(se_t2 / mc ** 2 + mt ** 2 * se_c2 / mc ** 4) if mc else float("nan")
    return d, se, p, pct, se_pct


def groups(rows, vcol):
    g = {}
    for r in rows:
        g.setdefault(r[vcol], []).append(r)
    return g


def pick_control(g, control):
    if control:
        if control not in g:
            raise SystemExit(f"контроль '{control}' не найден; варианты: {sorted(g)}")
        return control
    for cand in ("control", "Control", "C", "A", "0"):
        if cand in g:
            return cand
    return sorted(g)[0]


def print_srm(g, ratios):
    names = sorted(g)
    counts = [len(g[k]) for k in names]
    chi, p = srm(counts, ratios)
    tot = sum(counts)
    print("SRM: " + ", ".join(f"{k}={c:,} ({c / tot:.2%})" for k, c in zip(names, counts)) + f" → χ²={chi:.2f}, p={p:.3g}")
    if p < 0.001:
        print("🚨 SRM: остальные результаты, скорее всего, невалидны. Отладка: python3 scripts/abdata.py segments ...")
    elif p < 0.01:
        print("⚠ Пограничный дисбаланс групп — проверьте назначение и фильтрацию.")
    return p


def cmd_summary(a):
    rows = load(a.file)
    g = groups(rows, a.variant)
    ctrl = pick_control(g, a.control)
    print_srm(g, a.ratios)
    zc = N.inv_cdf(1 - a.alpha / 2)

    def vals(rs, cap=None):
        xs = [num(r[a.metric]) for r in rs]
        return [min(x, cap) for x in xs] if cap is not None else xs

    versions = [("исходная", None)] + ([(f"capped ≤ {a.cap:g}", a.cap)] if a.cap is not None else [])
    for label, cap in versions:
        print(f"\nМетрика «{a.metric}» ({label}); контроль = {ctrl}")
        cs = vals(g[ctrl], cap)
        nc, mc, vc, sc = stats(cs)
        print(f"  {ctrl:<12} n={nc:<9,} mean={mc:<12.6g} sd={math.sqrt(vc):<10.4g} skew={sc:.2f}")
        for v in sorted(g):
            if v == ctrl:
                continue
            ts = vals(g[v], cap)
            nt, mt, vt, st = stats(ts)
            d, se, p, pct, se_pct = compare(mt, vt, nt, mc, vc, nc)
            print(f"  {v:<12} n={nt:<9,} mean={mt:<12.6g} sd={math.sqrt(vt):<10.4g} skew={st:.2f}")
            print(f"    Δ={d:+.6g} [{d - zc * se:+.6g}, {d + zc * se:+.6g}], Δ%={pct:+.3%} [{pct - zc * se_pct:+.3%}, {pct + zc * se_pct:+.3%}], p={p:.4g}")
        s_max = max(abs(stats(vals(g[v], cap))[3]) for v in g)
        need = 355 * s_max ** 2
        if s_max > 1:
            ok = "OK" if min(len(g[v]) for v in g) >= need else "⚠ МАЛО — нормальность среднего под вопросом"
            print(f"  355·s² = {need:,.0f} на вариант при |skew|={s_max:.1f}: {ok}")

    if a.pre:
        capf = (lambda v: min(v, a.cap)) if a.cap is not None else (lambda v: v)
        print(f"\nCUPED по ковариате «{a.pre}» (данные до эксперимента)" + (f", метрика capped ≤ {a.cap:g}" if a.cap is not None else ""))
        allx = [capf(num(r[a.pre])) for r in rows]
        ally = [capf(num(r[a.metric])) for r in rows]
        mx = sum(allx) / len(allx)
        my = sum(ally) / len(ally)
        cov = sum((x - mx) * (y - my) for x, y in zip(allx, ally)) / (len(allx) - 1)
        varx = sum((x - mx) ** 2 for x in allx) / (len(allx) - 1)
        theta = cov / varx if varx else 0.0
        adj = lambda rs: [capf(num(r[a.metric])) - theta * (capf(num(r[a.pre])) - mx) for r in rs]
        nc, mc, vc, _ = stats(adj(g[ctrl]))
        _, _, vc_raw, _ = stats([capf(num(r[a.metric])) for r in g[ctrl]])
        print(f"  θ = {theta:.4g}; дисперсия контроля: {vc_raw:.4g} → {vc:.4g} (снижение {1 - vc / vc_raw:.1%})")
        for v in sorted(g):
            if v == ctrl:
                continue
            nt, mt, vt, _ = stats(adj(g[v]))
            d, se, p, pct, se_pct = compare(mt, vt, nt, mc, vc, nc)
            print(f"  {v}: Δ={d:+.6g} [{d - zc * se:+.6g}, {d + zc * se:+.6g}], Δ%≈{pct:+.3%}, p={p:.4g}")


def cmd_ratio(a):
    rows = load(a.file)
    g = groups(rows, a.variant)
    ctrl = pick_control(g, a.control)
    print_srm(g, a.ratios)
    zc = N.inv_cdf(1 - a.alpha / 2)
    res = {}
    for v, rs in g.items():
        xs = [num(r[a.num]) for r in rs]
        ys = [num(r[a.den]) for r in rs]
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        vx = sum((x - mx) ** 2 for x in xs) / (n - 1)
        vy = sum((y - my) ** 2 for y in ys) / (n - 1)
        cxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (n - 1)
        r = mx / my
        var_delta = (vx / my ** 2 - 2 * mx * cxy / my ** 3 + mx ** 2 * vy / my ** 4) / n
        tot_y = sum(ys)
        var_naive = r * (1 - r) / tot_y if 0 <= r <= 1 else float("nan")
        res[v] = (n, r, var_delta, var_naive, tot_y)
        print(f"  {v:<12} пользователей={n:<9,} {a.num}/{a.den} = {r:.5g}  SE(delta)={math.sqrt(var_delta):.3g}  SE(наивная, по событиям)={math.sqrt(var_naive):.3g}")
    nc, rc, vdc, vnc, _ = res[ctrl]
    for v, (nt, rt, vdt, vnt, _) in res.items():
        if v == ctrl:
            continue
        d = rt - rc
        se_d = math.sqrt(vdt + vdc)
        se_n = math.sqrt(vnt + vnc)
        p_d = 2 * (1 - N.cdf(abs(d / se_d)))
        p_n = 2 * (1 - N.cdf(abs(d / se_n))) if se_n == se_n else float("nan")
        print(f"\n{v} vs {ctrl}: Δ={d:+.5g} ({d / rc:+.2%})")
        print(f"  delta method: CI [{d - zc * se_d:+.5g}, {d + zc * se_d:+.5g}], p={p_d:.4g}  ← правильно")
        print(f"  наивно (события независимы): p={p_n:.4g}  ← занижает дисперсию, если у пользователя много событий")


def cmd_aa(a):
    rows = load(a.file)
    if a.variant and a.only:
        rows = [r for r in rows if r[a.variant] == a.only]
    xs = [num(r[a.metric]) for r in rows]
    if a.cap is not None:
        xs = [min(x, a.cap) for x in xs]
    rnd = random.Random(a.seed)
    ps = []
    n = len(xs)
    for _ in range(a.runs):
        idx = list(range(n))
        rnd.shuffle(idx)
        h = n // 2
        g1 = [xs[i] for i in idx[:h]]
        g2 = [xs[i] for i in idx[h:]]
        n1, m1, v1, _ = stats(g1)
        n2, m2, v2, _ = stats(g2)
        se = math.sqrt(v1 / n1 + v2 / n2)
        ps.append(2 * (1 - N.cdf(abs((m1 - m2) / se))) if se > 0 else 1.0)
    ps.sort()
    sig = sum(p < a.alpha for p in ps) / len(ps)
    D = max(max((i + 1) / len(ps) - p, p - i / len(ps)) for i, p in enumerate(ps))
    crit = 1.36 / math.sqrt(len(ps))
    print(f"A/A по «{a.metric}»: {n:,} единиц, {a.runs} перемешиваний")
    print(f"Доля p<{a.alpha}: {sig:.1%} (ожидается {a.alpha:.0%})")
    print(f"KS-статистика против равномерного: D={D:.3f} (критическое ≈{crit:.3f} при 0.05) → {'⚠ НЕ равномерно' if D > crit else 'OK'}")
    bins = [0] * 10
    for p in ps:
        bins[min(int(p * 10), 9)] += 1
    print("Гистограмма p (децили): " + " ".join(f"{b}" for b in bins))
    near32 = sum(0.30 <= p <= 0.34 for p in ps) / len(ps)
    if near32 > 0.1:
        print("⚠ Пик около p≈0.32 — один огромный выброс доминирует (гл. 19). Расследовать или --cap.")
    if D > crit and near32 <= 0.1:
        print("Возможные причины: неверная дисперсия (ratio-метрика → ratio), сильная асимметрия (→ --cap), мало данных.")
    print("Ограничение: перемешивание не ловит баги назначения, кеши и производительность — нужен и реальный A/A.")


def cmd_segments(a):
    rows = load(a.file)
    names = sorted({r[a.variant] for r in rows})
    seg = {}
    for r in rows:
        seg.setdefault(r[a.segment], {}).setdefault(r[a.variant], 0)
        seg[r[a.segment]][r[a.variant]] += 1
    print(f"SRM по сегменту «{a.segment}» (варианты: {', '.join(names)})")
    out = []
    for s, c in seg.items():
        counts = [c.get(v, 0) for v in names]
        if min(counts) == 0:
            out.append((0.0, s, counts))
            continue
        _, p = srm(counts, a.ratios)
        out.append((p, s, counts))
    for p, s, counts in sorted(out):
        tot = sum(counts)
        flag = "🚨" if p < 0.001 else ("⚠" if p < 0.01 else "  ")
        print(f" {flag} {s:<24} " + " ".join(f"{c:>9,}" for c in counts) + f"  доля 1-го: {counts[0] / tot:.2%}  p={p:.3g}")
    print("Сегмент с SRM указывает, где искать причину (гл. 21): браузер/бот-фильтр, день (рамп, чужой эксперимент), новые/старые.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, metric=True):
        p.add_argument("file")
        p.add_argument("--variant", required=True, help="колонка с вариантом")
        p.add_argument("--control", help="имя контрольного варианта")
        p.add_argument("--ratios", type=float, nargs="+", help="плановые доли вариантов в алфавитном порядке")
        p.add_argument("--alpha", type=float, default=0.05)
        if metric:
            p.add_argument("--metric", required=True)

    p = sub.add_parser("summary"); common(p)
    p.add_argument("--cap", type=float, help="обрезать метрику сверху (capping)")
    p.add_argument("--pre", help="колонка с той же метрикой до эксперимента (CUPED)")
    p.set_defaults(f=cmd_summary)

    p = sub.add_parser("ratio"); common(p, metric=False)
    p.add_argument("--num", required=True, help="числитель на пользователя (клики)")
    p.add_argument("--den", required=True, help="знаменатель на пользователя (просмотры)")
    p.set_defaults(f=cmd_ratio)

    p = sub.add_parser("aa")
    p.add_argument("file"); p.add_argument("--metric", required=True)
    p.add_argument("--variant"); p.add_argument("--only", help="взять только этот вариант (например, контроль)")
    p.add_argument("--runs", type=int, default=1000); p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--cap", type=float); p.add_argument("--seed", type=int, default=1)
    p.set_defaults(f=cmd_aa)

    p = sub.add_parser("segments")
    p.add_argument("file"); p.add_argument("--variant", required=True); p.add_argument("--segment", required=True)
    p.add_argument("--ratios", type=float, nargs="+")
    p.set_defaults(f=cmd_segments)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
