"""Listes autorisées du profil. Sert à valider les formulaires."""
from __future__ import annotations

LEVELS = {"debutant", "intermediaire", "expert"}
HORIZONS = {"court", "moyen", "long"}
RISKS = {"prudent", "equilibre", "dynamique"}
ALERT_KINDS = {"mm20", "mm50", "repli", "volatilite"}


def clean_list(values: list[str] | None, *, limit: int, item_max: int) -> list[str]:
    cleaned: list[str] = []
    for raw in values or []:
        text = " ".join(str(raw).split())
        if not text or len(text) > item_max:
            continue
        if text not in cleaned:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def default_notif_prefs() -> dict:
    return {"frequence": "instantane", "heure": 8, "quiet_start": 22, "quiet_end": 7}


def clean_prefs(raw: dict | None) -> dict:
    prefs = default_notif_prefs()
    if not isinstance(raw, dict):
        return prefs
    frequence = raw.get("frequence")
    if frequence in {"instantane", "quotidien"}:
        prefs["frequence"] = frequence
    for key in ("heure", "quiet_start", "quiet_end"):
        value = raw.get(key)
        if isinstance(value, int) and 0 <= value <= 23:
            prefs[key] = value
    return prefs
