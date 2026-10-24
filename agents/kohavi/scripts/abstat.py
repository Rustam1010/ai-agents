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

    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
