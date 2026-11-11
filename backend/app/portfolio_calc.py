"""Risque d'un portefeuille équipondéré, sur les dates communes seulement."""
from __future__ import annotations

import math
from datetime import date


def _returns(points: list[tuple[date, float]]) -> dict[date, float]:
    ordered = sorted(points, key=lambda item: item[0])
    out: dict[date, float] = {}
    previous = None
    for day, close in ordered:
        if previous and previous > 0 and close > 0:
            out[day] = (close / previous) - 1.0
        previous = close
    return out


def portfolio_risk(series: dict[str, list[tuple[date, float]]], level: str) -> dict:
    symbols = sorted(series)
    if len(symbols) < 2:
        return {"status": "insufficient_data", "message": "Ajoute au moins deux symboles.", "symbols": symbols}
    mapped = {symbol: _returns(series[symbol]) for symbol in symbols}
    common = set.intersection(*(set(mapped[symbol]) for symbol in symbols))
    days = sorted(common)
    if len(days) < 20:
        return {
            "status": "insufficient_data",
            "message": f"Seulement {len(days)} séances communes. Il en faut 20. Les actions et BTC-USD ne cotent pas les mêmes jours.",
            "symbols": symbols,
            "seances_communes": len(days),
        }
    matrix = [[mapped[symbol][day] for day in days] for symbol in symbols]
    count = len(symbols)
    corr = []
    for left in range(count):
        row = []
        for right in range(count):
            row.append(round(_corr(matrix[left], matrix[right]), 2))
        corr.append(row)
    basket = [sum(mapped[symbol][day] for symbol in symbols) / count for day in days]
    vol = _std(basket) * math.sqrt(252) * 100
    off = [corr[i][j] for i in range(count) for j in range(count) if i != j]
    average = sum(off) / len(off) if off else 0.0
    diversification = round(max(0.0, min(100.0, (1 - average) * 50)), 1)
    contributions = []
    for index, symbol in enumerate(symbols):
        alone = _std(matrix[index]) * math.sqrt(252) * 100
        contributions.append({"symbol": symbol, "volatilite_annualisee_pct": round(alone, 1)})
    top = max(contributions, key=lambda item: item["volatilite_annualisee_pct"])
    return {
        "status": "ok",
        "symbols": symbols,
        "seances_communes": len(days),
        "correlation": corr,
        "volatilite_portefeuille_pct": round(vol, 1),
        "diversification": diversification,
        "plus_contributeur": top["symbol"],
        "contributions": contributions,
        "explication": _explain(level, top["symbol"], diversification),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    center = _mean(values)
    variance = sum((value - center) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def _corr(left: list[float], right: list[float]) -> float:
    if _std(left) == 0 or _std(right) == 0:
        return 0.0
    center_l = _mean(left)
    center_r = _mean(right)
    cov = sum((a - center_l) * (b - center_r) for a, b in zip(left, right)) / (len(left) - 1)
    return cov / (_std(left) * _std(right))


def _explain(level: str, top: str, score: float) -> str:
    base = (
        f"Portefeuille équipondéré. Score de diversification {score}/100 : "
        "100 si les rendements communs ne bougent pas ensemble. "
        f"L'actif dont la volatilité propre est la plus haute est {top}. "
        "Ce n'est pas un conseil d'allocation."
    )
    if level == "debutant":
        return "Deux actifs qui montent et baissent ensemble protègent moins qu'on ne le croit. " + base
    return base
