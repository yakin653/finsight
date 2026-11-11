"""Indicateurs, probabilité du modèle local et recommandation déterministe.

Le LLM ne calcule rien ici. Les chiffres viennent des cours enregistrés.
La probabilité de hausse n'est renvoyée que si best_model.pkl s'applique
réellement. Sinon elle reste nulle : elle n'est jamais inventée.

La note sur 5 mesure la cohérence des signaux, pas un gain attendu.
"""
from __future__ import annotations

import json
import math
import os
import warnings
from functools import lru_cache
from pathlib import Path

MIN_POINTS = 20
MIN_POINTS_ML = 50
ML_UP = 60.0
ML_DOWN = 40.0
VOL_MAX = 45.0
DD_MAX = 30.0
TRADING_DAYS = 252

# Évaluation publiée dans le README du projet (AAPL, 2018-2026).
# Ce ne sont pas des performances garanties, ni un résultat recalculé à la volée.
REPORT_BASELINE_PCT = 52.9
REPORT_RF_ACCURACY_PCT = 52.7

NOTE_DEFINITION = (
    "La note de 1 à 5 mesure la cohérence du signal, pas un rendement. "
    "On part de 1, on ajoute 1 si la MM20 est calculable, 1 si la MM50 l'est, "
    "1 si la volatilité annualisée reste sous 45 % et le repli maximal sous 30 %, "
    "et 1 si le modèle confirme une direction technique non nulle. "
    "Un désaccord entre le modèle et les moyennes plafonne la note à 2."
)

LIMITES = (
    "Lecture pédagogique : ce n'est pas un conseil d'investissement et rien ne garantit "
    "un résultat financier. Les performances passées ne préjugent pas des performances futures. "
    f"Sur l'évaluation documentée du projet, la forêt aléatoire ({REPORT_RF_ACCURACY_PCT:.1f} %) "
    f"ne dépasse pas la baseline « toujours prédire une hausse » ({REPORT_BASELINE_PCT:.1f} %). "
    "Une probabilité de hausse n'est pas un rendement attendu."
)


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _r(value, digits: int):
    if not _finite(value):
        return None
    return round(float(value), digits)


def _sample_std(values: list[float]) -> float | None:
    n = len(values)
    if n < 2 or any(not _finite(v) for v in values):
        return None
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var)


def rolling_mean(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    acc = 0.0
    for i, value in enumerate(values):
        acc += value
        if i >= window:
            acc -= values[i - window]
        if i >= window - 1:
            out[i] = acc / window
    return out


def compute_indicators(closes: list[float], volumes: list[float] | None = None) -> dict:
    """Indicateurs bruts. Les moyennes restent nulles si la fenêtre n'est pas pleine."""
    vols = list(volumes or [0.0] * len(closes))
    n = len(closes)
    price = closes[-1] if n else None
    prev = closes[-2] if n >= 2 else None
    variation = None
    if _finite(price) and _finite(prev) and prev != 0:
        variation = (price / prev - 1.0) * 100.0

    ma20 = sum(closes[-20:]) / 20 if n >= 20 else None
    ma50 = sum(closes[-50:]) / 50 if n >= 50 else None

    returns: list[float | None] = [None]
    for i in range(1, n):
        base = closes[i - 1]
        returns.append(None if not base else closes[i] / base - 1.0)

    realized = [r for r in returns[1:] if _finite(r)]
    vol = None
    if len(realized) >= 2:
        std = _sample_std(realized)
        if std is not None:
            vol = std * math.sqrt(TRADING_DAYS) * 100.0

    drawdown = None
    if n >= 2:
        peak = closes[0]
        worst = 0.0
        for close in closes:
            peak = max(peak, close)
            if peak > 0:
                worst = min(worst, close / peak - 1.0)
        drawdown = worst * 100.0

    if ma20 is None or price is None:
        tendance = "indéterminée"
    elif price > ma20:
        tendance = "haussière"
    elif price < ma20:
        tendance = "baissière"
    else:
        tendance = "neutre"

    return {
        "n": n,
        "prix": price,
        "variation_1j_pct": variation,
        "ma20": ma20,
        "ma50": ma50,
        "volatilite_annualisee_pct": vol,
        "max_drawdown_pct": drawdown,
        "tendance": tendance,
        "returns": returns,
        "volumes": vols,
        "closes": closes,
    }


def technical_signal(ind: dict) -> int:
    """+1 hausse, -1 baisse, 0 mélange ou donnée insuffisante."""
    price, ma20, ma50 = ind.get("prix"), ind.get("ma20"), ind.get("ma50")
    if not _finite(price) or not _finite(ma20):
        return 0
    short = 1 if price > ma20 else -1 if price < ma20 else 0
    if not _finite(ma50):
        return short
    long = 1 if ma20 > ma50 else -1 if ma20 < ma50 else 0
    if short == 0 or long == 0 or short == long:
        return short or long
    return 0


def ml_signal(probability: float | None) -> int | None:
    if not _finite(probability):
        return None
    if probability >= ML_UP:
        return 1
    if probability <= ML_DOWN:
        return -1
    return 0


def high_risk(ind: dict) -> bool:
    vol = ind.get("volatilite_annualisee_pct")
    dd = ind.get("max_drawdown_pct")
    vol_hot = _finite(vol) and vol >= VOL_MAX
    dd_hot = _finite(dd) and abs(dd) >= DD_MAX
    return vol_hot or dd_hot


def coherence_note(ind: dict, tech: int, ml_sig: int | None, status: str) -> int | None:
    if status != "ok":
        return None
    note = 1
    if _finite(ind.get("ma20")):
        note += 1
    if _finite(ind.get("ma50")):
        note += 1
    if not high_risk(ind):
        note += 1
    if ml_sig is not None and tech != 0 and ml_sig == tech:
        note += 1
    if ml_sig is not None and tech != 0 and ml_sig == -tech:
        note = min(note, 2)
    return max(1, min(5, note))


def decide(ind: dict, probability: float | None) -> dict:
    """Règles explicites. Le modèle ne déclenche un achat ou une vente que s'il confirme la technique."""
    tech = technical_signal(ind)
    sig = ml_signal(probability)
    risk = high_risk(ind)
    ma20_ok = ind.get("n", 0) >= MIN_POINTS and _finite(ind.get("ma20"))

    if not ma20_ok:
        return {
            "status": "insufficient_data",
            "decision": None,
            "note": None,
            "base": "donnees_insuffisantes",
            "tech": tech,
            "ml_sig": sig,
            "risque_eleve": risk,
        }

    if sig is None:
        base = "moyennes_mobiles"
        if tech == 1 and not risk:
            decision = "ACHAT"
        elif tech == -1 and not risk:
            decision = "VENTE"
        else:
            decision = "CONSERVATION"
    else:
        base = "modele_ml_et_moyennes_mobiles"
        if sig == 1 and tech == 1 and not risk:
            decision = "ACHAT"
        elif sig == -1 and tech == -1 and not risk:
            decision = "VENTE"
        else:
            decision = "CONSERVATION"

    status = "ok"
    return {
        "status": status,
        "decision": decision,
        "note": coherence_note(ind, tech, sig, status),
        "base": base,
        "tech": tech,
        "ml_sig": sig,
        "risque_eleve": risk,
    }


def _model_dirs() -> list[Path]:
    candidates: list[Path] = []
    env_dir = os.getenv("ML_MODELS_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    candidates.append(Path("/ml/models"))
    candidates.append(Path(__file__).resolve().parents[2] / "ml" / "models")
    return candidates


def _model_dir() -> Path | None:
    for folder in _model_dirs():
        if (folder / "best_model.pkl").is_file() and (folder / "features.json").is_file():
            return folder
    return None


@lru_cache(maxsize=1)
def _load_model():
    folder = _model_dir()
    if folder is None:
        return None
    try:
        import joblib
    except ImportError:
        return None
    with (folder / "features.json").open(encoding="utf-8") as handle:
        features = json.load(handle)
    model = joblib.load(folder / "best_model.pkl")
    baseline = REPORT_BASELINE_PCT
    baseline_path = folder / "baseline.json"
    if baseline_path.is_file():
        try:
            raw = json.loads(baseline_path.read_text(encoding="utf-8"))
            if _finite(raw.get("baseline_accuracy")):
                baseline = round(float(raw["baseline_accuracy"]) * 100.0, 1)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return {"model": model, "features": features, "baseline_pct": baseline, "folder": str(folder)}


def feature_row(closes: list[float], volumes: list[float]) -> dict | None:
    """Dernière ligne de variables. None si une valeur manque."""
    if len(closes) < MIN_POINTS_ML or len(volumes) != len(closes):
        return None
    ind = compute_indicators(closes, volumes)
    returns: list[float | None] = ind["returns"]
    if any(not _finite(returns[i]) for i in (-1, -2, -6)):
        return None
    window = returns[-20:]
    if any(not _finite(v) for v in window):
        return None
    vol20 = _sample_std([float(v) for v in window])
    prev_vol = volumes[-2]
    if not _finite(prev_vol) or prev_vol == 0 or not _finite(volumes[-1]):
        return None
    vol_chg = volumes[-1] / prev_vol - 1.0
    row = {
        "return": returns[-1],
        "ma20": ind["ma20"],
        "ma50": ind["ma50"],
        "vol20": vol20,
        "vol_chg": vol_chg,
        "ret_lag1": returns[-2],
        "ret_lag5": returns[-6],
    }
    if any(not _finite(v) for v in row.values()):
        return None
    return row


def predict_probability(closes: list[float], volumes: list[float]) -> dict:
    """Probabilité de la classe 1 du RandomForest, ou disponible=False."""
    empty = {
        "disponible": False,
        "probabilite_hausse_pct": None,
        "modele": None,
        "baseline_toujours_hausse_pct": REPORT_BASELINE_PCT,
        "precision_modele_pct": REPORT_RF_ACCURACY_PCT,
        "message": "Le modèle local n'a pas pu produire de probabilité.",
    }
    bundle = _load_model()
    if bundle is None:
        empty["message"] = "Le fichier du modèle ou ses dépendances sont indisponibles."
        return empty

    names = bundle["features"]
    row = feature_row(closes, volumes)
    if row is None:
        empty["baseline_toujours_hausse_pct"] = bundle["baseline_pct"]
        empty["message"] = (
            f"Il faut au moins {MIN_POINTS_ML} séances avec des volumes exploitables "
            "pour calculer les variables du modèle."
        )
        return empty

    try:
        ordered = [float(row[name]) for name in names]
        model = bundle["model"]
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            proba = model.predict_proba([ordered])[0]
        classes = list(model.classes_)
        index = classes.index(1) if 1 in classes else len(classes) - 1
        pct = float(proba[index]) * 100.0
        if not _finite(pct):
            raise ValueError("probabilité non numérique")
        pct = max(0.0, min(100.0, pct))
    except Exception as exc:  # modèle incompatible ou variable inattendue
        print(f"ML non appliqué : {type(exc).__name__}")
        empty["baseline_toujours_hausse_pct"] = bundle["baseline_pct"]
        empty["message"] = "Le modèle enregistré n'a pas pu être appliqué à cette série."
        return empty

    return {
        "disponible": True,
        "probabilite_hausse_pct": round(pct, 1),
        "modele": type(model).__name__,
        "baseline_toujours_hausse_pct": bundle["baseline_pct"],
        "precision_modele_pct": REPORT_RF_ACCURACY_PCT,
        "message": (
            "Probabilité estimée par le RandomForest local que la variation suivante soit positive. "
            "Ce n'est pas un rendement attendu."
        ),
    }


def _facts(symbol: str, ind: dict, ml: dict, rules: dict, as_of: str | None) -> dict:
    price = _r(ind.get("prix"), 2)
    ma20 = _r(ind.get("ma20"), 2)
    ma50 = _r(ind.get("ma50"), 2)
    var = _r(ind.get("variation_1j_pct"), 2)
    vol = _r(ind.get("volatilite_annualisee_pct"), 1)
    dd = _r(ind.get("max_drawdown_pct"), 1)
    favorable: list[str] = []
    unfavorable: list[str] = []

    if price is not None and ma20 is not None:
        if price > ma20:
            favorable.append(f"Le cours ({price:.2f} USD) est au-dessus de la MM20 ({ma20:.2f} USD).")
        elif price < ma20:
            unfavorable.append(f"Le cours ({price:.2f} USD) est sous la MM20 ({ma20:.2f} USD).")
    if ma20 is not None and ma50 is not None:
        if ma20 > ma50:
            favorable.append(f"La MM20 ({ma20:.2f} USD) est au-dessus de la MM50 ({ma50:.2f} USD).")
        elif ma20 < ma50:
            unfavorable.append(f"La MM20 ({ma20:.2f} USD) est sous la MM50 ({ma50:.2f} USD).")

    proba = ml.get("probabilite_hausse_pct")
    if ml.get("disponible") and _finite(proba):
        if proba >= ML_UP:
            favorable.append(
                f"Le modèle estime une probabilité de hausse de {proba:.1f} %, au-dessus du seuil de {ML_UP:.0f} %."
            )
        elif proba <= ML_DOWN:
            unfavorable.append(
                f"Le modèle estime une probabilité de hausse de {proba:.1f} %, sous le seuil de {ML_DOWN:.0f} %."
            )

    if _finite(vol) and vol >= VOL_MAX:
        unfavorable.append(
            f"La volatilité annualisée ({vol:.1f} %) dépasse le seuil de prudence de {VOL_MAX:.0f} %."
        )
    if _finite(dd) and abs(dd) >= DD_MAX:
        unfavorable.append(f"Le repli maximal sur la fenêtre observée atteint {dd:.1f} %.")

    if rules["ml_sig"] is not None and rules["tech"] != 0 and rules["ml_sig"] == -rules["tech"]:
        unfavorable.append("Le modèle et la structure des moyennes mobiles ne vont pas dans le même sens.")

    if rules["status"] != "ok":
        titre = f"{symbol} : historique insuffisant"
        synthese = (
            f"Seulement {ind.get('n', 0)} clôtures sont disponibles pour {symbol}. "
            f"Il en faut au moins {MIN_POINTS} pour calculer une MM20 et appliquer une règle."
        )
    else:
        labels = {
            "ACHAT": "orientation haussière sous conditions",
            "VENTE": "orientation baissière sous conditions",
            "CONSERVATION": "pas de direction assez nette",
        }
        titre = f"{symbol} : {labels[rules['decision']]}"
        bits = []
        if price is not None:
            when = f" le {as_of}" if as_of else ""
            bits.append(f"{symbol} clôture à {price:.2f} USD{when}")
        if var is not None:
            bits.append(f"la variation sur la séance précédente est de {var:+.2f} %")
        if ind.get("tendance") == "haussière":
            bits.append("le cours est au-dessus de sa moyenne mobile à 20 séances")
        elif ind.get("tendance") == "baissière":
            bits.append("le cours est sous sa moyenne mobile à 20 séances")
        synthese = (bits[0][:1].upper() + bits[0][1:] + ". " + " ".join(s[0].upper() + s[1:] + "." for s in bits[1:])).strip()

    declenchees = _triggered_rules(ind, ml, rules, vol, dd)
    return {
        "titre": titre,
        "synthese": synthese,
        "elements_favorables": favorable,
        "elements_defavorables": unfavorable,
        "regles_declenchees": declenchees,
    }


def _triggered_rules(ind: dict, ml: dict, rules: dict, vol, dd) -> list[str]:
    lines = []
    if rules["status"] != "ok":
        lines.append(f"Règle d'arrêt : moins de {MIN_POINTS} clôtures, aucune recommandation.")
        return lines
    tech_label = {1: "haussière", -1: "baissière", 0: "mixte ou neutre"}[rules["tech"]]
    lines.append(f"Structure de prix : {tech_label}.")
    if ml.get("disponible") and _finite(ml.get("probabilite_hausse_pct")):
        lines.append(
            f"Modèle ML : {ml['probabilite_hausse_pct']:.1f} % "
            f"(seuils {ML_UP:.0f} % / {ML_DOWN:.0f} %)."
        )
    else:
        lines.append("Modèle ML : probabilité non disponible, les règles de prix s'appliquent seules.")
    if rules["risque_eleve"]:
        lines.append(
            f"Risque au-dessus des seuils (volatilité {VOL_MAX:.0f} % ou repli {DD_MAX:.0f} %) : "
            "la règle impose la conservation."
        )
    else:
        vol_txt = f"{vol:.1f} %" if _finite(vol) else "n/d"
        dd_txt = f"{dd:.1f} %" if _finite(dd) else "n/d"
        lines.append(f"Risque contenu sur les seuils retenus (volatilité {vol_txt}, repli {dd_txt}).")
    decision = rules["decision"]
    if rules["base"] == "moyennes_mobiles":
        lines.append(f"Décision {decision} fondée sur les moyennes mobiles, sans probabilité ML.")
    elif rules["ml_sig"] not in (None, 0) and rules["tech"] not in (0,) and rules["ml_sig"] != rules["tech"]:
        lines.append(f"Décision {decision} : le modèle et les moyennes divergent.")
    elif rules["ml_sig"] == 0:
        lines.append(
            f"Décision {decision} : la probabilité reste entre {ML_DOWN:.0f} % et {ML_UP:.0f} %, "
            "elle ne confirme pas de direction."
        )
    else:
        lines.append(f"Décision {decision} : le modèle et la technique sont alignés, et le risque est accepté par la règle.")
    return lines


def fallback_text(symbol: str, facts: dict, rules: dict, ml: dict) -> str:
    parts = [facts["titre"] + ".", facts["synthese"]]
    if facts["elements_favorables"]:
        parts.append("Éléments favorables : " + " ".join(facts["elements_favorables"]))
    else:
        parts.append("Aucun élément favorable net ne sort des règles configurées.")
    if facts["elements_defavorables"]:
        parts.append("Éléments défavorables : " + " ".join(facts["elements_defavorables"]))
    else:
        parts.append("Aucun élément défavorable net ne sort des règles configurées.")

    if ml.get("disponible") and _finite(ml.get("probabilite_hausse_pct")):
        parts.append(
            f"Le modèle {ml.get('modele') or 'local'} donne une probabilité de hausse de "
            f"{ml['probabilite_hausse_pct']:.1f} %. "
            f"Lors de l'évaluation documentée, sa précision ({REPORT_RF_ACCURACY_PCT:.1f} %) "
            f"ne bat pas la baseline de {ml.get('baseline_toujours_hausse_pct', REPORT_BASELINE_PCT):.1f} %."
        )
    else:
        parts.append(ml.get("message") or "Aucune probabilité de modèle n'est disponible.")

    decision = rules.get("decision")
    note = rules.get("note")
    if decision and note is not None:
        parts.append(
            f"Recommandation issue des règles : {decision}. "
            f"Note de cohérence du signal : {note}/5. {NOTE_DEFINITION}"
        )
    else:
        parts.append("Aucune recommandation n'est émise, faute de données suffisantes.")
    parts.append(LIMITES)
    return " ".join(parts)


def compose_review(
    symbol: str,
    closes: list[float],
    volumes: list[float] | None,
    *,
    as_of: str | None = None,
    origine: str = "inconnue",
    ml_override: dict | None = None,
) -> dict:
    """Paquet complet servi par l'API. ml_override sert aux tests de règles."""
    vols = list(volumes) if volumes is not None else [1.0] * len(closes)
    ind = compute_indicators(closes, vols)
    ml = ml_override if ml_override is not None else predict_probability(closes, vols)
    if ml_override is not None and "disponible" not in ml:
        ml = {**ml, "disponible": _finite(ml.get("probabilite_hausse_pct"))}
    rules = decide(ind, ml.get("probabilite_hausse_pct") if ml.get("disponible") else None)
    facts = _facts(symbol, ind, ml, rules, as_of)
    texte = fallback_text(symbol, facts, rules, ml)

    return {
        "symbol": symbol,
        "status": rules["status"],
        "titre": facts["titre"],
        "synthese": facts["synthese"],
        "elements_favorables": facts["elements_favorables"],
        "elements_defavorables": facts["elements_defavorables"],
        "observe": {
            "prix_actuel": _r(ind.get("prix"), 2),
            "date": as_of,
            "variation_1j_pct": _r(ind.get("variation_1j_pct"), 2),
            "ma20": _r(ind.get("ma20"), 2),
            "ma50": _r(ind.get("ma50"), 2),
            "tendance": ind.get("tendance"),
            "volatilite_annualisee_pct": _r(ind.get("volatilite_annualisee_pct"), 2),
            "max_drawdown_pct": _r(ind.get("max_drawdown_pct"), 2),
            "nb_observations": ind.get("n", 0),
            "origine": origine,
        },
        "ml": {
            "disponible": bool(ml.get("disponible")),
            "probabilite_hausse_pct": ml.get("probabilite_hausse_pct") if ml.get("disponible") else None,
            "modele": ml.get("modele"),
            "baseline_toujours_hausse_pct": ml.get("baseline_toujours_hausse_pct", REPORT_BASELINE_PCT),
            "precision_modele_pct": ml.get("precision_modele_pct", REPORT_RF_ACCURACY_PCT),
            "message": ml.get("message"),
        },
        "recommandation": {
            "decision": rules["decision"],
            "note_sur_5": rules["note"],
            "definition_note": NOTE_DEFINITION if rules["note"] is not None else None,
            "base": rules["base"],
            "regles_declenchees": facts["regles_declenchees"],
        },
        "commentaire": {"source": "fallback", "modele": None, "texte": texte},
        "limites": LIMITES,
        "review": texte,
    }


def asset_summary(
    symbol: str,
    closes: list[float],
    volumes: list[float] | None,
    *,
    as_of: str | None = None,
    origine: str = "inconnue",
) -> dict:
    """Résumé marché, sans texte d'analyste. La probabilité ML est réelle ou nulle."""
    vols = list(volumes) if volumes is not None else [0.0] * len(closes)
    ind = compute_indicators(closes, vols)
    ml = predict_probability(closes, vols)
    return {
        "symbol": symbol,
        "prix_actuel": _r(ind.get("prix"), 2),
        "date": as_of,
        "tendance": ind.get("tendance"),
        "ma20": _r(ind.get("ma20"), 2),
        "ma50": _r(ind.get("ma50"), 2),
        "variation_1j_pct": _r(ind.get("variation_1j_pct"), 2),
        "volatilite_annualisee_pct": _r(ind.get("volatilite_annualisee_pct"), 2),
        "max_drawdown_pct": _r(ind.get("max_drawdown_pct"), 2),
        "nb_observations": ind.get("n", 0),
        "origine": origine,
        "fraicheur": as_of,
        "probabilite_hausse_pct": ml.get("probabilite_hausse_pct") if ml.get("disponible") else None,
        "ml_disponible": bool(ml.get("disponible")),
        "ml_message": ml.get("message"),
        "baseline_toujours_hausse_pct": ml.get("baseline_toujours_hausse_pct", REPORT_BASELINE_PCT),
        "precision_modele_pct": ml.get("precision_modele_pct", REPORT_RF_ACCURACY_PCT),
    }


def history_points(closes: list[float], dates: list, limit: int) -> list[dict]:
    """Les `limit` dernières clôtures, dans l'ordre chronologique, avec MM20 et MM50."""
    ma20 = rolling_mean(closes, 20)
    ma50 = rolling_mean(closes, 50)
    size = max(1, min(int(limit), 500))
    start = max(0, len(closes) - size)
    points = []
    for i in range(start, len(closes)):
        raw_date = dates[i]
        iso = raw_date.isoformat() if hasattr(raw_date, "isoformat") else str(raw_date)
        points.append({
            "date": iso,
            "close": round(float(closes[i]), 4),
            "ma20": _r(ma20[i], 4),
            "ma50": _r(ma50[i], 4),
        })
    return points
