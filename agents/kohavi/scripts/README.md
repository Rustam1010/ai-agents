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
