"""Aufgaben-Bank für den Jarvis-Modell-Benchmark.

Vier Kategorien, jede mit einem passenden Modell-Feld (siehe bench/models.py):
  - routing:   winzige, schnelle Klassifikation (objektiv per Exact-Match bewertet)
  - chat:      natürliche deutsche Jarvis-Konversation (blind von Claude bewertet)
  - coding:    Code schreiben/fixen/erklären (blind bewertet)
  - reasoning: Planen, Fakten extrahieren, zusammenfassen, JSON (blind bewertet)

Routing-Aufgaben haben ein `expected`-Label (Exact-Match). Offene Aufgaben haben
eine `rubric`, an der der blinde Judge 1–10 vergibt.
"""

# ── Routing-Builder (objektiv) ────────────────────────────────────────────────

_ROUTE_LABELS = "fitness | nutrition | productivity | health | knowledge | habits | goals | robot | flipper | chat"


def _intent(tid, msg, expected):
    prompt = (
        "Du bist der Routing-Layer eines Assistenten. Ordne die Nutzer-Nachricht GENAU EINER "
        f"Kategorie zu.\nKategorien: {_ROUTE_LABELS}\n"
        "'chat' = reiner Smalltalk/keine der anderen. Antworte NUR mit dem Kategorie-Wort, sonst nichts.\n\n"
        f"Nachricht: \"{msg}\"\nKategorie:"
    )
    return {"id": tid, "category": "routing", "subtype": "intent", "prompt": prompt,
            "expected": expected, "scoring": "exact"}


def _address(tid, msg, expected):
    prompt = (
        "Entscheide, ob diese gesprochene Äußerung an den Assistenten 'Mantis' gerichtet ist und "
        "eine Reaktion braucht. Beiläufiges Gerede/Selbstgespräch = NEIN. Antworte NUR mit JA oder NEIN.\n\n"
        f"Äußerung: \"{msg}\"\nAntwort:"
    )
    return {"id": tid, "category": "routing", "subtype": "address", "prompt": prompt,
            "expected": expected, "scoring": "exact"}


def _gate(tid, msg, expected):
    prompt = (
        "Braucht diese Nachricht eine AKTION (etwas anlegen/ändern/abrufen, Tool nötig) oder ist es "
        "reines GESPRAECH? Antworte NUR mit AKTION oder GESPRAECH.\n\n"
        f"Nachricht: \"{msg}\"\nAntwort:"
    )
    return {"id": tid, "category": "routing", "subtype": "gate", "prompt": prompt,
            "expected": expected, "scoring": "exact"}


def _open(tid, category, prompt, rubric):
    return {"id": tid, "category": category, "prompt": prompt, "rubric": rubric, "scoring": "judge"}


# ── Routing (~16) ─────────────────────────────────────────────────────────────

ROUTING = [
    _intent("r_int1", "Ich hab heute 30 Minuten Oberkörper trainiert", "fitness"),
    _intent("r_int2", "Trag bitte ein dass ich 3 Eier zum Frühstück hatte", "nutrition"),
    _intent("r_int3", "Erinnere mich morgen um 9 an den Zahnarzt", "productivity"),
    _intent("r_int4", "Wie hab ich letzte Nacht geschlafen?", "health"),
    _intent("r_int5", "Was kostet ein Flug nach Tokio gerade so?", "knowledge"),
    _intent("r_int6", "Hab meine Meditation heute abgehakt", "habits"),
    _intent("r_int7", "Mein Ziel ist es bis Dezember 90 Kilo zu wiegen", "goals"),
    _intent("r_int8", "Fahr den Roboter zwei Sekunden vor", "robot"),
    _intent("r_int9", "Mach die Schreibtischlampe an", "flipper"),
    _intent("r_int10", "Erzähl mir einen Witz", "chat"),
    _address("r_adr1", "Mantis, wie spät ist es?", "JA"),
    _address("r_adr2", "boah bin ich müde heute...", "NEIN"),
    _address("r_adr3", "kannst du mir kurz das Wetter sagen", "JA"),
    _address("r_adr4", "ja ne das passt schon so glaub ich", "NEIN"),
    _gate("r_gate1", "Leg eine Aufgabe an: Steuer machen", "AKTION"),
    _gate("r_gate2", "Was denkst du über künstliche Intelligenz?", "GESPRAECH"),
]

# ── Chat / Konversation (~12) ─────────────────────────────────────────────────

_CHAT_RUBRIC = ("Natürliches, fehlerfreies Deutsch; hilfreich und konkret; prägnant (nicht "
                "geschwätzig); freundlicher, kompetenter Assistent-Ton (kein Roboter, keine "
                "Floskel-Wand); erfindet keine spezifischen Fakten. 10 = wie ein exzellenter "
                "persönlicher Assistent, 1 = unbrauchbar/falsche Sprache/erfunden.")

CHAT = [
    _open("c1", "chat", "Guten Morgen! Fass mir in zwei Sätzen zusammen, worauf ich mich heute freuen kann, "
          "wenn ich einen freien Samstag mit gutem Wetter habe.", _CHAT_RUBRIC),
    _open("c2", "chat", "Ich bin gerade echt gestresst wegen meiner Prüfung nächste Woche. Sag was Aufbauendes, "
          "aber ohne Kitsch.", _CHAT_RUBRIC),
    _open("c3", "chat", "Erklär mir in einfachen Worten, warum der Himmel blau ist.", _CHAT_RUBRIC),
    _open("c4", "chat", "Ich kann mich nicht entscheiden zwischen Joggen und Krafttraining heute. Hilf mir "
          "in 2-3 Sätzen zu entscheiden.", _CHAT_RUBRIC),
    _open("c5", "chat", "Was wäre ein guter, einfacher Plan für einen produktiven Vormittag?", _CHAT_RUBRIC),
    _open("c6", "chat", "Erzähl mir einen kurzen, wirklich lustigen Witz auf Deutsch.", _CHAT_RUBRIC),
    _open("c7", "chat", "Ich hab schlecht geschlafen und muss trotzdem funktionieren. Ein konkreter Tipp bitte.",
          _CHAT_RUBRIC),
    _open("c8", "chat", "Motivier mich in einem Satz, mit dem Schreiben meiner Hausarbeit anzufangen.", _CHAT_RUBRIC),
    _open("c9", "chat", "Was ist der Unterschied zwischen 'weniger' und 'geringer'? Kurz und klar.", _CHAT_RUBRIC),
    _open("c10", "chat", "Ich hab Lust auf was Neues zum Kochen, mag aber keine Pilze. Schlag EIN Gericht vor "
          "und begründe kurz.", _CHAT_RUBRIC),
    _open("c11", "chat", "Sag mir ehrlich und freundlich: Ist es okay, heute einfach mal nichts zu tun?", _CHAT_RUBRIC),
    _open("c12", "chat", "Gib mir eine 10-Sekunden-Atemübung als Text, die ich sofort machen kann.", _CHAT_RUBRIC),
]

# ── Coding (~10) ──────────────────────────────────────────────────────────────

_CODE_RUBRIC = ("Korrektheit steht über allem (löst die Aufgabe die Lösung wirklich?); idiomatisch/sauber; "
                "keine offensichtlichen Bugs; knapp erklärt wo nötig. 10 = korrekt und sauber, "
                "1 = falsch/kompiliert nicht/löst die Aufgabe nicht.")

CODING = [
    _open("co1", "coding", "Schreibe eine Python-Funktion `is_palindrome(s: str) -> bool`, die Groß/Klein und "
          "Nicht-Buchstaben ignoriert.", _CODE_RUBRIC),
    _open("co2", "coding", "Dieser Code hat einen Bug, finde und fixe ihn:\n\ndef avg(xs):\n    return sum(xs) / len(xs)\n\n"
          "Er soll bei leerer Liste 0 zurückgeben statt zu crashen.", _CODE_RUBRIC),
    _open("co3", "coding", "Schreibe ein SQL-Statement: die 3 Nutzer mit den meisten Bestellungen der letzten "
          "30 Tage, aus Tabellen users(id,name) und orders(id,user_id,created_at).", _CODE_RUBRIC),
    _open("co4", "coding", "Schreibe eine Python-Funktion, die eine verschachtelte Liste beliebiger Tiefe "
          "flach macht (flatten).", _CODE_RUBRIC),
    _open("co5", "coding", "Erkläre in 2-3 Sätzen, was dieser Code tut:\n\n"
          "result = [x for x in data if x % 2 == 0][:5]", _CODE_RUBRIC),
    _open("co6", "coding", "Schreibe einen Regex, der eine deutsche IBAN grob validiert (DE + 20 Ziffern).",
          _CODE_RUBRIC),
    _open("co7", "coding", "Schreibe eine async Python-Funktion, die 3 URLs parallel mit httpx lädt und die "
          "Statuscodes als Liste zurückgibt.", _CODE_RUBRIC),
    _open("co8", "coding", "Refactor: mach diese Schleife pythonic:\n\nresult = []\nfor i in range(len(items)):\n"
          "    result.append(items[i].upper())", _CODE_RUBRIC),
    _open("co9", "coding", "Schreibe eine Python-Funktion `chunk(lst, n)`, die eine Liste in n-große Stücke "
          "teilt (letztes darf kleiner sein).", _CODE_RUBRIC),
    _open("co10", "coding", "Was ist an diesem Code gefährlich und wie behebt man es?\n\n"
          'cur.execute(\"SELECT * FROM users WHERE name = \'\" + name + \"\'\")', _CODE_RUBRIC),
]

# ── Reasoning / Background (~11) ──────────────────────────────────────────────

_REASON_RUBRIC = ("Korrekt, vollständig und dem Format treu (wenn JSON/Liste verlangt, dann exakt so); "
                  "keine erfundenen Fakten; logisch nachvollziehbar. 10 = präzise und formattreu, "
                  "1 = falsch/erfindet/ignoriert das Format.")

REASONING = [
    _open("re1", "reasoning", "Extrahiere dauerhafte Fakten über die Person als JSON-Array [{\"fakt\":..., "
          "\"kategorie\":...}]. Nur was wirklich gesagt wird:\n\n"
          "'Ich heiße Timo, wohne in Nürnberg und arbeite als Softwareentwickler. Heute ist mir kalt.'",
          _REASON_RUBRIC),
    _open("re2", "reasoning", "Zerlege die Aufgabe 'Geburtstagsfeier für 20 Leute organisieren' in 4-6 "
          "konkrete Unterschritte als nummerierte Liste.", _REASON_RUBRIC),
    _open("re3", "reasoning", "Fasse diesen Text in genau einem Satz zusammen:\n\n"
          "'Das Meeting wurde von Dienstag auf Donnerstag verschoben, weil zwei Teilnehmer krank sind. "
          "Der Raum bleibt derselbe, die Agenda wird gekürzt.'", _REASON_RUBRIC),
    _open("re4", "reasoning", "Ein Zug fährt um 14:20 und die Fahrt dauert 1 Stunde 55 Minuten. Wann kommt er "
          "an? Antworte nur mit der Uhrzeit.", _REASON_RUBRIC),
    _open("re5", "reasoning", "Klassifiziere die Stimmung dieses Satzes als positiv/neutral/negativ und "
          "begründe in einem Halbsatz:\n\n'Naja, war okay, hätte schlimmer sein können.'", _REASON_RUBRIC),
    _open("re6", "reasoning", "Gib die Antwort NUR als JSON {\"kalorien\": int, \"protein_g\": int} für: "
          "'zwei Scheiben Vollkorntoast mit Erdnussbutter'. Schätze realistisch.", _REASON_RUBRIC),
    _open("re7", "reasoning", "Timo hat Mo, Di, Do trainiert und will 4x/Woche. Heute ist Freitag. Soll er "
          "heute trainieren? Antworte mit Ja/Nein und einem kurzen Grund.", _REASON_RUBRIC),
    _open("re8", "reasoning", "Erkenne den Widerspruch: 'Ich esse kein Fleisch' und später 'Gestern gab's "
          "das beste Steak meines Lebens'. Erkläre in einem Satz.", _REASON_RUBRIC),
    _open("re9", "reasoning", "Priorisiere diese 3 Aufgaben nach Dringlichkeit und begründe je einen Halbsatz: "
          "(a) Steuererklärung in 2 Wochen fällig, (b) Freund zurückrufen, (c) Kühlschrank ist leer.",
          _REASON_RUBRIC),
    _open("re10", "reasoning", "Rechne: Ein Rezept für 4 Personen braucht 600g Mehl. Wieviel für 6 Personen? "
          "Antworte nur mit der Zahl in Gramm.", _REASON_RUBRIC),
    _open("re11", "reasoning", "Wandle in einen Kalendereintrag als JSON {\"titel\":..,\"datum\":..,\"uhrzeit\":..}: "
          "'Nächsten Montag um halb 4 Nachmittags Friseur'. Heute ist Freitag, 2026-07-10.", _REASON_RUBRIC),
]

ALL_TASKS = ROUTING + CHAT + CODING + REASONING


def tasks_for_category(cat: str) -> list[dict]:
    return [t for t in ALL_TASKS if t["category"] == cat]
