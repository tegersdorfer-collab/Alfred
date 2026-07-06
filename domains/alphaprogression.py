"""
Alpha Progression share-link Parser.
Fetcht eine alphaprogression.com/de/{code} URL und extrahiert Workout-Daten.
"""
import logging
import re
from datetime import date

import httpx

from domains import fitness

log = logging.getLogger(__name__)

AP_RE = re.compile(r'https?://alphaprogression\.com/(?:[a-z]{2}/)?([A-Za-z0-9]+)')


def extract_link(text: str) -> str | None:
    """Gibt erste Alpha-Progression-URL aus dem Text zurück, oder None."""
    m = AP_RE.search(text)
    return m.group(0) if m else None


def parse_page(html: str) -> dict | None:
    """
    Parst das server-side-rendered HTML einer AP-Share-Seite.
    Gibt zurück: {title, exercises: [{name, equipment, sets, reps}]}
    """
    # Titel
    title_m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
    if not title_m:
        title_m = re.search(r'class="[^"]*workout-title[^"]*"[^>]*>(.*?)<', html, re.S)
    title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else 'Workout'

    # Übungen aus dem Klartext: je zwei Zeilen
    # "Name · Equipment\nX Satz · Y Wdh"
    text = re.sub(r'<[^>]+>', '\n', html)
    text = text.replace('&shy;', '').replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = re.sub(r'\n{2,}', '\n', text)
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    exercises = []
    i = 0
    while i < len(lines):
        # Zeile mit Equipment-Pattern: "Name · Gerät"
        if ' · ' in lines[i] and i + 1 < len(lines):
            next_line = lines[i + 1]
            # Nächste Zeile: "X Satz/Sätze · Y Wdh"
            sets_m = re.search(r'(\d+)\s*S[äa]tze?\w*\s*[·•]\s*(\d+)\s*Wdh', next_line, re.I)
            if sets_m:
                parts = lines[i].split(' · ', 1)
                name = parts[0].strip()
                equipment = parts[1].strip() if len(parts) > 1 else ''
                n_sets = int(sets_m.group(1))
                n_reps = int(sets_m.group(2))
                exercises.append({
                    'name': name,
                    'equipment': equipment,
                    'sets': n_sets,
                    'reps': n_reps,
                })
                i += 2
                continue
        i += 1

    if not exercises:
        return None
    return {'title': title, 'exercises': exercises}


def fetch_and_log(url: str, on_date: date | None = None) -> str:
    """
    Fetcht die URL, parst das Workout und loggt es in die DB.
    Gibt eine human-readable Zusammenfassung zurück.
    """
    # Immer deutsche Seite fetchen (Regex erwartet deutsche Bezeichnungen)
    m = AP_RE.search(url)
    if m:
        code = m.group(1)
        url = f'https://alphaprogression.com/de/{code}'
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={'User-Agent': 'Mozilla/5.0 (compatible; Mantis/1.0)'})
        r.raise_for_status()
    except Exception as e:
        log.error(f"AP fetch error: {e}")
        return f"❌ Konnte Alpha Progression Link nicht laden: {e}"

    data = parse_page(r.text)
    if not data:
        return "❌ Konnte keine Übungsdaten aus dem Link lesen."

    title = data['title']
    exercises = data['exercises']

    # Sets für DB bauen: jede Wiederholung als eigener Set-Eintrag
    sets_db = []
    for ex in exercises:
        for s in range(ex['sets']):
            sets_db.append({
                'exercise': ex['name'],
                'reps': ex['reps'],
                'weight_kg': None,  # AP-Plan hat keine Gewichte
                'set_index': len(sets_db) + 1,
            })

    wid = fitness.log_workout(
        title=title,
        type_='strength',
        notes=f"Import via Alpha Progression · {url}",
        on_date=on_date,
        sets=sets_db,
    )

    # Antwort bauen
    lines = [f"✅ **{title}** eingetragen (ID #{wid})"]
    total_sets = sum(e['sets'] for e in exercises)
    lines.append(f"{len(exercises)} Übungen · {total_sets} Sätze")
    lines.append("")
    for ex in exercises:
        lines.append(f"• {ex['name']} ({ex['equipment']}) – {ex['sets']}×{ex['reps']}")
    lines.append("")
    lines.append("_Gewichte wurden nicht mitgeteilt – kannst du nachträglich per Chat ergänzen._")
    return '\n'.join(lines)
