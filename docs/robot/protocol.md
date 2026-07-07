# X5-Droid — BLE-Protokoll (Recon-Notizen)

Lebendes Dokument. Ergänzt sich während Phase 0 (Try-and-Error).

## Gerät
- **BLE-Name:** `EVRobot2`
- **macOS-Adresse (UUID, keine MAC):** `B2D3A2E1-CB64-1E9C-A19B-8C87F04D7D2D`
  - Hinweis: macOS zeigt geräteinterne UUIDs, keine MAC. Adresse kann pro Mac variieren →
    im Treiber besser per **Name** (`EVRobot2`) verbinden.
- RSSI nah am Roboter: ~ −45 dBm.

## GATT-Layout
Ein einziger Custom-Service:

**Service** `2f5772da-18e3-4f2e-82ab-910e81b9f232`

| Charakteristik | Handle | Properties | Vermutete Rolle |
|---|---|---|---|
| `5e366294-5436-4356-a009-7ccd1e03526d` | 15 | notify, read | **Telemetrie/Sensoren** (einziger Notify-Kanal) |
| `165aecf8-ed44-45e7-aae4-63789234a30f` | 18 | write-without-response, read, write | Befehle (Kandidat A) |
| `cc9151df-c5eb-477a-a793-287a5500fc81` | 20 | read, write | Config? (kein WWR) |
| `26c8d1e9-f4ae-4f76-97ea-8576d5e23079` | 22 | write-without-response, read, write | Befehle (Kandidat B) |

## Befehls-Bytes (Bytes → Wirkung)
_(wird beim Ausprobieren gefüllt)_

| Charakteristik | Bytes (hex) | Wirkung |
|---|---|---|
| | | |

## Sensor-Frames (Notify 5e36…) — DEKODIERT ✅

Der Kanal streamt **kontinuierlich** ~10–15 Frames/s, je **9 Bytes**:

```
 [0:2] [2:4] [4:6] [6:8] [8]
  ch0   ch1   ch2   ch3  term
```

- **4 Kanäle** à 16 Bit, **little-endian** (uint16).
- **Byte 8** = konstant `0x00` (Terminator).
- **Ruhewert** jedes Kanals = `0x000d` = **13** (nichts in Reichweite).
- **Höherer Wert = Objekt näher** (analoge IR-Reflexion, keine Kamera/kein Bild).

Beobachtete Reaktionen beim Handwedeln:
| Kanal | Bytes | Ruhe | Max beobachtet | Reaktion |
|---|---|---|---|---|
| ch0 | 0–1 | 13 | ~761 (`0x02f9`) | stark (ein IR-Sensor) |
| ch1 | 2–3 | 13 | ~798 (`0x031e`) | stark (anderer IR-Sensor) |
| ch2 | 4–5 | 13 | ~35 | schwach |
| ch3 | 6–7 | 13 | 13 (konstant) | keine (bei diesem Test) |

→ ch0 & ch1 sind die beiden Haupt-IR-Sensoren (vorne/hinten). ch2/ch3 noch
  zuordnen (evtl. seitlich, Boden-/Liniensensor, oder Greifer). Nächster Test:
  gezielt nur vorne bzw. nur hinten wedeln, um ch0↔ch1 = vorne/hinten festzulegen.

## Offene Fragen
- **Befehle:** Welcher Write-Kanal steuert Motoren/Greifer/Sound (18 vs. 22 vs. 20)?
  Format? → nächster Schritt (Try-and-Error oder PacketLogger-Sniff).
- Handshake/Init nötig, bevor Befehle wirken?
- ch2/ch3 physisch zuordnen (welcher Sensor am Roboter).
