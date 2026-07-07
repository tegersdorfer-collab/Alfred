#!/usr/bin/env python3.14
"""Interaktive Tastatur-Steuerung für den X5-Droid — testet den Treiber live.

Start:  python3.14 scripts/robot_drive.py

Tasten (jeweils Enter):
  w/s/a/d  vor / zurück / links drehen / rechts drehen  (je ~1 s, stoppt selbst)
  x        sofort stoppen
  o/c      Greifer auf / zu
  1..15    Sound abspielen
  p        aktuelle Sensorwerte anzeigen (ir0 / ir1 / Druck)
  +/-      Fahrleistung hoch/runter
  q        beenden
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.robot import connect
from tools.robot import protocol as P


async def ainput(prompt: str = "") -> str:
    return await asyncio.to_thread(input, prompt)


async def main() -> None:
    print(__doc__)
    print("Verbinde mit X5 (Droid an, keine andere App verbunden) ...")
    bot = await connect()
    print("✅ Verbunden. Los geht's.\n")

    power = 0.5
    secs = 1.0
    try:
        while True:
            cmd = (await ainput(f"[pow {power:.0%}] > ")).strip().lower()
            if not cmd:
                continue
            if cmd == "q":
                break
            elif cmd == "w":
                await bot.forward(power, secs)
            elif cmd == "s":
                await bot.backward(power, secs)
            elif cmd == "a":
                await bot.turn_left(power, secs)
            elif cmd == "d":
                await bot.turn_right(power, secs)
            elif cmd == "x":
                await bot.stop()
            elif cmd == "o":
                await bot.grip_open()
            elif cmd == "c":
                await bot.grip_close()
            elif cmd == "p":
                s = bot.sensors
                if s:
                    print(f"   ir0={s.ir0}  ir1={s.ir1}  druck={s.pressure}  (ruhe≈{P.Sensors.IDLE})")
                else:
                    print("   noch keine Sensordaten")
            elif cmd == "+":
                power = min(1.0, round(power + 0.1, 2))
            elif cmd == "-":
                power = max(0.1, round(power - 0.1, 2))
            elif cmd.isdigit():
                await bot.play_sound(int(cmd))
            else:
                print("   ? w/s/a/d x o/c 1..15 p +/- q")
    finally:
        print("\nStoppe & trenne ...")
        await bot.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
