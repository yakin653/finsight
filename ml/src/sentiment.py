"""
FinSight — Analyse de sentiment avec FinBERT.

Charge le modèle FinBERT une seule fois (singleton) pour éviter
de le recharger à chaque appel.
"""
from functools import lru_cache
from transformers import pipeline

MODEL_NAME = "ProsusAI/finbert"


@lru_cache(maxsize=1)
def get_classifier():
    """Charge FinBERT une seule fois et le met en cache."""
    print("🔄 Chargement de FinBERT (une seule fois)...")
    return pipeline(
        "text-classification",
        model=MODEL_NAME,
        top_k=None,   # renvoie tous les labels avec leur score
        device=-1,    # -1 = CPU. Mets 0 si tu as un GPU NVIDIA
    )


def score_text(text: str) -> dict:
    """
    Score une phrase et renvoie un dict :
    {"positive": 0.91, "neutral": 0.05, "negative": 0.04}
    """
    clf = get_classifier()
    results = clf(text)[0]   # liste [{'label': ..., 'score': ...}, ...]
    return {r["label"]: round(r["score"], 4) for r in results}


def dominant_label(scores: dict) -> str:
    """Renvoie le label avec le score le plus élevé."""
    return max(scores, key=scores.get)


if __name__ == "__main__":
    # Petit test
    tests = [
        "Apple beats earnings expectations",
        "Tesla recalls 500,000 vehicles due to brake issue",
        "The company announced its quarterly results today",
        "Apple stock surges 20% after record-breaking earnings",
    ]
    for t in tests:
        s = score_text(t)
        print(f"{dominant_label(s).upper():8s} ({s}) — {t}")