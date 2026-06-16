"""Gemeinsame Duplikat-Erkennung für Task-Vorschläge (insight_engine, task_executor)."""

STOPWORDS = {
    "python", "skript", "einer", "einen", "eines", "basierend", "durch",
    "sowie", "oder", "dass", "nicht", "werden", "können", "diese", "dieses",
    "beim", "nach", "über", "unter", "vor", "analyse", "erstellung",
    "generierung", "berechnung", "validierung", "erstellen", "berechnen",
    "validieren", "identifikation", "isolierung",
}


def _keywords(title: str) -> set[str]:
    return {w for w in title.lower().split() if len(w) > 5 and w not in STOPWORDS}


def is_duplicate_title(title: str, recent_titles: list[str], threshold: float = 0.30) -> bool:
    """True wenn `title` thematisch zu stark mit einem der `recent_titles` überlappt
    (Jaccard auf Inhaltswörtern, Stopwörter/kurze Wörter ausgefiltert)."""
    new_kw = _keywords(title)
    if not new_kw:
        return False
    for existing in recent_titles:
        existing_kw = _keywords(existing)
        if not existing_kw:
            continue
        overlap = len(new_kw & existing_kw) / max(1, len(new_kw | existing_kw))
        if overlap >= threshold:
            return True
    return False
