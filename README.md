 [![CI](https://github.com/yakin653/finsight/actions/workflows/ci.yml/badge.svg)](https://github.com/yakin653/finsight/actions/workflows/ci.yml)

\# FinSight



> Pipeline complet d'analyse financière : des données brutes à l'analyse générée par IA.



\*\*FinSight\*\* collecte des données de marché et des actualités financières, entraîne des modèles de prédiction, analyse le sentiment des news avec un modèle NLP spécialisé finance, puis génère une analyse en langage naturel — le tout exposé via une API REST containerisée.



\---



\## 🎯 Ce que fait FinSight



1\. \*\*Collecte\*\* les prix historiques de 10 actifs (actions, crypto, or, forex, indices) via Yahoo Finance

2\. \*\*Stocke\*\* les données dans PostgreSQL (24 000+ lignes de prix)

3\. \*\*Récupère\*\* les actualités financières via Finnhub (1 000+ articles)

4\. \*\*Analyse le sentiment\*\* de chaque article avec \*\*FinBERT\*\*, un modèle NLP spécialisé finance

5\. \*\*Entraîne\*\* des modèles de ML (LogisticRegression, RandomForest, XGBoost) pour prédire la direction des cours

6\. \*\*Backteste\*\* une stratégie de croisement de moyennes mobiles avec frais de transaction

7\. \*\*Génère une analyse\*\* en français à partir de tous les indicateurs calculés — via un LLM local (\*\*Ollama + Qwen2.5\*\*)

8\. \*\*Expose\*\* le tout via une API FastAPI containerisée



\---



\## 🏗️ Architecture



```

┌──────────────────┐     ┌──────────────────┐

│  Yahoo Finance   │     │     Finnhub      │

│    (prix OHLCV)  │     │      (news)      │

└────────┬─────────┘     └────────┬─────────┘

&#x20;        │                        │

&#x20;        ▼                        ▼

┌────────────────────────────────────────────┐

│         data\_pipeline/                     │

│  • fetch\_prices.py   (10 actifs)           │

│  • fetch\_news.py     (Finnhub + FinBERT)   │

└────────────────┬───────────────────────────┘

&#x20;                │

&#x20;                ▼

&#x20;       ┌──────────────────┐

&#x20;       │   PostgreSQL 16  │

&#x20;       │  market\_data     │

&#x20;       │  news            │

&#x20;       └────────┬─────────┘

&#x20;                │

&#x20;   ┌────────────┼────────────┬────────────┐

&#x20;   ▼            ▼            ▼            ▼

┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐

│   ML   │ │ Backtest │ │   NLP    │ │   Risk   │

│  (sklearn│ │ (MA20/50)│ │(FinBERT) │ │(Sharpe…) │

│  /XGB) │ │          │ │          │ │          │

└────┬───┘ └─────┬────┘ └─────┬────┘ └─────┬────┘

&#x20;    │           │            │            │

&#x20;    └───────────┴────────────┴────────────┘

&#x20;                    │

&#x20;                    ▼

&#x20;           ┌──────────────────┐

&#x20;           │  Ollama/Qwen2.5  │

&#x20;           │  (analyse LLM)   │

&#x20;           └────────┬─────────┘

&#x20;                    │

&#x20;                    ▼

&#x20;           ┌──────────────────┐

&#x20;           │   FastAPI        │

&#x20;           │   (backend)      │

&#x20;           └────────┬─────────┘

&#x20;                    │

&#x20;                    ▼

&#x20;           ┌──────────────────┐

&#x20;           │  Docker Compose  │

&#x20;           │  db + backend    │

&#x20;           └──────────────────┘

```



\---



\## 📊 Exemple de réponse — `GET /insight/AAPL`



```json

{

&#x20; "symbol": "AAPL",

&#x20; "date": "2026-09-25T00:00:00",

&#x20; "prix\_actuel": 341.07,

&#x20; "tendance": "haussière",

&#x20; "ma20": 329.4,

&#x20; "ma50": 321.74,

&#x20; "volatilite\_annualisee\_pct": 30.46,

&#x20; "max\_drawdown\_pct": -38.52,

&#x20; "sentiment\_30j": {

&#x20;   "score\_moyen": 0.075,

&#x20;   "interpretation": "neutre",

&#x20;   "nombre\_articles": 245

&#x20; },

&#x20; "probabilite\_hausse\_pct": null,

&#x20; "analyse\_llm": "Le cours d'AAPL à la date du 25 septembre 2026 est de 341,07 $, ce qui correspond à une tendance haussière. Le prix moyen sur les 20 jours (MA20) est de 329,40 $, et le prix moyen sur les 50 jours (MA50) est de 321,74 $. La volatilité annualisée est estimée à 30,46 %. Le maximum de drawdown atteint est de -38,52 %, ce qui indique une baisse significative. Le sentiment des dernières 30 jours est neutre, avec un score moyen de 0,075 sur 245 articles analysés.",

&#x20; "disclaimer": "⚠️ AVERTISSEMENT — Cette analyse est produite à titre informatif et pédagogique. Elle ne constitue PAS un conseil financier."

}

```



\---



\## 🧠 Stack technique



| Composant | Technologie |

|---|---|

| \*\*Langage\*\* | Python 3.13 |

| \*\*Base de données\*\* | PostgreSQL 16 (Docker) |

| \*\*ORM / DB\*\* | SQLAlchemy 2.0, psycopg2 |

| \*\*Data\*\* | pandas, numpy |

| \*\*Data source\*\* | yfinance, Finnhub API, requests |

| \*\*NLP\*\* | HuggingFace Transformers, FinBERT (`ProsusAI/finbert`) |

| \*\*ML\*\* | scikit-learn, XGBoost |

| \*\*Suivi d'expériences\*\* | MLflow |

| \*\*LLM local\*\* | Ollama + Qwen2.5 3B Instruct |

| \*\*Backend\*\* | FastAPI, Uvicorn, Pydantic |

| \*\*Containerisation\*\* | Docker, Docker Compose |

| \*\*Notebooks\*\* | JupyterLab |



\---
## 🖥️ Interface
### 🎬 Démo (30 s)

[![Démo FinSight](docs/screenshot_dashboard.png)](docs/demo.mp4)

*Cliquez sur l'image pour voir la démo vidéo.*

### Dashboard principal
![Dashboard](docs/screenshot_dashboard.png)

### Analyse technique (chandelier + volume)
![Chandelier](docs/screenshot_chart.png)

### Actualités et sentiment FinBERT
![News](docs/screenshot_news.png)

### Vue d'ensemble du marché
![Marché](docs/screenshot_market.png)

---


\## 🚀 Démarrage rapide



\### Prérequis

\- Docker Desktop installé et démarré

\- \[Ollama](https://ollama.com/download) installé avec le modèle `qwen2.5:3b-instruct` :

&#x20; ```bash

&#x20; ollama pull qwen2.5:3b-instruct

&#x20; ```



\### Lancement



```bash

\# 1. Cloner le repo

git clone https://github.com/yakin653/finsight

cd finsight



\# 2. Créer un fichier .env avec vos clés

cp .env.example .env

\# Éditer .env (voir section Configuration ci-dessous)



\# 3. Démarrer la stack Docker

docker compose up --build

```



L'API sera accessible sur \*\*http://localhost:8000\*\*  

Documentation interactive : \*\*http://localhost:8000/docs\*\*



\---



\## ⚙️ Configuration (`.env`)



```bash

\# Base de données (Docker)

DATABASE\_URL=postgresql://postgres:monmdp@localhost:5432/finsight



\# Finnhub (news financières) — compte gratuit sur https://finnhub.io

FINNHUB\_API\_KEY=votre\_cle\_finnhub

```



> \*\*Ollama\*\* tourne en dehors de Docker. Il doit être lancé sur la machine hôte  

> (`ollama serve` ou via l'application Ollama).



\---



\## 📁 Structure du projet



```

finsight/

├── data\_pipeline/          # Ingestion des données

│   ├── fetch\_prices.py     #   → Yahoo Finance → market\_data

│   └── fetch\_news.py       #   → Finnhub + FinBERT → news

├── ml/

│   ├── notebooks/          # Exploration (EDA, modélisation)

│   ├── src/

│   │   ├── sentiment.py    # FinBERT (scoring de sentiment)

│   │   ├── risk.py         # Sharpe, Sortino, max drawdown…

│   │   ├── backtest.py     # Stratégie MA20/MA50 + frais

│   │   └── insight.py      # Génération d'analyse via Ollama

│   └── models/             # Modèles entraînés (.pkl)

├── backend/

│   └── app/

│       ├── main.py         # Point d'entrée FastAPI

│       ├── routers/        # Routes HTTP

│       ├── services/       # Logique métier

│       ├── schemas/        # Schémas Pydantic

│       └── db/             # Accès base de données

├── docker-compose.yml      # Orchestration (db + backend)

└── README.md

```



\---



\## 🔬 Méthodologie ML — et honnêteté sur les résultats



FinSight applique une démarche rigoureuse en ML financier :



\- \*\*Découpage temporel\*\* (pas de `train\_test\_split` aléatoire) → pas de fuite de données

\- \*\*Baseline naïve\*\* obligatoire : \*"toujours prédire hausse"\* (accuracy ≈ 53 %)

\- \*\*Frais de transaction\*\* inclus dans le backtest (0,1 % à chaque changement de position)

\- \*\*Signal décalé\*\* (`shift(1)`) : on agit le lendemain, pas le jour même



\### Résultats (AAPL, 2018–2026)



| Modèle | Accuracy | vs Baseline |

|---|---|---|

| \*\*Baseline\*\* (toujours hausse) | \*\*52,9 %\*\* | référence |

| LogisticRegression | 50,8 % | −2,1 pts |

| RandomForest | 52,7 % | −0,2 pts |

| XGBoost | 49,9 % | −3,0 pts |



> \*\*Aucun modèle ne bat la baseline.\*\* Ce résultat est \*\*attendu\*\* : les cours d'actions à court terme sont proches d'une marche aléatoire. Prédire leur direction à partir de simples indicateurs techniques est un problème \*\*extrêmement difficile\*\*. Un score plus élevé (70 %+) indiquerait presque toujours une fuite de données.



C'est \*\*cette honnêteté méthodologique\*\* qui différencie un projet de data science sérieux d'un projet qui triche.



\### Backtest



| Métrique | Stratégie MA20/50 | Buy \& Hold |

|---|---|---|

| Total return | +250 % | +740 % |

| Sharpe | 0,79 | 0,96 |

| Max drawdown | \*\*−29,8 %\*\* | −38,5 % |



La stratégie de suivi de tendance \*\*réduit significativement le risque\*\* (drawdown plus faible, volatilité plus basse), mais \*\*sous-performe\*\* le Buy \& Hold en rendement sur un actif haussier.



\---



\## ⚠️ Disclaimer



Ce projet est \*\*pédagogique\*\*. Les analyses produites par FinSight \*\*ne constituent PAS un conseil financier\*\*. Les performances passées ne préjugent pas des performances futures.



\---



\## 👤 Auteur



\*\*Yakin Nmiri\*\* — \[@yakin653](https://github.com/yakin653)



\---



\## 📄 Licence



MIT — voir \[LICENSE](LICENSE) (à ajouter).
## 🖥️ Interface utilisateur

![Streamlit UI](docs/streamlit.png)


