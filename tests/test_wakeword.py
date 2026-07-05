import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch

import core.wakeword as wakeword


class TestWakeWordDetector:
    def test_check_true_when_score_above_threshold(self, tmp_path):
        model_path = tmp_path / "mantis.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(wakeword, "_load_model") as mock_load:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"mantis": 0.8}
            mock_load.return_value = mock_model

            detector = wakeword.WakeWordDetector(model_path, threshold=0.5)
            assert detector.check(b"\x00\x00" * 1280) is True

    def test_check_false_when_score_below_threshold(self, tmp_path):
        model_path = tmp_path / "mantis.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(wakeword, "_load_model") as mock_load:
            mock_model = MagicMock()
            mock_model.predict.return_value = {"mantis": 0.2}
            mock_load.return_value = mock_model

            detector = wakeword.WakeWordDetector(model_path, threshold=0.5)
            assert detector.check(b"\x00\x00" * 1280) is False

    def test_check_rejects_wrong_frame_size(self, tmp_path):
        model_path = tmp_path / "mantis.onnx"
        model_path.write_bytes(b"fake")
        with patch.object(wakeword, "_load_model") as mock_load:
            mock_load.return_value = MagicMock()

            detector = wakeword.WakeWordDetector(model_path, threshold=0.5)
            try:
                detector.check(b"\x00\x00" * 128)
                assert False, "expected ValueError for wrong frame size"
            except ValueError:
                pass
