---
name: analyze-data
description: Проанализировать сырые данные A/B-теста из CSV (строка = пользователь) — SRM, эффекты с CI, capping, CUPED, ratio-метрики по delta method, SRM по сегментам, симуляция A/A — через scripts/abdata.py.
---

1. Узнай путь к CSV и колонки: вариант, контроль, метрики, данные до эксперимента (для CUPED), сегменты (день, браузер, платформа), числитель и знаменатель ratio-метрик.
   Посмотри файл: `head -5 <file>`.
2. **Сначала доверие:**
   - `python3 scripts/abdata.py summary <file> --variant <col> --metric <m>` — первая строка показывает SRM;
   - если SRM ≥ пограничного → `python3 scripts/abdata.py segments <file> --variant <col> --segment <seg>` по каждому сегменту, затем субагент `srm-detective`. При SRM дальше результаты не интерпретировать.
3. **Метрики:**
   - асимметричные (выручка, количество) — добавить `--cap <порог>` (разумный порог: p99 или бизнес-лимит) и сравнить;
   - есть данные до эксперимента — `--pre <col>` (CUPED), показать снижение дисперсии;
   - ratio-метрики (CTR и т.п.) — `abdata.py ratio --num <col> --den <col>` (delta method против наивной).
4. **A/A-проверка метрики** (сомнения в дисперсии или выбросах): `abdata.py aa <file> --variant <col> --only <control> --metric <m>` (с `--cap` и без). Неравномерные p-values → метрику в текущем виде использовать нельзя.
5. Много метрик → `abstat.py multi --pvalues ... --names ...` (BH, tiered).
6. Итог: таблица метрик (Δ%, CI, p, значимо ли с учётом множественности) + проверки доверия + передать в `/review-test` или `/launch-decision`.
