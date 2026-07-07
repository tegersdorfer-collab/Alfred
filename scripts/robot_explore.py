#!/usr/bin/env python3.14
"""
robot_explore.py — Interaktiver BLE-Explorer für den Clementoni X5-Droid.

Zweck (Phase 0a im Design 2026-07-07-x5-robot-autonomy-design.md):
Vom Mac aus die BLE-Charakteristiken des X5 finden und per Try-and-Error
herausfinden, welche Bytes was bewirken und was die IR-Sensoren melden.

Voraussetzung: X5 ist AN und die Clementoni-App ist NICHT verbunden
(BLE koppelt immer nur mit einem Gerät gleichzeitig).

Start:  python3.14 scripts/robot_explore.py

Ablauf:
  1) [s] scannen  -> Geräteliste, X5 anhand Name/RSSI identifizieren
  2) [c N] verbinden mit Gerät N
  3) [l] Services/Charakteristiken auflisten
  4) [n] alle Notify-Charakteristiken abonnieren
         -> jetzt Hand vor vorderen/hinteren Sensor halten und beobachten,
            welche Bytes sich ändern (= Sensor-Semantik)
  5) [w] Bytes an eine Charakteristik schreiben
         -> Roboter beobachten (fährt? greift? piept?) und Treffer notieren
"""

import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic

LAST_FILE = ".robot_last"  # merkt sich zuletzt benutzte Geräteadresse


async def ainput(prompt: str = "") -> str:
    """input() ohne den asyncio-Loop (und damit die Notify-Callbacks) zu blockieren."""
    return await asyncio.to_thread(input, prompt)


def ts() -> str:
    return time.strftime("%H:%M:%S")


async def scan(timeout: float = 8.0):
    print(f"\n🔍 Scanne {timeout:.0f}s nach BLE-Geräten ...")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    # nach Signalstärke sortieren — der X5 in Reichweite ist meist oben
    items = sorted(found.values(), key=lambda t: t[1].rssi, reverse=True)
    print(f"\n{len(items)} Geräte gefunden:")
    for i, (dev, adv) in enumerate(items):
        name = dev.name or adv.local_name or "(kein Name)"
        print(f"  [{i:2}] {name:28} {dev.address}   RSSI {adv.rssi} dBm")
    print("\nTipp: Der X5 hat oft einen Namen wie 'Clementoni', 'RoboMaker', 'X5' o.ä.")
    print("      Falls kein Name: das Gerät mit stärkstem RSSI, das nah bei dir ist.")
    return [dev for dev, _ in items]


def dump_services(client: BleakClient):
    print("\n📋 GATT-Services & Charakteristiken:")
    writ, noti = [], []
    for svc in client.services:
        print(f"\n  Service {svc.uuid}  ({svc.description})")
        for ch in svc.characteristics:
            props = ",".join(ch.properties)
            print(f"    Char {ch.uuid}  handle={ch.handle}  [{props}]")
            if "write" in ch.properties or "write-without-response" in ch.properties:
                writ.append(ch)
            if "notify" in ch.properties or "indicate" in ch.properties:
                noti.append(ch)
    print(f"\n  → {len(writ)} schreibbar, {len(noti)} notify/indicate")
    return writ, noti


def make_notify_cb():
    """Dekodiert das 9-Byte-Sensorframe (4x uint16 LE + Konstante) und
    druckt nur bei nennenswerter Änderung, um die Konsole nicht zu fluten."""
    state = {"last": None}

    def cb(ch: BleakGATTCharacteristic, data: bytearray):
        if len(data) == 9:
            ch0 = int.from_bytes(data[0:2], "little")
            ch1 = int.from_bytes(data[2:4], "little")
            ch2 = int.from_bytes(data[4:6], "little")
            ch3 = int.from_bytes(data[6:8], "little")
            vals = (ch0, ch1, ch2, ch3)
            last = state["last"]
            if last is None or any(abs(a - b) > 3 for a, b in zip(vals, last)):
                state["last"] = vals
                print(f"  {ts()} SENS  ch0={ch0:5}  ch1={ch1:5}  "
                      f"ch2={ch2:5}  ch3={ch3:5}   raw={data.hex(' ')}")
        else:
            print(f"  {ts()} NOTIFY {ch.uuid} <- {data.hex(' ')} ({len(data)} B)")
    return cb


async def start_all_notify(client: BleakClient, notifiable):
    if not notifiable:
        print("⚠️  Keine Notify-Charakteristiken vorhanden.")
        return
    cb = make_notify_cb()
    for ch in notifiable:
        try:
            await client.start_notify(ch, cb)
            print(f"  ✅ abonniert: {ch.uuid}")
        except Exception as e:
            print(f"  ❌ {ch.uuid}: {e}")
    print("\n👉 Jetzt Hand vor die Sensoren (vorne/hinten) halten und die Bytes beobachten.")
    print("   Mit [enter] zurück ins Menü (Notifications laufen weiter).")
    await ainput()


async def write_cmd(client: BleakClient, writable):
    if not writable:
        print("⚠️  Keine schreibbaren Charakteristiken.")
        return
    print("\nSchreibbare Charakteristiken:")
    for i, ch in enumerate(writable):
        props = ",".join(ch.properties)
        print(f"  [{i}] {ch.uuid}  [{props}]")
    sel = (await ainput("Welche? (Index) > ")).strip()
    if not sel.isdigit() or int(sel) >= len(writable):
        print("Abbruch.")
        return
    ch = writable[int(sel)]
    resp = "write" in ch.properties  # sonst write-without-response
    print("Bytes als Hex eingeben, z.B.  01 0a ff   (leer = zurück).")
    print("Tipp: systematisch durchprobieren, jeden Treffer sofort notieren.")
    while True:
        raw = (await ainput(f"{ch.uuid} < ")).strip()
        if not raw:
            return
        try:
            payload = bytes.fromhex(raw.replace(",", " "))
        except ValueError:
            print("  ⚠️  Ungültiges Hex.")
            continue
        try:
            await client.write_gatt_char(ch, payload, response=resp)
            print(f"  {ts()} SENT {payload.hex(' ')}  → beobachte den Roboter!")
        except Exception as e:
            print(f"  ❌ {e}")


async def session(device):
    print(f"\n🔗 Verbinde mit {device.name or device.address} ...")
    async with BleakClient(device) as client:
        print("✅ Verbunden." if client.is_connected else "❌ Nicht verbunden.")
        try:
            with open(LAST_FILE, "w") as f:
                f.write(device.address)
        except OSError:
            pass
        writable, notifiable = dump_services(client)
        while True:
            print("\n── Menü ──  [l] list  [n] notify-all  [w] write  [d] disconnect")
            cmd = (await ainput("> ")).strip().lower()
            if cmd == "l":
                writable, notifiable = dump_services(client)
            elif cmd == "n":
                await start_all_notify(client, notifiable)
            elif cmd == "w":
                await write_cmd(client, writable)
            elif cmd in ("d", "q", "exit"):
                print("👋 Trenne Verbindung.")
                return
            else:
                print("Unbekannt. [l]/[n]/[w]/[d]")


async def main():
    print(__doc__)
    devices = []
    while True:
        print("\n══ Haupt ══  [s] scan  [c N] connect Gerät N  [q] quit")
        cmd = (await ainput("> ")).strip().lower()
        if cmd == "s":
            devices = await scan()
        elif cmd.startswith("c"):
            parts = cmd.split()
            if len(parts) == 2 and parts[1].isdigit() and int(parts[1]) < len(devices):
                try:
                    await session(devices[int(parts[1])])
                except Exception as e:
                    print(f"❌ Session-Fehler: {e}")
            else:
                print("Nutzung: c N   (erst [s] scannen)")
        elif cmd in ("q", "exit"):
            return
        else:
            print("Unbekannt. [s]/[c N]/[q]")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(0)
