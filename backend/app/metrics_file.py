"""Lit les métriques du fichier d'évaluation. Rien n'est écrit en dur dans la page."""
from __future__ import annotations

import json
from pathlib import Path

from .analysis import _model_dirs


def read_model_metrics() -> dict:
    # evaluation.json est suivi par Git, le modèle (*.pkl) ne l'est pas : sur un clone neuf,
    # les métriques doivent rester lisibles même sans le fichier du modèle.
    path = next((folder / "evaluation.json" for folder in _model_dirs() if (folder / "evaluation.json").is_file()), None)
    if path is None:
        raise FileNotFoundError("evaluation.json introuvable")
    raw = json.loads(path.read_text(encoding="utf-8"))
    precision = float(raw["precision_modele"]) * 100.0
    baseline = float(raw["baseline_toujours_hausse"]) * 100.0
    return {
        "modele": raw.get("modele") or "RandomForest",
        "precision_modele_pct": round(precision, 1),
        "baseline_toujours_hausse_pct": round(baseline, 1),
        "avantage_prouve": bool(precision > baseline + 0.05),
        "source": raw.get("source") or "fichier d'évaluation",
        "fichier": "ml/models/evaluation.json",
    }
