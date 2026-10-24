# Скрипты

## abstat.py — калькулятор A/B-тестов (stdlib, без зависимостей)

Формулы — из Kohavi, Deng, Vermeer 2022 (Intuition Busters) и Kohavi et al. 2014 (Rules of Thumb).
Проверено на примерах из статей (мощность 3% в кейсе GuessTheTest, FPR 26.4% для Airbnb и т.д.).

```sh
# Размер выборки: конверсия 3.7%, хотим ловить +10% относительных
python3 scripts/abstat.py sample-size --p 0.037 --mde-rel 0.10
# Непрерывная метрика: среднее 25, sd 60, MDE 2%
python3 scripts/abstat.py sample-size --mean 25 --sd 60 --mde-rel 0.02
# Мощность при 80 пользователях на вариант
python3 scripts/abstat.py power --p 0.037 --mde-rel 0.10 --n 80
# SRM: 50/50 план, фактические числа
python3 scripts/abstat.py srm --counts 50500 49500
# SRM: план 10/90
python3 scripts/abstat.py srm --counts 10400 89600 --ratios 0.1 0.9
# False Positive Risk при 10% успешных идей
python3 scripts/abstat.py fpr --success-rate 0.10
# Сравнить конверсии
python3 scripts/abstat.py ztest --c-n 10000 --c-conv 370 --t-n 10000 --t-conv 410
# Минимум для асимметричной метрики (skewness 17.9)
python3 scripts/abstat.py skew-min --skewness 17.9
# Длительность: 41.6k на вариант, 5000 новых пользователей в день
python3 scripts/abstat.py duration --n-per-variant 41642 --daily-users 5000
```

### Команды по книге (гл. 15–20)

```sh
python3 scripts/abstat.py dilute --trig-delta 0.03 --trig-n 1000 --trig-mean 1.0 --overall-mean 10 --overall-n 10000
python3 scripts/abstat.py multi --k 10
python3 scripts/abstat.py multi --pvalues 0.001 0.02 0.04 0.2 --names OEC clicks revenue crashes
python3 scripts/abstat.py fisher --pvalues 0.04 0.03
python3 scripts/abstat.py pct-ci --mean-t 3.12 --mean-c 3.21 --se-t 0.02 --se-c 0.02
python3 scripts/abstat.py split --treatment-share 0.1
python3 scripts/abstat.py peek-sim --runs 300 --days 14
```

Проверено на цифрах книги: SRM 821,588/815,482 → p=1.8e-6 (гл. 21); 121,600 и 6,400 пользователей (гл. 20);
P(ложной значимости) 23% и 40% при 5 и 10 метриках (гл. 7); разбавление 3% → 0.03% (гл. 20).

## abdata.py — анализ сырых данных CSV (строка = пользователь)

```sh
# SRM + эффект + capping + CUPED (колонка с метрикой до эксперимента)
python3 scripts/abdata.py summary data.csv --variant variant --metric revenue --cap 200 --pre revenue_pre
# ratio-метрика с delta method (клики/просмотры на пользователя)
python3 scripts/abdata.py ratio data.csv --variant variant --num clicks --den pageviews
# SRM по сегментам — отладка SRM
python3 scripts/abdata.py segments data.csv --variant variant --segment browser
# симуляция A/A на контроле: равномерность p-values
python3 scripts/abdata.py aa data.csv --variant variant --only control --metric revenue --cap 200
```

Проверено на синтетике: SRM найден в подложенном сегменте; A/A с выбросами не проходит, с capping — проходит;
CUPED снизил дисперсию на 28% и дал оценку +3.3% при заложенных +3%.
