"""Reformulation Ollama. Les chiffres et la recommandation viennent de analysis.py."""
from __future__ import annotations

import os
import re

import httpx

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "120"))

REFUSAL_PHRASES = (
    "i can't",
    "i cannot",
    "i can not",
    "i'm sorry",
    "i am sorry",
    "je ne peux pas",
    "en tant qu'ia",
    "en tant qu'intelligence artificielle",
    "as an ai",
    "as a language model",
    "je dois refuser",
    "i must refuse",
    "cannot provide financial",
    "can't provide financial",
    "ne peux pas fournir",
)

_PCT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*%")


def ollama_base() -> str:
    raw = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
    if "/v1/" in raw:
        raw = raw.split("/v1/", 1)[0]
    return raw.rstrip("/")


def ollama_generate_url() -> str:
    return ollama_base() + "/api/generate"


def _percents(text: str) -> list[float]:
    values = []
    for match in _PCT_RE.findall(text or ""):
        try:
            values.append(float(match.replace(",", ".")))
        except ValueError:
            continue
    return values


def validate_llm_text(answer: str, *, symbol: str, decision: str | None, source_text: str) -> bool:
    """Accepte une reformulation qui garde le symbole, la décision et les pourcentages connus."""
    if not isinstance(answer, str):
        return False
    text = answer.strip().strip('"').strip()
    if not (60 <= len(text) <= 2000):
        return False
    if not text.endswith((".", "!", "?", "…", "»")):
        return False
    lowered = text.lower()
    if any(phrase in lowered for phrase in REFUSAL_PHRASES):
        return False
    if symbol.upper() not in text.upper():
        return False
    if decision and re.search(rf"\b{re.escape(decision)}\b", text) is None:
        return False
    allowed = _percents(source_text)
    for value in _percents(text):
        if not any(abs(value - known) <= 1.0 for known in allowed):
            return False
    return True


def build_prompt(package: dict) -> str:
    decision = package.get("recommandation", {}).get("decision") or "aucune"
    draft = package.get("commentaire", {}).get("texte") or ""
    symbol = package.get("symbol", "")
    level = package.get("niveau") or "intermediaire"
    tone = {
        "debutant": "Vocabulaire de débutant : dis « moyenne des 20 derniers cours » pour la MM20.",
        "expert": "Vocabulaire technique concis.",
    }.get(level, "Vocabulaire standard.")
    return (
        "Reformule le texte entre guillemets triples en français professionnel, en 5 à 7 phrases.\n"
        f"{tone}\n"
        "Contraintes :\n"
        f"- Conserve le symbole {symbol} et la recommandation {decision}.\n"
        "- Conserve les chiffres déjà écrits. N'en ajoute aucun.\n"
        "- « Direction » désigne le cours, jamais la direction de l'entreprise.\n"
        "- N'ajoute aucun événement, aucune actualité, aucune entreprise.\n"
        "- Ne refuse pas la reformulation et ne t'excuse pas.\n"
        "- 5 à 7 phrases, et termine par un point.\n"
        "- Réponds uniquement avec le texte reformulé.\n\n"
        f'"""\n{draft}\n"""'
    )


async def ask_ollama(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(OLLAMA_TIMEOUT, connect=5.0)) as client:
        response = await client.post(
            ollama_generate_url(),
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "10m",
                "options": {"temperature": 0.1, "num_predict": 420},
            },
        )
        response.raise_for_status()
        content = response.json().get("response")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("réponse Ollama vide")
        text = content.strip()
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        return text


async def comment(package: dict) -> dict:
    """Texte Ollama si la réponse est valide, sinon le texte Python déjà calculé."""
    fallback = package.get("commentaire") or {
        "source": "fallback",
        "modele": None,
        "texte": package.get("review") or "",
    }
    if package.get("status") != "ok":
        return fallback
    try:
        raw = await ask_ollama(build_prompt(package))
    except Exception as exc:
        print(f"Ollama indisponible : {type(exc).__name__}")
        return fallback

    decision = (package.get("recommandation") or {}).get("decision")
    source = fallback.get("texte") or ""
    if not validate_llm_text(raw, symbol=package.get("symbol", ""), decision=decision, source_text=source):
        print("Réponse Ollama rejetée, texte Python conservé.")
        return fallback
    return {"source": "ollama", "modele": OLLAMA_MODEL, "texte": raw}
