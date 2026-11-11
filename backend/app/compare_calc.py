"""Comparaison en base 100 et pires séances d'un portefeuille équipondéré."""
from __future__ import annotations

from datetime import date

from .analysis import compute_indicators


def align(series: dict[str, list[tuple[date, float]]]) -> tuple[list[date], dict[str, list[float]]]:
    maps = {symbol: {day: close for day, close in rows if close} for symbol, rows in series.items()}
    common: set[date] | None = None
    for values in maps.values():
        days = set(values)
        common = days if common is None else common & days
    if not common:
        return [], {}
    ordered = sorted(common)
    return ordered, {symbol: [maps[symbol][day] for day in ordered] for symbol in maps}


def base100(values: list[float]) -> list[float]:
    if not values or not values[0]:
        return []
    return [round(value / values[0] * 100, 2) for value in values]


def compare_frame(series: dict[str, list[tuple[date, float]]]) -> dict:
    days, prices = align(series)
    if len(days) < 5:
        return {"status": "insuffisant", "message": "Pas assez de séances communes pour superposer ces actifs."}
    columns = []
    frame = []
    for symbol, values in prices.items():
        try:
            indicators = compute_indicators(values, [0.0] * len(values))
        except Exception:
            indicators = {}
        window = round((values[-1] / values[0] - 1) * 100, 2) if values[0] else None
        columns.append({
            "symbol": symbol,
            "variation_fenetre_pct": window,
            "volatilite_annualisee_pct": indicators.get("volatilite_annualisee_pct"),
            "max_drawdown_pct": indicators.get("max_drawdown_pct"),
            "dernier": round(values[-1], 2),
        })
        scaled = base100(values)
        for index, day in enumerate(days):
            if len(frame) <= index:
                frame.append({"date": day.isoformat()})
            frame[index][symbol] = scaled[index]
    return {
        "status": "ok",
        "points": frame,
        "metriques": columns,
        "avertissement": "Base 100 au premier jour commun. Le passé ne prédit pas l'avenir.",
    }


def stress_frame(series: dict[str, list[tuple[date, float]]]) -> dict:
    days, prices = align(series)
    note = "Le passé ne prédit pas l'avenir. Une fenêtre d'environ six mois est courte."
    if len(days) < 21:
        return {"status": "insuffisant", "message": "Il faut au moins 20 séances communes.", "avertissement": note}
    returns = {
        symbol: [values[index] / values[index - 1] - 1 for index in range(1, len(values))]
        for symbol, values in prices.items()
    }
    count = len(returns)
    portfolio = []
    for index in range(len(days) - 1):
        portfolio.append(sum(returns[symbol][index] for symbol in returns) / count)
    worst = sorted(range(len(portfolio)), key=lambda index: portfolio[index])[:5]
    rows = []
    for index in worst:
        rows.append({
            "date": days[index + 1].isoformat(),
            "perte_pct": round(portfolio[index] * 100, 2),
            "contributions": {
                symbol: round(returns[symbol][index] / count * 100, 2) for symbol in returns
            },
        })
    return {"status": "ok", "jours": rows, "avertissement": note}
