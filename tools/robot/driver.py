"""Asynchroner BLE-Treiber für den X5-Droid (bleak).

Dünner Wrapper um `protocol`: verbinden, Sensor-Notify abonnieren, High-Level-
Aktionen senden. Bewusst schlank gehalten (Mantis-Leitlinie: einfacher Code).

Beispiel:
    async with await connect() as bot:
        await bot.forward(power=0.5, secs=1.0)
        await bot.grip_close()
        print(bot.sensors)  # zuletzt empfangener Sensorstand
"""

from __future__ import annotations

from typing import Callable, Optional

from bleak import BleakClient, BleakScanner

from . import protocol as P


class X5Robot:
    """Verbindung zu einem X5-Droid. Motoren = write-without-response, Sound = write."""

    def __init__(self, device_or_address, name: str = P.DEVICE_NAME):
        self._target = device_or_address
        self.name = name
        self._client: Optional[BleakClient] = None
        self.sensors: Optional[P.Sensors] = None
        self.on_sensors: Optional[Callable[[P.Sensors], None]] = None

    # ── Verbindung ───────────────────────────────────────────────────────────
    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> "X5Robot":
        self._client = BleakClient(self._target)
        await self._client.connect()
        await self._client.start_notify(P.CH_SENSORS, self._handle_sensors)
        return self

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self.stop()
            except Exception:
                pass
            await self._client.disconnect()
            self._client = None

    async def __aenter__(self) -> "X5Robot":
        if not self.is_connected:
            await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.disconnect()

    # ── intern ───────────────────────────────────────────────────────────────
    def _handle_sensors(self, _char, data: bytearray) -> None:
        s = P.parse_sensors(data)
        if s is not None:
            self.sensors = s
            if self.on_sensors is not None:
                self.on_sensors(s)

    async def _motors(self, packet: bytes) -> None:
        await self._client.write_gatt_char(P.CH_MOTORS, packet, response=False)

    # ── High-Level-Aktionen ──────────────────────────────────────────────────
    async def forward(self, power: float = 0.4, secs: float = 0.0) -> None:
        await self._motors(P.forward(power, secs))

    async def backward(self, power: float = 0.4, secs: float = 0.0) -> None:
        await self._motors(P.backward(power, secs))

    async def turn_left(self, power: float = 0.4, secs: float = 0.0) -> None:
        await self._motors(P.turn_left(power, secs))

    async def turn_right(self, power: float = 0.4, secs: float = 0.0) -> None:
        await self._motors(P.turn_right(power, secs))

    async def stop(self) -> None:
        await self._motors(P.stop())

    async def grip_open(self, power: float = 1.0, secs: float = 1.0) -> None:
        await self._motors(P.grip_open(power, secs))

    async def grip_close(self, power: float = 1.0, secs: float = 1.0) -> None:
        await self._motors(P.grip_close(power, secs))

    async def play_sound(self, sound_id: int) -> None:
        # Sound-Kanal ist write-with-response (kein WWR verfügbar).
        await self._client.write_gatt_char(P.CH_AUDIO, P.sound(sound_id), response=True)


async def find_device(name: str = P.DEVICE_NAME, timeout: float = 10.0):
    """X5 per BLE-Name finden (macOS-Adresse variiert, daher nicht fest verdrahtet)."""
    return await BleakScanner.find_device_by_name(name, timeout=timeout)


async def connect(name: str = P.DEVICE_NAME, timeout: float = 10.0) -> X5Robot:
    """X5 finden, verbinden und ein einsatzbereites X5Robot zurückgeben."""
    device = await find_device(name, timeout)
    if device is None:
        raise RuntimeError(
            f"'{name}' nicht gefunden. Ist der Droid an und keine andere App verbunden?"
        )
    robot = X5Robot(device, name=name)
    await robot.connect()
    return robot
