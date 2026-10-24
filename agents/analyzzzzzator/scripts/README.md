# Скрипты

- `nhl.py` — база НХЛ (`data/nhl.sqlite`) и аналитика тоталов. Справка: `python3 scripts/nhl.py -h`.
- `nhl_model.py` — модель v2 (броски × реализация × вратарь × b2b + калибровка). Описание и точность — `knowledge/model.md`.

```sh
python3 scripts/nhl.py sync --boxscores 0              # ежедневно: новые матчи и протоколы
python3 scripts/nhl.py slate --date 2026-10-25         # карта дня
python3 scripts/nhl.py match COL NSH --odds tb5.5=1.83 tm5.5=2.00 --home-goalie Saros --away-goalie Blackwood
python3 scripts/nhl.py team COL --last 10
python3 scripts/nhl.py h2h COL NSH                     # очные за 2 сезона (--all — вся история)
python3 scripts/nhl.py league --trend 10
python3 scripts/nhl.py calibrate                       # раз в неделю
python3 scripts/nhl.py backtest --season 20252026
```

Первичная установка на новой машине: `sync --history`, затем `sync --boxscores 20252026 20242025 20232024 20222023 20212022`, затем `calibrate`.
