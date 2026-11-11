"""Recherche locale dans les fiches. Pas de base vectorielle : TF-IDF déjà fourni par scikit-learn."""
from __future__ import annotations

import os
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

THRESHOLD = 0.12
_CACHE: dict = {"stamp": None, "docs": [], "matrix": None, "vectorizer": None}
_QUIZ = re.compile(r"Question: (.+)\n- A\. (.+)\n- B\. (.+)\nRéponse: ([AB])", re.DOTALL)


def knowledge_dir() -> Path:
    env = os.getenv("KNOWLEDGE_DIR", "").strip()
    if env:
        return Path(env)
    mounted = Path("/knowledge")
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2] / "knowledge"


def _docs() -> list[dict]:
    folder = knowledge_dir()
    files = sorted(folder.glob("*.md"))
    stamp = tuple((path.name, path.stat().st_mtime) for path in files)
    if _CACHE["stamp"] == stamp and _CACHE["docs"]:
        return _CACHE["docs"]
    docs = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        title = path.stem
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
        quiz = None
        found = _QUIZ.search(text)
        if found:
            quiz = {"question": found.group(1).strip(), "a": found.group(2).strip(), "b": found.group(3).strip(), "answer": found.group(4)}
        docs.append({"slug": path.stem, "title": title, "text": text, "quiz": quiz})
    vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform([doc["text"] for doc in docs]) if docs else None
    _CACHE.update(stamp=stamp, docs=docs, matrix=matrix, vectorizer=vectorizer)
    return docs


def search_fiches(query: str, limit: int = 3) -> list[dict]:
    """Les meilleures fiches, avec un score cosinus. Liste vide si le dossier est vide."""
    docs = _docs()
    if not docs or _CACHE["matrix"] is None:
        return []
    vector = _CACHE["vectorizer"].transform([query])
    scores = cosine_similarity(vector, _CACHE["matrix"]).ravel()
    order = scores.argsort()[::-1][:limit]
    hits = []
    for index in order:
        doc = docs[int(index)]
        hits.append({
            "slug": doc["slug"],
            "title": doc["title"],
            "score": float(scores[index]),
            "text": doc["text"],
            "quiz": doc["quiz"],
        })
    return hits


def list_fiches() -> list[dict]:
    return [{"slug": doc["slug"], "title": doc["title"], "quiz": doc["quiz"] is not None} for doc in _docs()]


def get_fiche(slug: str) -> dict | None:
    for doc in _docs():
        if doc["slug"] == slug:
            return doc
    return None


def excerpt(text: str) -> str:
    """Débutant + définition, sans le quiz, pour une réponse déterministe."""
    body = text.split("## Quiz", 1)[0]
    body = body.replace("<!-- à relire -->", "").strip()
    lines = [line.strip() for line in body.splitlines() if line.strip() and not line.startswith("#")]
    kept = []
    for line in lines:
        if line.startswith("##"):
            continue
        kept.append(line)
        if len(" ".join(kept)) > 420:
            break
    return " ".join(kept)[:500]
