# Code retiré du chemin vivant

Ces fichiers n'étaient pas montés par `backend/app/main.py`. Ils restent ici pour l'historique du dépôt.

- `backend/app/routers/news.py`, `signal.py`, `insight.py`, `anomalies.py` : anciennes routes. Certaines construisaient le SQL en collant le symbole dans la requête.
- `backend/app/services/news_service.py`, `signal_service.py`, `insight_service.py`, `anomaly_service.py`, `data_service.py` : services associés. `data_service.py` utilisait un `SELECT` en f-string.
- `backend/app/schemas/news.py`, `signal.py`, `insight.py` : schémas de ces routes.
- `data_pipeline/fetch_news.py` et `ml/src/sentiment.py` : collecte et FinBERT. PyTorch est trop lourd pour le démarrage de l'image Docker. Le sentiment des titres reste `NULL`.
- `ml/src/insight.py` : script CLI qui parlait à ces services. L'analyse servie par l'API est `backend/app/chat_engine.py`.

Les routes actuelles lisent `market_data` avec SQLAlchemy, paramètres liés, pas de chaîne SQL assemblée.
