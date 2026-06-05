"""
Router – entscheidet welche Tools für eine Anfrage gebraucht werden.
Schnell, kein LLM-Call nötig: keyword-basiert + einfache Heuristiken.
"""
import re

# Suchanfragen: aktuelle Infos, Fakten, News, Preise etc.
SEARCH_PATTERNS = [
    r"\bwetter\b",
    r"\bnews\b",
    r"\baktuell\b",
    r"\bheute\b",
    r"\bmorgen\b",
    r"\bwas ist\b",
    r"\bwer ist\b",
    r"\bwie viel\b",
    r"\bwieviel\b",
    r"\bwann\b.*\b(findet|ist|war|kommt)\b",
    r"\bpreis\b",
    r"\bkostet\b",
    r"\bkurs\b",
    r"\bbörse\b",
    r"\bsuch\b",
    r"\brecherchier\b",
    r"\bfind(e)?\b.*\binfo\b",
    r"\b202[0-9]\b",   # Jahreszahlen → wahrscheinlich aktuell
    r"\bneueste\b",
    r"\blatest\b",
]

# Komplexe Analysen → Claude Code
COMPLEX_PATTERNS = [
    r"\banalysier\b",
    r"\bvergleich\b",
    r"\bstrategie\b",
    r"\bplan\b.*\berstell\b",
    r"\bzusammenfass\b",
    r"\büberleg\b",
    r"\bbewert\b",
    r"\bcode\b.*\bschreib\b",
    r"\bprogrammier\b",
]


NEWS_PATTERNS = [
    r"\bnews\b",
    r"\bnachrichten\b",
    r"\bschlagzeilen\b",
    r"\bheute\b.*(passiert|geschehen|los)",
    r"\bwas.*(welt|deutschland|politik|wirtschaft)",
    r"\baktuell(e|es|er)?\b.*(ereignis|meldung|bericht)",
]


def needs_search(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in SEARCH_PATTERNS)


def needs_news(text: str) -> bool:
    """Spezifisch für aktuelle Nachrichten → Google News RSS."""
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in NEWS_PATTERNS)


def needs_claude(text: str) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in COMPLEX_PATTERNS)
