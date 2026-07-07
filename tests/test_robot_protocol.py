"""Tests für die reine X5-Protokoll-Logik (tools/robot/protocol.py)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.robot import protocol as P


def test_packet_length_is_9():
    assert len(P.forward()) == 9
    assert len(P.stop()) == 9
    assert len(P.grip_open()) == 9


def test_forward_full_power_max_time():
    # links vorwärts (cmd 0x00), rechts vorwärts (cmd 0x01), Greifer Bremse
    assert P.forward(power=1.0, secs=2.55) == bytes([0, 255, 254, 1, 255, 254, 2, 0, 0])


def test_backward_full_power_max_time():
    assert P.backward(power=1.0, secs=2.55) == bytes([1, 255, 254, 0, 255, 254, 2, 0, 0])


def test_turn_left_is_ccw():
    # links rückwärts (0x01), rechts vorwärts (0x01)
    assert P.turn_left(power=1.0, secs=2.55) == bytes([1, 255, 254, 1, 255, 254, 2, 0, 0])


def test_turn_right_is_cw():
    # links vorwärts (0x00), rechts rückwärts (0x00)
    assert P.turn_right(power=1.0, secs=2.55) == bytes([0, 255, 254, 0, 255, 254, 2, 0, 0])


def test_stop_all_brake():
    assert P.stop() == bytes([2, 0, 0, 2, 0, 0, 2, 0, 0])


def test_gripper_maps_open_close():
    # nur Motor 2, Räder gebremst
    assert P.grip_open(power=1.0, secs=1.0) == bytes([2, 0, 0, 2, 0, 0, 1, 255, 100])
    assert P.grip_close(power=1.0, secs=1.0) == bytes([2, 0, 0, 2, 0, 0, 0, 255, 100])


def test_power_and_time_scaling_and_clamping():
    assert P._pow_byte(0.0) == 0
    assert P._pow_byte(0.5) == 127
    assert P._pow_byte(1.0) == 255
    assert P._pow_byte(2.0) == 255  # geclamped
    assert P._time_byte(1.0) == 100
    assert P._time_byte(0.0) == 0
    assert P._time_byte(10.0) == 254  # auf 2.55 s geclamped (Firmware schneidet ab)


def test_sound_is_single_byte():
    assert P.sound(0x07) == bytes([0x07])


def test_parse_sensors_baseline():
    frame = bytes([13, 0, 13, 0, 13, 0, 13, 0, 0])
    s = P.parse_sensors(frame)
    assert (s.ir0, s.ir1, s.pressure, s.ch3) == (13, 13, 13, 13)


def test_parse_sensors_little_endian_and_object_near():
    # ir1 = 0x0288 = 648 (Hand nah vor Sensor)
    frame = bytes([0x0D, 0x00, 0x88, 0x02, 0x0D, 0x00, 0x0D, 0x00, 0x00])
    s = P.parse_sensors(frame)
    assert s.ir0 == 13
    assert s.ir1 == 648
    assert s.pressure == 13


def test_parse_sensors_rejects_short():
    assert P.parse_sensors(b"\x00\x01") is None
    assert P.parse_sensors(None) is None
