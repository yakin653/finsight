"""
Service insight : combine prix + ML + sentiment + LLM.

Réutilise la logique de ml/src/insight.py pour éviter la duplication.
"""
import sys
from pathlib import Path

# Ajouter ml/src au path pour importer insight.py
ROOT = Path(__file__).resolve().parents[3]
ML_SRC = ROOT / "ml" / "src"
sys.path.insert(0, str(ML_SRC))

import insight as ml_insight   # noqa: E402


DISCLAIMER = (
    "⚠️  AVERTISSEMENT — Cette analyse est produite à titre informatif et pédagogique. "
    "Elle ne constitue PAS un conseil financier, ni une recommandation d'achat ou de vente. "
    "Les performances passées ne préjugent pas des performances futures."
)


def get_insight(symbol: str) -> dict:
    """
    Génère l'analyse complète pour un symbole :
    1. Rassemble les données (prix, ML, sentiment) via build_context
    2. Envoie à Ollama pour l'explication
    3. Ajoute le disclaimer
    """
    context = ml_insight.build_context(symbol)
    analyse = ml_insight.generate_insight(context)

    # On ajoute le disclaimer et l'analyse LLM
    context["disclaimer"] = DISCLAIMER
    context["analyse_llm"] = analyse

    return context