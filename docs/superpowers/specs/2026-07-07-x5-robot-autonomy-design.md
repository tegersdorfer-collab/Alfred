# X5-Droid Autonomie über Mantis — Design

**Datum:** 2026-07-07
**Status:** Entwurf → Phase 0/1 konkret, Phase 2–4 als Roadmap (werden nach Recon detailliert)

## Ziel

Der Clementoni "Galileo Science" RoboMaker **X5-Droid** (gebaut) soll von **Mantis** aus
autonom gesteuert werden — **ohne die Clementoni-App**. Endziel: echte Autonomie
(Hindernis-Vermeidung, Patrouille, Verhalten auf Sensor-Basis). Wir bauen gestaffelt dorthin.

### Fähigkeiten des X5 (laut Nutzer)
- Fahren (Antrieb, Lenkung)
- Greifen (Greifer auf/zu)
- Roboter-Sounds abspielen
- IR-Sensoren vorne + hinten ("Kameras" — real vermutlich IR-Abstandssensoren, kein Bild)
- Anbindung: **Bluetooth Low Energy (BLE 4.1)**, normalerweise via Clementoni-App

### Erwartungs-Realität IR-Sensoren
Über BLE 4.1 ist **kein Videostream** möglich (Bandbreite). Die "Kameras" liefern mit hoher
Wahrscheinlichkeit pro Seite ein **Flag** (Hindernis ja/nein) oder einen **groben Abstandswert**.
Die echte Semantik wird empirisch bestimmt (Hand vor Sensor halten, Notify-Bytes beobachten).

## Ansatz

**Sniff-optional, Try-and-Error-first.** Das Clementoni-BLE-Protokoll ist nicht dokumentiert.
Statt zwingend die App zu sniffen, erkunden wir zuerst vom Mac aus empirisch — das ist billiger
und für die Sensor-Semantik ohnehin die beste Methode.

Verworfene Alternativen:
- **Flipper Zero als Sniffer:** ungeeignet (STM32WB55 kann keine fremde Verbindung über 37 Kanäle
  mitverfolgen).
- **Sofort voll sniffen:** nur als Fallback nötig, falls ein Handshake/Init nicht erratbar ist.
- **nRF52840-Dongle:** Backup-Hardware, nur falls PacketLogger + Try-and-Error nicht reichen.

Fallback-Sniffing (falls nötig): **PacketLogger** (Additional Tools for Xcode) + Bluetooth-Logging-
Profil auf dem iPhone → zeichnet BLE inkl. Entschlüsselung auf.

## Architektur-Prinzip

- **BLE-Treiber ist pur** — keine Mantis-Abhängigkeiten, unabhängig testbar (CLI).
- **Mantis-Tool ist ein dünner Wrapper** um den Treiber.
- Passt zu Mantis-Leitlinie: *einfacher Code > Abstraktion, lokal first*.

## Phasen

### Phase 0a — Erkunden vom Mac (SOFORT)
- Dependency: `bleak` installieren.
- **Explorer-Skript** (`scripts/robot_explore.py`), interaktiv:
  - Scannen & X5 per Name/MAC finden, verbinden.
  - Alle GATT-Services & Charakteristiken auflisten (Properties: write/notify/read).
  - **Sensor-Modus:** Notify abonnieren, eintreffende Bytes live anzeigen (hex + Zeitstempel) →
    Nutzer wedelt vor vorderem/hinterem Sensor → wir sehen, welche Bytes reagieren.
  - **Befehls-Modus:** Bytes an gewählte Charakteristik schreiben → Roboter beobachten →
    Treffer notieren.
- **Deliverable:** wachsende Tabelle „Bytes → Wirkung" und „Notify-Byte → Sensor-Bedeutung",
  festgehalten in `docs/robot/protocol.md`.

### Phase 0b — Sniffing (nur als Fallback)
- Wenn Try-and-Error hängt (z.B. nötiger Init-Handshake): gezielt *eine* App-Aktion mit
  PacketLogger aufzeichnen, `.pklg` mit `tshark`/Wireshark analysieren, fehlendes Detail ergänzen.

### Phase 1 — Reine BLE-Treiber-Lib (`tools/robot/driver.py`)
- `bleak`-async-Client: verbinden (auto-reconnect), Befehl schreiben, Notify abonnieren.
- Low-Level-Primitive: `drive(...)`, `turn(...)`, `grip(open|close)`, `sound(id)`, Sensor-Callback.
- Ggf. Init-/Handshake-Sequenz aus Phase 0.
- **Eigenständig testbar:** CLI-Skript fährt den Roboter manuell; jeder Befehl wird real verifiziert.

### Phase 2 — Sensor-Layer *(nach Recon detaillieren)*
- Notify-Frames → strukturierter Zustand (IR vorne/hinten), als async-Stream/Latest-State.

### Phase 3 — Mantis-Integration (`tools/robot.py`) *(nach Recon detaillieren)*
- Roboter-Aktionen ins bestehende Tool-/Action-System (`tools/actions.py`-Muster) einhängen.
- High-Level-Kommandos: "fahr vor bis Hindernis", "greif", "patrouilliere".

### Phase 4 — Autonomie-Loop *(nach Recon detaillieren)*
- Verhaltens-Loop (Hindernis-Vermeidung, Patrouille) auf Sensor-Basis, im `idle`/`proactive`-Framework.
- **Safety:** Watchdog/Not-Stop, Befehls-Timeouts, Stopp bei BLE-Verbindungsverlust.

## Offene Punkte (klären sich in Phase 0)
- Sendet der X5 Befehle nur nach einem Handshake? → sonst Phase 0b.
- Sensor-Format: Flag oder Wert? Auflösung? Update-Rate?
- BLE-Stabilität/Latenz vom Mac aus (M4) für einen Autonomie-Loop ausreichend?
- Firmware-Sicherheit: verschlüsselte Verbindung/Pairing nötig? (PacketLogger könnte Keys liefern.)

## Erfolgskriterien
- **Phase 1 erreicht:** Der X5 fährt, lenkt, greift und piept auf Befehl eines Mac-Skripts —
  ohne Clementoni-App.
- **Endziel:** Mantis lässt den X5 autonom eine Fläche abfahren und Hindernissen ausweichen.
