"""Règles d'envoi des notifications. Fonctions pures, testées sans base."""
from __future__ import annotations


def in_quiet_hours(start: int, end: int, hour: int) -> bool:
    """Heures calmes, y compris quand la plage passe minuit (22 → 7)."""
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def matches_interest(symbol: str, title: str, favorites: list[str], keywords: list[str]) -> bool:
    if symbol.upper() in {item.upper() for item in favorites}:
        return True
    lowered = title.lower()
    return any(word.lower() in lowered for word in keywords if word.strip())


def delivery_mode(prefs: dict, hour: int) -> str:
    """instant, digest, ou skip si l'heure est calme ou si le résumé n'est pas à l'heure choisie."""
    start = int(prefs.get("quiet_start", 22))
    end = int(prefs.get("quiet_end", 7))
    if in_quiet_hours(start, end, hour):
        return "skip"
    if prefs.get("frequence") == "quotidien":
        return "digest" if hour == int(prefs.get("heure", 8)) else "skip"
    return "instant"
