"""IsolationForest sur les cours déjà en base. Aucun point n'est inventé."""
from __future__ import annotations

import numpy as np
from sklearn.ensemble import IsolationForest


def detect_points(closes: list[float], dates: list[str]) -> dict:
    if len(closes) < 60 or len(dates) != len(closes):
        return {
            "status": "insufficient_data",
            "message": "Il faut au moins 60 séances pour chercher une anomalie.",
            "dates": [],
        }
    prices = np.asarray(closes, dtype=float)
    if np.any(prices <= 0) or not np.all(np.isfinite(prices)):
        return {"status": "insufficient_data", "message": "Des cours ne sont pas exploitables.", "dates": []}
    log_ret = np.diff(np.log(prices), prepend=np.nan)
    vol = np.full(len(prices), np.nan)
    gap = np.full(len(prices), np.nan)
    for index in range(20, len(prices)):
        window = log_ret[index - 19 : index + 1]
        vol[index] = float(np.std(window, ddof=1))
        ma20 = float(np.mean(prices[index - 19 : index + 1]))
        gap[index] = (prices[index] - ma20) / ma20 if ma20 else np.nan
    usable = np.isfinite(log_ret) & np.isfinite(vol) & np.isfinite(gap)
    if int(usable.sum()) < 60:
        return {"status": "insufficient_data", "message": "Moins de 60 séances complètes.", "dates": []}
    matrix = np.column_stack([log_ret[usable], vol[usable], gap[usable]])
    model = IsolationForest(contamination=0.02, random_state=42)
    labels = model.fit_predict(matrix)
    chosen = []
    cursor = 0
    for index, keep in enumerate(usable):
        if not keep:
            continue
        if labels[cursor] == -1:
            chosen.append(dates[index])
        cursor += 1
    return {"status": "ok", "message": None, "dates": chosen, "count": len(chosen)}
