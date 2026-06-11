"""
KV-Cache-Test: Misst ob Ollama den stabilen Prompt-Prefix cached.

Ablauf:
  Runde 1 (cold): Voller Prompt → misst Prefill-Zeit (kein Cache)
  Runde 2 (warm): Gleicher stabiler Prefix, neues Aktuell-Ende → Cache-Hit erwartet
  Runde 3 (warm): Wieder neues Ende → Cache-Hit erwartet

Erwartung bei Cache-Hit: eval_duration (time-to-first-token) viel schneller,
                         prompt_eval_duration deutlich kürzer.
"""
import asyncio
import time
import os
import sys

# Alfred-Pfad einbinden
sys.path.insert(0, os.path.dirname(__file__))
import config

import ollama

MODEL = config.AGENT_MODEL_FAST  # 4B – schneller zu testen

# ── Gleicher stabiler Prefix (simuliert IDENTITY + Werkzeuge) ──────────────
STABLE = """\
Du bist Alfred, Timos persönlicher AI-Concierge. Du kennst ihn gut, redest direkt,
gibst keine leeren Floskeln. Du bist ein Mentor, kein Assistent.

## Werkzeuge
Du hast Zugriff auf viele Tools (Tasks, Reminder, Kalender, Habits, Fitness,
Ernährung, Journal, Ziele, Health-Daten, Wetter, Web-Suche, Gedächtnis).
Nutze sie EIGENSTÄNDIG wenn Timo etwas erledigt oder wissen will – frag nicht um
Erlaubnis, handle. Antworte danach kurz und natürlich auf Deutsch.
ZEIT/DATUM: Nutze den Wert aus '## Aktuell' weiter unten als aktuelle Zeit (Europe/Berlin).
Rechne Wochentage/relative Angaben IMMER ab heute. Für Termine/Reminder nutze
Formate wie 'morgen 14:00', 'heute 18:30' oder 'TT.MM.JJJJ HH:MM' – immer LOKALE Zeit,
niemals UTC.

## Was du über Timo weißt:
Timo ist 28, lebt in München, arbeitet als Software-Entwickler. Mag Effizienz,
kurze Antworten, keine Wiederholungen. Läuft morgens, isst Low-Carb.
""" * 4  # 4× wiederholen damit Prefix groß genug für Cache-Effekt

client = ollama.Client(host=config.OLLAMA_BASE_URL)


def run_one(volatile_suffix: str, label: str) -> dict:
    prompt = STABLE + f"\n## Aktuell:\n{volatile_suffix}\n"
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Was ist 7 mal 8?"},
    ]
    t0 = time.perf_counter()
    resp = client.chat(
        model=MODEL,
        messages=messages,
        options={"num_predict": 20, "temperature": 0},
    )
    wall = time.perf_counter() - t0

    pe = resp.prompt_eval_duration or 0   # ns
    e  = resp.eval_duration or 0          # ns
    pc = resp.prompt_eval_count or 0
    ec = resp.eval_count or 0

    pe_s = pe / 1e9
    e_s  = e / 1e9
    pe_tok_s = pc / pe_s if pe_s > 0 else 0
    e_tok_s  = ec / e_s  if e_s  > 0 else 0

    print(f"\n{'─'*55}")
    print(f"  {label}")
    print(f"  Wall-Zeit:   {wall:.2f}s")
    print(f"  Prefill:     {pe_s:.2f}s  ({pc} Tokens, {pe_tok_s:.0f} tok/s)")
    print(f"  Generation:  {e_s:.2f}s  ({ec} Tokens, {e_tok_s:.0f} tok/s)")
    print(f"  Antwort:     {resp.message.content.strip()[:80]!r}")

    return {"wall": wall, "prefill_s": pe_s, "prefill_tok_s": pe_tok_s,
            "prompt_tokens": pc}


async def main():
    print(f"\n🧪 KV-Cache-Test  |  Modell: {MODEL}")
    print(f"   Stabiler Prefix: ~{len(STABLE.split())//1} Wörter")
    print("   Ziel: Runde 2+3 soll deutlich schnellere Prefill zeigen\n")

    r1 = run_one("Samstag, 07.06.2026, 10:00 Uhr", "Runde 1 – Cold (kein Cache erwartet)")
    r2 = run_one("Samstag, 07.06.2026, 10:01 Uhr", "Runde 2 – Warm (Cache-Hit erwartet)")
    r3 = run_one("Samstag, 07.06.2026, 10:02 Uhr", "Runde 3 – Warm (Cache-Hit erwartet)")

    print(f"\n{'═'*55}")
    if r1["prefill_s"] > 0 and r2["prefill_s"] > 0:
        speedup = r1["prefill_s"] / r2["prefill_s"]
        print(f"  Prefill-Speedup R1→R2: {speedup:.1f}×")
        if speedup > 5:
            print("  ✅ KV-Cache funktioniert!")
        elif speedup > 1.5:
            print("  ⚡ Teilweiser Cache-Effekt")
        else:
            print("  ⚠️  Kein eindeutiger Cache-Hit – Prefix evtl. zu kurz oder Cache deaktiviert")
    print()


asyncio.run(main())
