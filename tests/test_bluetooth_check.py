"""Tests für den macOS-Bluetooth-Entitlement-Check (tools/robot/platform_check.py).
Erstellt temporäre Info.plists; simuliert Plattformen über sys.platform.
"""

import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.robot import platform_check as pc

_KEY = "NSBluetoothAlwaysUsageDescription"


def _write_plist(path, keys: dict):
    with open(path, "wb") as f:
        plistlib.dump(keys, f)


def test_plist_with_key_is_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "darwin")
    p = tmp_path / "Info.plist"
    _write_plist(p, {_KEY: "Mantis nutzt Bluetooth", "CFBundleName": "Python"})
    assert pc.bluetooth_entitlement_ok(str(p)) is True


def test_plist_without_key_is_not_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "darwin")
    p = tmp_path / "Info.plist"
    _write_plist(p, {"CFBundleName": "Python"})  # Bluetooth-Key fehlt
    assert pc.bluetooth_entitlement_ok(str(p)) is False


def test_missing_plist_does_not_block(monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "darwin")
    # Nicht existierender Pfad → True (nicht fälschlich blockieren)
    assert pc.bluetooth_entitlement_ok("/nonexistent/Info.plist") is True


def test_non_macos_always_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "linux")
    p = tmp_path / "Info.plist"
    _write_plist(p, {"CFBundleName": "Python"})  # Key fehlt, aber egal auf Linux
    assert pc.bluetooth_entitlement_ok(str(p)) is True


def test_info_plist_path_none_on_non_macos(monkeypatch):
    monkeypatch.setattr(pc.sys, "platform", "linux")
    assert pc.info_plist_path() is None


def test_hint_mentions_fix_script():
    assert "fix_bluetooth.sh" in pc.entitlement_hint()
