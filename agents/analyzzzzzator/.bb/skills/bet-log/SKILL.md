---
name: bet-log
description: Журнал прогнозов и ставок — записать прогноз (рынок, кф, вероятность модели, размер), позже — результат и коэффициент закрытия для оценки CLV.
---

Файл `data/bets.csv` (создать, если нет), колонки:
`date,match,market,odds_taken,model_prob,stake_pct,closing_odds,result,profit_units,notes`

1. **Новый прогноз:** дописать строку с date, match (`MTL@TOR`), market (`ТБ5.5`), odds_taken, model_prob, stake_pct; остальные колонки пустые.
2. **Закрытие:** перед матчем или после — closing_odds (если пользователь даст); после матча — result (win/loss/push) и profit_units (stake × (кф−1) или −stake).
3. **Итоги по запросу:** число ставок, ROI, средний EV по модели, **CLV** (средний odds_taken/closing_odds − 1), Brier модели по записанным прогнозам. Посчитать скриптом на Python (`csv`).
4. Не подталкивать к увеличению ставок после серии проигрышей.
