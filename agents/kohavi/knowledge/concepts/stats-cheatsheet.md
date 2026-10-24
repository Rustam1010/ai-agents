# Статистика A/B: шпаргалка (формулы → команды)

| Что | Формула | Команда |
|---|---|---|
| Выборка на вариант (α=0.05, 80%) | n ≈ 16σ²/δ², σ²=p(1−p) для конверсии | `abstat.py sample-size` |
| Мощность | 1−β = Φ(δ/SE − z₁₋α/₂), SE = σ√(2/n); обнаружимый δ ≈ 2.8·SE | `abstat.py power` |
| Длительность | n·k / (трафик·доля), округлить до недель | `abstat.py duration` |
| SRM | χ² по плановым долям, p<0.001 | `abstat.py srm`, `abdata.py segments` |
| False Positive Risk | α/2·π / (α/2·π + (1−β)(1−π)), π = 1 − доля успехов | `abstat.py fpr` |
| Нормальность среднего | n ≥ 355·s² на вариант при \|s\|>1 | `abstat.py skew-min`, `abdata.py summary` |
| Δ% и его CI | var(Δ%) ≈ var(T̄)/C̄² + T̄²var(C̄)/C̄⁴ | `abstat.py pct-ci`, `abdata.py summary` |
| Ratio-метрика (CTR) | var(X̄/Ȳ) ≈ var(X̄)/Ȳ² − 2X̄cov/Ȳ³ + X̄²var(Ȳ)/Ȳ⁴ | `abdata.py ratio` |
| CUPED | Y′ = Y − θ(X − X̄), θ = cov(Y,X)/var(X) | `abdata.py summary --pre` |
| Множественные проверки | P(≥1 ложной) = 1−(1−α)^k; Bonferroni α/k; BH; tiered 0.05/0.01/0.001 | `abstat.py multi` |
| Fisher (реплики) | −2Σln pᵢ ~ χ²(2k) | `abstat.py fisher` |
| Разбавление триггера | Δθ·Nθ / (M_ωC·N_ω) | `abstat.py dilute` |
| Неравный сплит | var ∝ 1/(q(1−q)); MPR = 50/50 | `abstat.py split` |
| Peeking | рост ложных срабатываний в 5–10 раз | `abstat.py peek-sim` |
| A/A | p ~ U(0,1), ~5% значимых; KS | `abdata.py aa` |
| Post-hoc power (не использовать) | Φ(z₁₋ₚ/₂ − z₁₋α/₂) — функция только от p | — |

## Ориентиры
- Доля успешных идей: Microsoft ~33%, Bing ~15%, Booking/Google Ads/Netflix ~10%, Airbnb Search ~8%, Slack (монетизация) ~30%.
- Успех на ключевой метрике зрелого продукта: +0.1–2%. Bing Relevance: +2% OEC за год от всех экспериментов.
- Трафик: тысячи, лучше десятки тысяч пользователей. Длительность: ≥1 неделя на MPR.
- SRM есть в ~6% экспериментов Microsoft. Ключевых метрик ≤ 5 (при k=5 P(ложной)=23%, при k=10 — 40%).
- Скорость: Bing — 100 мс = 0.6% выручки (2012), 4 мс окупают инженера (2015); Amazon — 100 мс = 1% продаж.
