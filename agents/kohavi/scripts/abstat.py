#!/usr/bin/env python3
"""Калькулятор A/B-тестов по формулам из работ Кохави и соавторов. Только stdlib.

Команды:
  sample-size  размер выборки на вариант (конверсия --p или непрерывная --sd)
  power        мощность при заданной выборке
  srm          проверка Sample Ratio Mismatch (хи-квадрат)
  fpr          False Positive Risk по доле успешных идей
  ztest        сравнение конверсий двух групп: lift, CI, p-value
  skew-min     минимальная выборка для асимметричной метрики (правило 355·s²)
  duration     сколько дней нужно при заданном трафике
  dilute       разбавить эффект триггерной популяции на всю аудиторию (гл. 20)
  multi        множественные проверки: P(ложная значимость), Bonferroni, Benjamini-Hochberg, tiered
  fisher       объединить p-values независимых реплик (мета-анализ Фишера, гл. 17)
  pct-ci       CI для относительной разницы Δ% по delta method (гл. 18)
  split        эффективность неравного сплита относительно MPR 50/50 (гл. 15)
  peek-sim     симуляция: во сколько раз peeking завышает ложные срабатывания (гл. 3)
Примеры — в scripts/README.md.
"""
import argparse
import math
from statistics import NormalDist

N = NormalDist()


def z(q):
    return N.inv_cdf(q)


def variance(args):
    if args.p is not None:
        return args.p * (1 - args.p), args.p
    if args.sd is None or args.mean is None:
        raise SystemExit("нужно --p (конверсия) или --sd и --mean (непрерывная метрика)")
    return args.sd ** 2, args.mean


def delta(args, base):
    if args.mde_abs is not None:
        return args.mde_abs
    if args.mde_rel is None:
        raise SystemExit("нужно --mde-rel (относительный, 0.05 = 5%) или --mde-abs")
    return base * args.mde_rel


def cmd_sample_size(a):
    var, base = variance(a)
    d = delta(a, base)
    n = 2 * var * (z(1 - a.alpha / 2) + z(a.power)) ** 2 / d ** 2
    rule16 = 16 * var / d ** 2
    print(f"На вариант: {math.ceil(n):,} пользователей  (правило 16σ²/δ²: {math.ceil(rule16):,})")
    print(f"Всего при {a.variants} вариантах: {math.ceil(n) * a.variants:,}")
    print(f"MDE: {d:.6g} абсолютных ({d / base:.2%} относительных), α={a.alpha}, мощность={a.power:.0%}")


def cmd_power(a):
    var, base = variance(a)
    d = delta(a, base)
    se = math.sqrt(2 * var / a.n)
    pw = N.cdf(d / se - z(1 - a.alpha / 2))
    print(f"Мощность: {pw:.1%}  (n={a.n:,} на вариант, MDE={d / base:.2%} отн., α={a.alpha})")
    print(f"Минимально обнаружимый эффект при 80% мощности: {2.8 * se / base:.2%} относительных")
    if pw < 0.5:
        print("⚠ Мощность < 50%: значимый результат, если случится, скорее всего ложный и сильно завышен.")


def chi2_sf(x, k):
    """P(Chi2_k > x) через регуляризованную неполную гамма-функцию."""
    s, xx = k / 2.0, x / 2.0
    if xx <= 0:
        return 1.0
    if xx < s + 1:  # ряд для P
        term = total = 1.0 / s
        n = s
        while abs(term) > 1e-15 * abs(total):
            n += 1
            term *= xx / n
            total += term
        p = total * math.exp(-xx + s * math.log(xx) - math.lgamma(s))
        return max(0.0, 1.0 - p)
    # цепная дробь для Q (Lentz)
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


def cmd_srm(a):
    counts = a.counts
    ratios = a.ratios or [1.0] * len(counts)
    if len(ratios) != len(counts):
        raise SystemExit("--ratios должен иметь столько же значений, сколько --counts")
    total, rs = sum(counts), sum(ratios)
    exp = [total * r / rs for r in ratios]
    chi = sum((o - e) ** 2 / e for o, e in zip(counts, exp))
    p = chi2_sf(chi, len(counts) - 1)
    for i, (o, e) in enumerate(zip(counts, exp)):
        print(f"  группа {i + 1}: {o:,} (ожидалось {e:,.0f}, {o / total:.3%} вместо {ratios[i] / rs:.3%})")
    print(f"χ²={chi:.3f}, p-value={p:.3g}")
    if p < a.threshold:
        print(f"🚨 SRM (p < {a.threshold}): результатам теста доверять нельзя, пока не найдена причина.")
    elif p < 0.01:
        print(f"⚠ Пограничное отклонение (p < 0.01): SRM не подтверждён, но проверьте назначение, ботов и логирование; на больших выборках перепроверьте.")
    else:
        print(f"OK: SRM не обнаружен (порог {a.threshold}).")


def fpr_value(success, alpha, power):
    pi = 1 - success
    a2 = alpha / 2
    return a2 * pi / (a2 * pi + power * (1 - pi))


def cmd_fpr(a):
    f = fpr_value(a.success_rate, a.alpha, a.power)
    print(f"False Positive Risk: {f:.1%}  (доля успешных идей {a.success_rate:.0%}, α={a.alpha}, мощность={a.power:.0%})")
    pi = 1 - a.success_rate
    need = 2 * a.target * a.power * (1 - pi) / ((1 - a.target) * pi)
    print(f"Чтобы FPR был {a.target:.0%}, нужен порог p-value ≈ {need:.4f} (двусторонний)")


def cmd_ztest(a):
    pc, pt = a.c_conv / a.c_n, a.t_conv / a.t_n
    se = math.sqrt(pc * (1 - pc) / a.c_n + pt * (1 - pt) / a.t_n)
    d = pt - pc
    zz = d / se
    p = 2 * (1 - N.cdf(abs(zz)))
    ci = z(1 - a.alpha / 2) * se
    print(f"Control: {pc:.4%} ({a.c_conv:,}/{a.c_n:,})   Treatment: {pt:.4%} ({a.t_conv:,}/{a.t_n:,})")
    print(f"Δ = {d:+.4%} абс., lift = {d / pc:+.2%}; {1 - a.alpha:.0%} CI для Δ: [{d - ci:+.4%}, {d + ci:+.4%}]")
    print(f"z = {zz:.3f}, p-value = {p:.4g}")
    if min(a.c_conv, a.t_conv, a.c_n - a.c_conv, a.t_n - a.t_conv) < 30:
        print("⚠ Мало событий: нормальное приближение ненадёжно; выборка почти наверняка недостаточна.")


def cmd_skew_min(a):
    n = 355 * a.skewness ** 2
    print(f"Минимум на вариант для нормальности среднего: {math.ceil(n):,} (355·s², s={a.skewness})")
    print("Правило применимо при |skewness| > 1. Уменьшить: capping (обрезка выбросов сверху) или трансформация метрики.")


def cmd_duration(a):
    days = math.ceil(a.n_per_variant * a.variants / (a.daily_users * a.traffic_share))
    weeks = max(1, math.ceil(days / 7))
    print(f"Нужно ~{days} дн. → округлите до полных недель: {weeks * 7} дн. ({weeks} нед.)")
    print("Минимум неделя (лучше две) — из-за недельной сезонности и novelty-эффектов.")


def cmd_dilute(a):
    d_abs = a.trig_delta
    overall_total = a.overall_mean * a.overall_n
    diluted = d_abs * a.trig_n / overall_total
    tau = a.trig_n / a.overall_n
    print(f"Триггерных: {a.trig_n:,} из {a.overall_n:,} (τ = {tau:.2%})")
    print(f"Разбавленный (site-wide) эффект: {diluted:+.4%}  = Δθ·Nθ / (M_ωC·N_ω)")
    if a.trig_mean:
        naive = d_abs / a.trig_mean * tau
        print(f"Эффект на триггерных: {d_abs / a.trig_mean:+.3%}; наивное δθ·τ = {naive:+.4%}"
              f" (верно только если триггерные — случайная выборка; ошибка в {a.overall_mean / a.trig_mean:.2f} раза)")


def bh(pvals, q):
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    k_max = 0
    for rank, i in enumerate(order, 1):
        if pvals[i] <= rank / m * q:
            k_max = rank
    return {order[r] for r in range(k_max)}


def cmd_multi(a):
    if a.k:
        prob = 1 - (1 - a.alpha) ** a.k
        print(f"{a.k} независимых метрик при α={a.alpha}: P(≥1 ложно значимой) = {prob:.1%}; ожидается {a.k * a.alpha:.1f} ложных")
        print(f"Bonferroni: порог α/k = {a.alpha / a.k:.5f}")
    if a.pvalues:
        m = len(a.pvalues)
        rej = bh(a.pvalues, a.alpha)
        print(f"Benjamini-Hochberg (FDR {a.alpha}) по {m} p-values:")
        for i, pv in enumerate(a.pvalues):
            label = a.names[i] if a.names and i < len(a.names) else f"#{i + 1}"
            mark = "значимо" if i in rej else "—"
            bonf = "значимо" if pv < a.alpha / m else "—"
            print(f"  {label:<24} p={pv:<10.4g} BH: {mark:<8} Bonferroni: {bonf}")
    print("Tiered (Кохави, гл. 17): метрики 1-го порядка α=0.05, 2-го (каннибализация) α=0.01, 3-го (не ожидаем влияния) α=0.001")


def cmd_fisher(a):
    x = -2 * sum(math.log(p) for p in a.pvalues)
    k = len(a.pvalues)
    p = chi2_sf(x, 2 * k)
    print(f"Fisher: X = −2Σln(p) = {x:.3f}, df = {2 * k}, объединённый p-value = {p:.4g}")
    print("Применимо к независимым тестам одной гипотезы (оригинал + ортогональная реплика).")


def cmd_pct_ci(a):
    se_t, se_c = a.se_t, a.se_c
    if se_t is None:
        se_t = a.sd_t / math.sqrt(a.n_t)
        se_c = a.sd_c / math.sqrt(a.n_c)
    mt, mc = a.mean_t, a.mean_c
    pct = mt / mc - 1
    var = se_t ** 2 / mc ** 2 + mt ** 2 * se_c ** 2 / mc ** 4
    se = math.sqrt(var)
    zc = z(1 - a.alpha / 2)
    naive = math.sqrt(se_t ** 2 + se_c ** 2) / mc
    p = 2 * (1 - N.cdf(abs(pct / se)))
    print(f"Δ% = {pct:+.3%}; {1 - a.alpha:.0%} CI: [{pct - zc * se:+.3%}, {pct + zc * se:+.3%}]; p ≈ {p:.4g}")
    print(f"SE(Δ%) delta method = {se:.4%}; наивное var(Δ)/C̄² дало бы {naive:.4%}")


def cmd_split(a):
    q = a.treatment_share
    eff = 0.25 / (q * (1 - q))
    print(f"Treatment {q:.0%} / Control {1 - q:.0%}: дисперсия ∝ 1/(q(1−q)) — в {eff:.2f} раза больше, чем при 50/50")
    print(f"Чтобы сохранить мощность, нужно в {eff:.2f} раза больше трафика или времени.")
    if q < 0.5:
        print("⚠ Неравные группы: при асимметричных метриках t-test не держит ошибку на хвостах; LRU-кеши дают фору большой группе (гл. 18, 19).")


def cmd_peek_sim(a):
    import random
    rnd = random.Random(a.seed)
    zc = z(1 - a.alpha / 2)
    fp_end = fp_peek = 0
    for _ in range(a.runs):
        st = sc = 0.0
        stt = scc = 0.0
        n = 0
        peeked = False
        for day in range(1, a.days + 1):
            for _ in range(a.users_per_day):
                xt = rnd.random() < a.p; xc = rnd.random() < a.p
                st += xt; sc += xc
            n += a.users_per_day
            pt, pc = st / n, sc / n
            se = math.sqrt(max(pt * (1 - pt) + pc * (1 - pc), 1e-12) / n)
            zz = (pt - pc) / se
            if abs(zz) > zc:
                peeked = True
        fp_end += abs(zz) > zc
        fp_peek += peeked
    print(f"A/A-симуляция: {a.runs} прогонов, {a.days} дн. по {a.users_per_day} польз./группа в день, проверка каждый день")
    print(f"Ложно значимых при одной проверке в конце: {fp_end / a.runs:.1%} (ожидается {a.alpha:.0%})")
    print(f"Ложно значимых, если остановиться при первой значимости: {fp_peek / a.runs:.1%} — в {fp_peek / max(fp_end, 1):.1f} раза больше")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def metric(p):
        p.add_argument("--p", type=float, help="базовая конверсия (0.037 = 3.7%%)")
        p.add_argument("--sd", type=float, help="стандартное отклонение непрерывной метрики")
        p.add_argument("--mean", type=float, help="среднее непрерывной метрики")
        p.add_argument("--mde-rel", type=float, help="минимальный эффект, относительный (0.05 = 5%%)")
        p.add_argument("--mde-abs", type=float, help="минимальный эффект, абсолютный")
        p.add_argument("--alpha", type=float, default=0.05)

    p = sub.add_parser("sample-size"); metric(p)
    p.add_argument("--power", type=float, default=0.8)
    p.add_argument("--variants", type=int, default=2)
    p.set_defaults(f=cmd_sample_size)

    p = sub.add_parser("power"); metric(p)
    p.add_argument("--n", type=int, required=True, help="пользователей на вариант")
    p.set_defaults(f=cmd_power)

    p = sub.add_parser("srm")
    p.add_argument("--counts", type=int, nargs="+", required=True)
    p.add_argument("--ratios", type=float, nargs="+", help="плановые доли (по умолчанию равные)")
    p.add_argument("--threshold", type=float, default=0.001)
    p.set_defaults(f=cmd_srm)

    p = sub.add_parser("fpr")
    p.add_argument("--success-rate", type=float, required=True, help="доля успешных идей (0.1 = 10%%)")
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--power", type=float, default=0.8)
    p.add_argument("--target", type=float, default=0.05, help="желаемый FPR")
    p.set_defaults(f=cmd_fpr)

    p = sub.add_parser("ztest")
    p.add_argument("--c-n", type=int, required=True); p.add_argument("--c-conv", type=int, required=True)
    p.add_argument("--t-n", type=int, required=True); p.add_argument("--t-conv", type=int, required=True)
    p.add_argument("--alpha", type=float, default=0.05)
    p.set_defaults(f=cmd_ztest)

    p = sub.add_parser("skew-min")
    p.add_argument("--skewness", type=float, required=True)
    p.set_defaults(f=cmd_skew_min)

    p = sub.add_parser("duration")
    p.add_argument("--n-per-variant", type=int, required=True)
    p.add_argument("--variants", type=int, default=2)
    p.add_argument("--daily-users", type=int, required=True, help="новых уникальных пользователей в день")
    p.add_argument("--traffic-share", type=float, default=1.0, help="доля трафика в эксперименте")
    p.set_defaults(f=cmd_duration)

    p = sub.add_parser("dilute")
    p.add_argument("--trig-delta", type=float, required=True, help="абсолютная разница метрики (T−C) у триггерных")
    p.add_argument("--trig-n", type=int, required=True, help="триггерных пользователей в группе")
    p.add_argument("--trig-mean", type=float, help="значение метрики у триггерного контроля (для сравнения с наивным)")
    p.add_argument("--overall-mean", type=float, required=True, help="значение метрики у всего контроля (M_ωC)")
    p.add_argument("--overall-n", type=int, required=True, help="всех пользователей в группе")
    p.set_defaults(f=cmd_dilute)

    p = sub.add_parser("multi")
    p.add_argument("--k", type=int, help="число метрик/сравнений")
    p.add_argument("--pvalues", type=float, nargs="+", help="список p-values для BH/Bonferroni")
    p.add_argument("--names", nargs="+", help="имена метрик в том же порядке")
    p.add_argument("--alpha", type=float, default=0.05)
    p.set_defaults(f=cmd_multi)

    p = sub.add_parser("fisher")
    p.add_argument("--pvalues", type=float, nargs="+", required=True)
    p.set_defaults(f=cmd_fisher)

    p = sub.add_parser("pct-ci")
    p.add_argument("--mean-t", type=float, required=True); p.add_argument("--mean-c", type=float, required=True)
    p.add_argument("--se-t", type=float); p.add_argument("--se-c", type=float)
    p.add_argument("--sd-t", type=float); p.add_argument("--sd-c", type=float)
    p.add_argument("--n-t", type=int); p.add_argument("--n-c", type=int)
    p.add_argument("--alpha", type=float, default=0.05)
    p.set_defaults(f=cmd_pct_ci)

    p = sub.add_parser("split")
    p.add_argument("--treatment-share", type=float, required=True, help="доля Treatment в эксперименте (0.1 = 10/90)")
    p.set_defaults(f=cmd_split)

    p = sub.add_parser("peek-sim")
    p.add_argument("--runs", type=int, default=500)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--users-per-day", type=int, default=500)
    p.add_argument("--p", type=float, default=0.05)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(f=cmd_peek_sim)

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
