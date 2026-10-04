"""
Service signal : combine 3 sources en un signal ACHAT/VENTE/NEUTRE.
"""
from sqlalchemy.engine import Engine

from app.services import data_service, news_service


def _technique_score(ma20: float, ma50: float) -> tuple[float, str]:
    """Score technique base sur les moyennes mobiles."""
    if ma20 > ma50:
        return 1.0, "Tendance haussiere (MA20 > MA50)"
    elif ma20 < ma50:
        return -1.0, "Tendance baissiere (MA20 < MA50)"
    return 0.0, "Tendance neutre"


def _sentiment_score(sent_score: float) -> tuple[float, str]:
    """Score base sur le sentiment des news."""
    if sent_score > 0.1:
        return 1.0, f"Sentiment positif ({sent_score:+.3f})"
    elif sent_score < -0.1:
        return -1.0, f"Sentiment negatif ({sent_score:+.3f})"
    return 0.0, f"Sentiment neutre ({sent_score:+.3f})"


def _ml_score(proba: float | None) -> tuple[float, str]:
    """Score base sur la probabilite du modele ML."""
    if proba is None:
        return 0.0, "Modele ML indisponible"
    if proba > 0.55:
        return 1.0, f"Probabilite de hausse elevee ({proba:.1%})"
    elif proba < 0.45:
        return -1.0, f"Probabilite de hausse faible ({proba:.1%})"
    return 0.0, f"Probabilite incertaine ({proba:.1%})"


def get_signal(engine: Engine, symbol: str) -> dict:
    """
    Genere un signal ACHAT/VENTE/NEUTRE pour un symbole.

    Combine :
    - Tendance technique (MA20 vs MA50)
    - Sentiment des news (FinBERT)
    - Probabilite du modele ML
    """
    # 1. Infos techniques
    info = data_service.get_asset_info(engine, symbol)
    if info is None:
        return None

    tech_score, tech_reason = _technique_score(info["ma20"], info["ma50"])

    # 2. Sentiment des news
    news = news_service.get_news(engine, symbol, days=30, limit=100)
    sent_score, sent_reason = _sentiment_score(news["sentiment_score"])

    # 3. Probabilite ML (non disponible pour l'instant)
    # TODO : charger best_model.pkl et calculer
    ml_proba = None
    ml_score, ml_reason = _ml_score(ml_proba)

    # --- Score composite ---
    total_score = tech_score + sent_score + ml_score
    max_score = 3.0
    confidence = abs(total_score) / max_score

    if total_score > 1.5:
        signal = "ACHAT"
        emoji = "🟢"
        color = "green"
    elif total_score < -1.5:
        signal = "VENTE"
        emoji = "🔴"
        color = "red"
    else:
        signal = "NEUTRE"
        emoji = "🟡"
        color = "orange"

    return {
        "symbol": symbol,
        "signal": signal,
        "emoji": emoji,
        "color": color,
        "score": round(total_score, 2),
        "max_score": max_score,
        "confidence_pct": round(confidence * 100, 1),
        "components": {
            "technique": {"score": tech_score, "reason": tech_reason},
            "sentiment": {"score": sent_score, "reason": sent_reason},
            "ml":        {"score": ml_score,   "reason": ml_reason},
        },
    }