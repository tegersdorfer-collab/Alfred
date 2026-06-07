"""
Robustes Extrahieren von JSON aus LLM-Ausgaben.
Selbst mit erzwungenem format='json' bleibt das ein Sicherheitsnetz gegen
Markdown-Fences, Vortext oder abgeschnittene Antworten – und gegen Modelle/
Provider, die kein hartes JSON-Format kennen.
"""
import json
import logging

log = logging.getLogger(__name__)


def extract_json(raw: str, default=None):
    """Parst ein JSON-Objekt/-Array aus einer LLM-Antwort.

    Reihenfolge: direktes Parsen → Code-Fence entfernen → äußerste Klammern
    {..} bzw. [..] greifen. Gibt `default` zurück, wenn nichts parsebar ist.
    """
    if not raw or not isinstance(raw, str):
        return default
    text = raw.strip()

    # 1) Direkt versuchen (Normalfall mit format='json')
    try:
        return json.loads(text)
    except Exception:
        pass

    # 2) Markdown-Code-Fence entfernen (```json ... ``` oder ``` ... ```)
    if "```" in text:
        try:
            seg = text.split("```", 2)[1]
            if seg.lstrip().lower().startswith("json"):
                seg = seg.lstrip()[4:]
            seg = seg.split("```")[0].strip()
            return json.loads(seg)
        except Exception:
            pass

    # 3) Äußerste Klammern greifen – Objekt oder Array, je nachdem was zuerst auftaucht
    candidates = []
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end > start:
            candidates.append((start, text[start:end + 1]))
    # das zuerst beginnende Konstrukt bevorzugen
    for _, snippet in sorted(candidates):
        try:
            return json.loads(snippet)
        except Exception:
            continue

    log.debug("extract_json: kein JSON gefunden in %r", text[:120])
    return default
