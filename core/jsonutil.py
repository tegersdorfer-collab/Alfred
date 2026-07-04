"""
Robustes Extrahieren von JSON aus LLM-Ausgaben.
Selbst mit erzwungenem format='json' bleibt das ein Sicherheitsnetz gegen
Markdown-Fences, Vortext oder abgeschnittene Antworten – und gegen Modelle/
Provider, die kein hartes JSON-Format kennen.
"""
import json
import logging
import re

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

    # 3) Klammer-Tiefenzählung statt rfind: rfind(close_c) griff die LETZTE
    # Klammer im gesamten Text – bricht sobald Fließtext NACH dem JSON
    # zufällig ein '}'/']' enthält (z.B. "...am 5} juli"). Stattdessen ab
    # der ersten öffnenden Klammer die tatsächlich zugehörige schließende
    # suchen (string-aware).
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        if start == -1:
            continue
        snippet = _match_bracket(text, start, open_c, close_c)
        if snippet is None:
            continue
        try:
            return json.loads(snippet)
        except json.JSONDecodeError:
            # Häufigster LLM-Fehler: Trailing-Komma vor } oder ]
            try:
                return json.loads(re.sub(r",\s*([}\]])", r"\1", snippet))
            except Exception:
                continue
        except Exception:
            continue

    log.debug("extract_json: kein JSON gefunden in %r", text[:120])
    return default


def _match_bracket(text: str, start: int, open_c: str, close_c: str) -> str | None:
    """Findet die zu `start` (Position von open_c) gehörige schließende Klammer,
    unter Berücksichtigung von String-Literalen. Gibt das Segment inkl. beider
    Klammern zurück, oder None wenn keine passende schließende Klammer existiert."""
    depth = 0
    in_str, escape = False, False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
        elif ch == "\\" and in_str:
            escape = True
        elif ch == '"':
            in_str = not in_str
        elif not in_str:
            if ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None
