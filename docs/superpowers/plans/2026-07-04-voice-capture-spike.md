# Sprach-Erfassung — Isolierter Messversuch (Phase 5a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den riskantesten Teil des gesamten Jarvis-Plans (Always-on-Sprachsteuerung ohne
Wake-Word) isoliert bauen und messbar machen, BEVOR er an den Agent-Loop angebunden wird —
Mikrofon-Erfassung im Tauri-Client, einfache Sprach-Segmentierung, Transkription, schneller
Ja/Nein-Adress-Check, Ergebnis sichtbar im HUD.

**Architecture:** Die Tauri-WebView ist eine echte Browser-Engine — Mikrofon-Zugriff läuft über
Standard-Web-APIs (`getUserMedia`/`MediaRecorder`/`AudioContext`), kein natives Rust-Audio-Modul
nötig. Eine einfache energiebasierte Sprach-Erkennung (Lautstärke-Schwellwert, kein ML-Modell)
segmentiert Sprache; jedes Segment geht als Audio-Upload an einen neuen Backend-Endpunkt, der die
BESTEHENDE Whisper-Transkriptionslogik wiederverwendet (aus `communication/telegram.py` in ein
gemeinsames Modul extrahiert, damit sie nicht dupliziert wird) plus einen schnellen
Ja/Nein-Adress-Check über das bereits vorhandene `core/fast.py::yes_no`. Diese Phase bindet NICHTS
an den eigentlichen Agent-Loop an — reiner Mess-/Beobachtungsaufbau.

**Tech Stack:** Python/FastAPI (Backend), TypeScript + Web Audio API (Frontend, apps/desktop),
openai-whisper (bereits installiert, Modell "base").

## Global Constraints

- KEINE Anbindung an `core/message_handler.py` oder den Agent-Loop in dieser Phase — reine
  Mess-/Beobachtungs-Infrastruktur (Transkript + Adress-Entscheidung landen im HUD, sonst nichts).
- Die bestehende Whisper-Transkriptionslogik aus `communication/telegram.py` wird NICHT
  dupliziert, sondern in ein gemeinsames Modul extrahiert und von beiden Stellen genutzt.
- Echte End-to-End-Tests mit einer menschlichen Stimme sind NICHT Teil der automatisierten
  Verifikation dieses Plans — kein Subagent kann eine echte Stimme erzeugen. Automatisiert wird
  geprüft: Code kompiliert/lädt fehlerfrei, der Backend-Endpunkt funktioniert mit einer
  synthetischen Test-Audiodatei (Stille reicht), das Frontend fragt Mikrofon-Zugriff an ohne zu
  crashen. Das eigentliche "erkennt es meine Stimme richtig"-Verifizieren ist für Timo selbst
  vorgesehen und wird im Bericht klar als offen markiert, nicht als erledigt behauptet.
- Optik folgt weiterhin dem Holographic-HUD-Stil: Cyan `#00e5ff` auf `#04070d`.

---

### Task 1: `core/voice.py` — Whisper-Transkription extrahieren + Adress-Check

**Files:**
- Create: `core/voice.py`
- Modify: `communication/telegram.py:26-51` (eigene `_transcribe`-Funktion entfernen, `core.voice`
  importieren und nutzen)
- Test: `tests/test_voice.py`

**Interfaces:**
- Produces:
  - `async def transcribe_audio(audio_path: str) -> str` (identisches Verhalten zur bisherigen
    `communication/telegram.py::_transcribe` — lazy-loaded Whisper-Modell "base", gibt leeren
    String bei Fehler/fehlendem Paket zurück)
  - `async def is_addressed_to_alfred(text: str) -> bool` (nutzt `core.fast.yes_no`)

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_voice.py`:

```python
"""Unit-Tests für core/voice.py: Whisper-Transkription + Adress-Check."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

import core.voice as voice


class TestTranscribeAudio:
    def setup_method(self):
        voice._whisper_model = None  # sauberer Start pro Test

    def test_gibt_transkribierten_text_zurueck(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {"text": "  Wie war mein Schlaf?  "}
        with patch("whisper.load_model", return_value=fake_model):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == "Wie war mein Schlaf?"

    def test_laedt_modell_nur_einmal(self):
        fake_model = MagicMock()
        fake_model.transcribe.return_value = {"text": "test"}
        with patch("whisper.load_model", return_value=fake_model) as mock_load:
            asyncio.run(voice.transcribe_audio("/tmp/a.wav"))
            asyncio.run(voice.transcribe_audio("/tmp/b.wav"))
        mock_load.assert_called_once()

    def test_transkriptions_fehler_gibt_leeren_string(self):
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = RuntimeError("kaputt")
        with patch("whisper.load_model", return_value=fake_model):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == ""

    def test_fehlendes_whisper_paket_gibt_leeren_string(self):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "whisper":
                raise ImportError("nicht installiert")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            text = asyncio.run(voice.transcribe_audio("/tmp/fake.wav"))
        assert text == ""


class TestIsAddressedToAlfred:
    def test_ja_antwort_liefert_true(self):
        with patch("core.fast.yes_no", new=AsyncMock(return_value=True)):
            result = asyncio.run(voice.is_addressed_to_alfred("Ruf mir die Nacht-Zusammenfassung auf"))
        assert result is True

    def test_nein_antwort_liefert_false(self):
        with patch("core.fast.yes_no", new=AsyncMock(return_value=False)):
            result = asyncio.run(voice.is_addressed_to_alfred("Ich rede gerade mit jemand anderem"))
        assert result is False

    def test_leerer_text_liefert_false_ohne_llm_call(self):
        with patch("core.fast.yes_no", new=AsyncMock()) as mock_yes_no:
            result = asyncio.run(voice.is_addressed_to_alfred(""))
        assert result is False
        mock_yes_no.assert_not_called()
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_voice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.voice'`

- [ ] **Step 3: `core/voice.py` schreiben**

```python
"""
Sprach-Verarbeitung — gemeinsame Whisper-Transkription + schneller Adress-Check.

Whisper-Teil ist identisch zu dem, was communication/telegram.py bisher exklusiv
für Telegram-Sprachnachrichten nutzte — jetzt hier zentralisiert, damit Phase 5
(Desktop-Sprachsteuerung) dieselbe Logik wiederverwendet statt sie zu duplizieren.
"""
import asyncio
import logging

from core import fast

log = logging.getLogger(__name__)

_whisper_model = None
_whisper_lock = asyncio.Lock()


async def transcribe_audio(audio_path: str) -> str:
    """Transkribiert eine Audiodatei lokal mit Whisper. Gibt leeren String bei Fehler zurück."""
    global _whisper_model
    try:
        import whisper
    except ImportError:
        log.warning("openai-whisper nicht installiert – Audio kann nicht transkribiert werden")
        return ""

    async with _whisper_lock:
        if _whisper_model is None:
            log.info("🔊 Lade Whisper-Modell 'base' …")
            _whisper_model = await asyncio.to_thread(whisper.load_model, "base")

    try:
        result = await asyncio.to_thread(_whisper_model.transcribe, audio_path, language="de")
        return (result.get("text") or "").strip()
    except Exception as e:
        log.error(f"Whisper-Transkription fehlgeschlagen: {e}")
        return ""


async def is_addressed_to_alfred(text: str) -> bool:
    """Schneller Ja/Nein-Check: ist dieser transkribierte Text ein an Alfred
    gerichteter Befehl/Anfrage? Leerer Text spart den LLM-Call."""
    if not text.strip():
        return False
    return await fast.yes_no(
        f"Ist dieser Satz eine Anfrage oder ein Befehl an einen persönlichen KI-Assistenten "
        f"namens Alfred (nicht nur Small Talk mit jemand anderem im Raum)?\n\n\"{text}\""
    )
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_voice.py -v`
Expected: PASS (7 Tests)

- [ ] **Step 5: `communication/telegram.py` auf `core.voice` umstellen**

In `communication/telegram.py`, den Block von Zeile 26 (`# ── Whisper (lazy-loaded, optional) ──`)
bis zum Ende der `_transcribe`-Funktion (vor `# ── Ollama-Vision (für Fotos) ──`) komplett
entfernen, und stattdessen am Kopf der Datei (bei den anderen Imports) ergänzen:

```python
from core.voice import transcribe_audio as _transcribe
```

Alle bestehenden Aufrufe von `_transcribe(...)` im Rest der Datei bleiben unverändert (der Alias
`_transcribe` sorgt dafür, dass kein weiterer Callsite geändert werden muss) — durchsuche die
Datei nach `_transcribe(` um alle Aufrufstellen zu bestätigen, aber ändere dort nichts.

- [ ] **Step 6: Volle Suite ausführen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS, keine Regressionen (Telegram-Verhalten bleibt identisch, nur die
Implementierung ist jetzt ausgelagert)

- [ ] **Step 7: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add core/voice.py communication/telegram.py tests/test_voice.py
git commit -m "feat(voice): Whisper-Transkription + Adress-Check zentralisieren (core/voice.py)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Backend-Endpunkt `/api/voice/segment`

**Files:**
- Create: `web/routers/voice.py`
- Modify: `web/routers/__init__.py`
- Test: `tests/test_voice_router.py`

**Interfaces:**
- Consumes: `transcribe_audio(audio_path)`, `is_addressed_to_alfred(text)` aus `core.voice` (Task 1)
- Produces: `POST /api/voice/segment` (multipart Audio-Upload) → JSON
  `{"text": str, "addressed": bool}`

- [ ] **Step 1: Fehlschlagenden Test schreiben**

Datei `tests/test_voice_router.py`:

```python
"""Testet POST /api/voice/segment über einen echten FastAPI-TestClient.
Whisper/Fast-LLM werden gemockt — dieser Test prüft nur die Endpunkt-Verkabelung,
nicht die tatsächliche Spracherkennungs-Qualität (dafür gibt es keinen
automatisierten Test, siehe Plan-Constraints)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import wave
from unittest.mock import patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from web.routers.voice import build_router


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(build_router())
    return TestClient(app)


def _fake_wav_bytes() -> bytes:
    """Erzeugt eine winzige, gültige (stille) WAV-Datei — reicht für den
    Upload-Pfad-Test, ohne echtes Audio-Material zu brauchen."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\x00\x00" * 1600)  # 0.1s Stille
    return buf.getvalue()


class TestVoiceSegmentEndpoint:
    def test_liefert_transkript_und_adress_entscheidung(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="Wie war mein Schlaf?")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock(return_value=True)):
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json() == {"text": "Wie war mein Schlaf?", "addressed": True}

    def test_nicht_adressiert_liefert_false(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="Und dann meinte er zu mir...")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock(return_value=False)):
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json()["addressed"] is False

    def test_leeres_transkript_ueberspringt_adress_check(self):
        with patch("web.routers.voice.transcribe_audio", new=AsyncMock(return_value="")), \
             patch("web.routers.voice.is_addressed_to_alfred", new=AsyncMock()) as mock_addr:
            client = _make_client()
            resp = client.post(
                "/api/voice/segment",
                files={"audio": ("segment.wav", _fake_wav_bytes(), "audio/wav")},
            )
        assert resp.status_code == 200
        assert resp.json() == {"text": "", "addressed": False}
        mock_addr.assert_not_called()
```

- [ ] **Step 2: Test ausführen, Fehlschlag verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_voice_router.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'web.routers.voice'`

- [ ] **Step 3: `web/routers/voice.py` schreiben**

```python
"""
Voice — API-Router für den Sprach-Erfassungs-Messaufbau (Phase 5a).
Nimmt vom Tauri-Client hochgeladene Audio-Segmente entgegen, transkribiert sie
lokal und prüft ob sie an Alfred gerichtet sind. KEINE Agent-Anbindung —
reine Mess-/Beobachtungs-Infrastruktur, siehe Plan-Constraints.
"""
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File

from core.voice import transcribe_audio, is_addressed_to_alfred

log = logging.getLogger("alfred.api")


def build_router(orch=None) -> APIRouter:
    router = APIRouter()

    @router.post("/api/voice/segment")
    async def voice_segment(audio: UploadFile = File(...)):
        suffix = Path(audio.filename or "segment.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(await audio.read())
            tmp.flush()
            text = await transcribe_audio(tmp.name)

        addressed = await is_addressed_to_alfred(text) if text else False
        return {"text": text, "addressed": addressed}

    return router
```

In `web/routers/__init__.py` ergänzen (Import-Zeile + `ROUTER_MODULES`-Liste, alphabetisch
zwischen `tasks` und `ui_state` einsortiert):

```python
from . import brain, calendar, chat, fitness, goals, habits, health, insights, journal, knowledge, meta, nutrition, system, tasks, ui_state, voice

ROUTER_MODULES = [
    brain,
    calendar,
    chat,
    fitness,
    goals,
    habits,
    health,
    insights,
    journal,
    knowledge,
    meta,
    nutrition,
    system,
    tasks,
    ui_state,
    voice,
]
```

- [ ] **Step 4: Test ausführen, Erfolg verifizieren**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/test_voice_router.py -v`
Expected: PASS (3 Tests)

Zusätzlich `pip show python-multipart` prüfen (FastAPI's `UploadFile` braucht das Paket) — es ist
laut `requirements.txt` bereits als Abhängigkeit gelistet (`python-multipart>=0.0.9`), sollte also
vorhanden sein. Falls der Test mit einem Fehler zu fehlendem `python-multipart` fehlschlägt:
`pip install python-multipart`.

- [ ] **Step 5: Volle Suite ausführen**

Run: `cd /Users/timoegersdorfer/Alfred && python3 -m pytest tests/ -q`
Expected: alle Tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add web/routers/voice.py web/routers/__init__.py tests/test_voice_router.py
git commit -m "feat(web): /api/voice/segment Endpunkt für Sprach-Erfassungs-Messaufbau

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend — Mikrofon-Erfassung + einfache VAD + HUD-Anzeige

**Files:**
- Create: `apps/desktop/src/voice-capture.ts`
- Modify: `apps/desktop/index.html`
- Modify: `apps/desktop/src/style.css`
- Modify: `apps/desktop/src/main.ts`

**Interfaces:**
- Consumes: `getBaseUrl()` aus `./config`
- Produces:
  - `type VoiceSegmentResult = { text: string; addressed: boolean }`
  - `startVoiceCapture(baseUrl: string, onSegment: (result: VoiceSegmentResult) => void): () => void`
    — startet Mikrofon-Erfassung, gibt eine Stop-Funktion zurück. Segmentiert Sprache über einen
    einfachen Lautstärke-Schwellwert (kein ML-Modell), lädt jedes Segment als WAV/WebM an
    `/api/voice/segment` hoch, ruft `onSegment` mit dem Ergebnis auf.

- [ ] **Step 1: `apps/desktop/src/voice-capture.ts` schreiben**

Dieser Task hat KEINEN automatisierten Vitest-Test — `MediaRecorder`/`AudioContext`/
`getUserMedia` sind Browser-APIs, die in der Node/jsdom-Testumgebung nicht sinnvoll simulierbar
sind (jsdom implementiert keine echte Audio-Pipeline), und eine echte Verifikation braucht ohnehin
eine physische Stimme (siehe Plan-Constraints). Verifikation erfolgt über `tsc --noEmit` (Typen
müssen stimmen) und manuelles Laden der App.

```typescript
export type VoiceSegmentResult = { text: string; addressed: boolean };

const SILENCE_THRESHOLD = 0.02;   // RMS-Lautstärke-Schwelle (0..1)
const SILENCE_MS_TO_STOP = 800;   // so lange Stille beendet ein Sprachsegment
const MIN_SEGMENT_MS = 300;       // kürzere "Segmente" werden verworfen (Rauschen)

export function startVoiceCapture(
  baseUrl: string,
  onSegment: (result: VoiceSegmentResult) => void,
): () => void {
  let stopped = false;
  let stream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let recorder: MediaRecorder | null = null;
  let chunks: BlobPart[] = [];
  let speaking = false;
  let silenceStartedAt: number | null = null;
  let segmentStartedAt = 0;
  let rafId: number | null = null;

  async function uploadSegment(blob: Blob): Promise<void> {
    try {
      const form = new FormData();
      form.append('audio', blob, 'segment.webm');
      const res = await fetch(`${baseUrl}/api/voice/segment`, { method: 'POST', body: form });
      const data = (await res.json()) as VoiceSegmentResult;
      onSegment(data);
    } catch {
      // Netzwerkfehler beim Upload — Segment geht verloren, kein Absturz
    }
  }

  function rms(data: Uint8Array): number {
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / data.length);
  }

  navigator.mediaDevices
    .getUserMedia({ audio: true })
    .then((mediaStream) => {
      if (stopped) {
        mediaStream.getTracks().forEach((t) => t.stop());
        return;
      }
      stream = mediaStream;
      audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const data = new Uint8Array(analyser.fftSize);

      function tick(): void {
        if (stopped || !audioCtx) return;
        analyser.getByteTimeDomainData(data);
        const level = rms(data);
        const now = performance.now();

        if (level > SILENCE_THRESHOLD) {
          silenceStartedAt = null;
          if (!speaking) {
            speaking = true;
            segmentStartedAt = now;
            chunks = [];
            recorder = new MediaRecorder(stream!);
            recorder.ondataavailable = (e) => chunks.push(e.data);
            recorder.start();
          }
        } else if (speaking) {
          if (silenceStartedAt === null) silenceStartedAt = now;
          if (now - silenceStartedAt >= SILENCE_MS_TO_STOP) {
            speaking = false;
            const duration = now - segmentStartedAt;
            const activeRecorder = recorder;
            recorder = null;
            if (activeRecorder && activeRecorder.state !== 'inactive') {
              activeRecorder.onstop = () => {
                if (duration >= MIN_SEGMENT_MS) {
                  uploadSegment(new Blob(chunks, { type: 'audio/webm' }));
                }
              };
              activeRecorder.stop();
            }
          }
        }
        rafId = requestAnimationFrame(tick);
      }
      rafId = requestAnimationFrame(tick);
    })
    .catch(() => {
      // Mikrofon-Zugriff verweigert/nicht verfügbar — Voice-Capture bleibt inaktiv, kein Absturz
    });

  return () => {
    stopped = true;
    if (rafId !== null) cancelAnimationFrame(rafId);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach((t) => t.stop());
    if (audioCtx) audioCtx.close();
  };
}
```

- [ ] **Step 2: `apps/desktop/index.html` — Voice-Status-Anzeige ergänzen**

Im `<body>`, direkt vor dem `<script type="module" src="/src/main.ts"></script>`-Tag, ergänzen:

```html
    <div id="voice-status" style="position:absolute;bottom:8px;right:8px;font-size:10px;color:#00e5ff88;font-family:'SF Mono',monospace;max-width:300px;text-align:right"></div>
```

- [ ] **Step 3: `apps/desktop/src/main.ts` um Voice-Capture ergänzen**

Am Ende von `apps/desktop/src/main.ts` (nach der bestehenden `subscribeUiState(...)`-Zeile)
anhängen:

```typescript
import { startVoiceCapture } from './voice-capture';
import type { VoiceSegmentResult } from './voice-capture';

function renderVoiceStatus(result: VoiceSegmentResult): void {
  const el = document.getElementById('voice-status');
  if (!el) return;
  const marker = result.addressed ? '🎙️ an Alfred' : '🎙️ ignoriert';
  el.textContent = `${marker}: "${result.text}"`;
}

startVoiceCapture(getBaseUrl(), renderVoiceStatus);
```

(Den `import { startVoiceCapture } ...`-Block an den Anfang der Datei zu den anderen Imports
verschieben, TypeScript erlaubt Imports zwar auch mitten in der Datei nicht wirklich — Imports
MÜSSEN am Dateianfang stehen. Also: die beiden `import`-Zeilen ganz oben bei den bestehenden
Imports ergänzen, NUR die beiden Aufruf-Zeilen `startVoiceCapture(...)`/die Funktion
`renderVoiceStatus` ans Ende der Datei anhängen.)

- [ ] **Step 4: Type-Check + bestehende Tests ausführen**

Run: `cd apps/desktop && npm test && npx tsc --noEmit`
Expected: alle 13 Tests PASS, `tsc` ohne Ausgabe (Exit 0)

- [ ] **Step 5: Laden ohne Absturz verifizieren (kein echter Sprachtest — siehe Constraints)**

```bash
cd /Users/timoegersdorfer/Alfred/apps/desktop
npm run tauri dev
```

Im Hintergrund starten, ein paar Sekunden warten, per Prozessliste bestätigen dass der Prozess
läuft (kein sofortiger Crash durch einen JS-Fehler beim Laden von `voice-capture.ts`), danach
sauber beenden. Ein Mikrofon-Berechtigungsdialog kann erscheinen (abhängig vom OS/Tauri-Setup) —
das ist erwartet, kein Fehler.

**Explizit NICHT Teil dieser automatisierten Verifikation:** ob die Sprach-Erkennung bei echtem
Sprechen sinnvoll auslöst, ob die Latenz niedrig genug ist, ob die Trefferquote (Fehlalarme vs.
verpasste Anfragen) akzeptabel ist. Diese drei Punkte sind der eigentliche Zweck des
"isolierten Messversuchs" aus der Spec — sie erfordern eine echte menschliche Stimme und müssen
von Timo selbst getestet werden. Im Bericht explizit als offen markieren.

- [ ] **Step 6: Commit**

```bash
cd /Users/timoegersdorfer/Alfred
git add apps/desktop/src/voice-capture.ts apps/desktop/index.html apps/desktop/src/style.css apps/desktop/src/main.ts
git commit -m "feat(desktop): Mikrofon-Erfassung + einfache Sprach-Segmentierung (Phase 5a)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec-Abdeckung:** Deckt den ersten, isolierten Teil von Abschnitt 5 der Spec ab (Mikrofon +
Segmentierung + Transkription + Adress-Check + Sichtbarkeit), OHNE die dort auch beschriebene
Agent-Anbindung — das ist bewusst so begrenzt (Spec empfiehlt selbst, diesen Teil zuerst isoliert
zu bauen und zu messen). Die eigentliche Messung (Latenz, Fehlalarm-Rate) ist NICHT durch diesen
Plan "erledigt", sondern durch ihn erst ermöglicht — das Ergebnis hängt von Timos eigenem Test ab.

**Platzhalter-Scan:** Keine TBD/TODO. Der einzige bewusst unvollständige Teil (kein automatisierter
Sprachtest) ist explizit als Constraint benannt, nicht als vager Platzhalter.

**Typ-Konsistenz:** `VoiceSegmentResult` (Task 3, TS) ist feldgleich mit dem JSON-Rückgabeformat
von `/api/voice/segment` (Task 2, Python): `{"text": str, "addressed": bool}`.
