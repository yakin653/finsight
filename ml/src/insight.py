"""
FinSight — Génération d'analyse par Ollama (LLM local, 100% gratuit).

PRINCIPE : on ne demande JAMAIS au LLM d'inventer une analyse.
On lui fournit les chiffres calculés par nos scripts, et il les explique.

Usage :
    python ml/src/insight.py --symbol AAPL
"""
import os
import sys
import json
import argparse
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Ajouter ml/src au path pour importer risk.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import risk   # noqa: E402

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Config Ollama ---
OLLAMA_URL   = "http://localhost:11434/v1/chat/completions"
OLLAMA_MODEL = "qwen2.5:3b-instruct"


# ---------------------------------------------------------------------------
# 1. Rassembler les données pour un symbole
# ---------------------------------------------------------------------------
def build_context(symbol: str) -> dict:
    """Rassemble tous les chiffres utiles pour le LLM."""
    engine = create_engine(DATABASE_URL)

    # --- Prix ---
    prices = pd.read_sql(
        f"SELECT * FROM market_data WHERE symbol = '{symbol}' ORDER BY \"Date\"",
        engine,
        parse_dates=["Date"],
    )
    if prices.empty:
        raise SystemExit(f"❌ Aucune donnée prix pour {symbol}")

    prices["return"] = prices["Close"].pct_change()
    prices["ma20"]   = prices["Close"].rolling(20).mean()
    prices["ma50"]   = prices["Close"].rolling(50).mean()

    last = prices.iloc[-1]
    trend = "haussière" if last["ma20"] > last["ma50"] else "baissière"

    # --- Risque ---
    returns = prices["return"].dropna()
    vol_ann = float(risk.annualized_volatility(returns))
    equity = (1 + returns).cumprod()
    mdd = float(risk.max_drawdown(equity))

    # --- Sentiment (news des 30 derniers jours) ---
    try:
        news = pd.read_sql(
            f"""SELECT pos, neu, neg FROM news
                WHERE symbol = '{symbol}'
                AND date >= NOW() - INTERVAL '30 days'""",
            engine,
        )
    except Exception:
        news = pd.DataFrame()

    if not news.empty:
        sent_score = float((news["pos"] - news["neg"]).mean())
        n_news = int(len(news))
    else:
        sent_score = 0.0
        n_news = 0

    sentiment_label = (
        "positif" if sent_score > 0.1 else
        "négatif" if sent_score < -0.1 else
        "neutre"
    )

    # --- Probabilité du modèle ML (si best_model.pkl existe) ---
    ml_proba = None
    model_path    = Path(__file__).resolve().parent.parent / "models" / "best_model.pkl"
    features_path = Path(__file__).resolve().parent.parent / "models" / "features.json"
    if model_path.exists() and features_path.exists():
        try:
            import joblib
            model = joblib.load(model_path)
            feats = json.load(open(features_path))

            df_feat = prices.copy()
            df_feat["vol20"]    = df_feat["return"].rolling(20).std()
            df_feat["vol_chg"]  = df_feat["Volume"].pct_change()
            df_feat["ret_lag1"] = df_feat["return"].shift(1)
            df_feat["ret_lag5"] = df_feat["return"].shift(5)
            df_feat = df_feat.dropna()
            if not df_feat.empty:
                X_last = df_feat[feats].iloc[[-1]]
                ml_proba = float(model.predict_proba(X_last)[0, 1])
        except Exception as e:
            print(f"⚠️  Modèle ML non utilisé : {e}")

    context = {
        "symbol": symbol,
        "date": str(last["Date"].date()),
        "prix_actuel": round(float(last["Close"]), 2),
        "tendance": trend,
        "ma20": round(float(last["ma20"]), 2),
        "ma50": round(float(last["ma50"]), 2),
        "volatilite_annualisee": round(vol_ann, 4),
        "max_drawdown_historique": round(mdd, 4),
        "sentiment_30j": {
            "score_moyen": round(sent_score, 3),
            "interpretation": sentiment_label,
            "nombre_articles": n_news,
        },
        "probabilite_hausse_modele_ml": round(ml_proba, 3) if ml_proba is not None else "non disponible",
    }
    return context


# ---------------------------------------------------------------------------
# 2. Appeler Ollama (local, gratuit, illimité)
# ---------------------------------------------------------------------------
def generate_insight(context: dict) -> str:
    """Envoie les chiffres à Ollama et récupère une explication."""
    system_prompt = (
        "Tu es un assistant d'analyse de marché. Tu expliques UNIQUEMENT les données fournies, "
        "sans inventer de chiffres ni de faits. Tu mentionnes toujours les risques et les incertitudes. "
        "Tu ne donnes AUCUN conseil d'investissement, aucune recommandation d'achat ou de vente. "
        "Réponds en français, en 4 à 6 phrases maximum, structurées."
    )

    user_message = (
        "Voici les données calculées pour un actif. Explique-les en français, "
        "de façon claire et honnête, en signalant les incertitudes :\n\n"
        + json.dumps(context, indent=2, ensure_ascii=False)
    )

    r = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "temperature": 0.3,
        },
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# 3. CLI
# ---------------------------------------------------------------------------
DISCLAIMER = (
    "⚠️  AVERTISSEMENT — Cette analyse est produite à titre informatif et pédagogique. "
    "Elle ne constitue PAS un conseil financier, ni une recommandation d'achat ou de vente. "
    "Les performances passées ne préjugent pas des performances futures."
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="AAPL")
    args = parser.parse_args()

    print(f"📊 Analyse {args.symbol}...\n")

    # 1. Rassembler les données
    context = build_context(args.symbol)
    print("=== Données envoyées au LLM ===")
    print(json.dumps(context, indent=2, ensure_ascii=False))
    print()

    # 2. Générer l'analyse
    print("=== Analyse (Ollama / Qwen2.5) ===")
    insight = generate_insight(context)
    print(insight)
    print()
    print(DISCLAIMER)


if __name__ == "__main__":
    main()