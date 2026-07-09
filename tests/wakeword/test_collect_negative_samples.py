import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.wakeword.collect_negative_samples import collect_negative_paths


def test_finds_wav_files_recursively(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "a.wav").write_bytes(b"RIFF")
    (tmp_path / "sub" / "b.wav").write_bytes(b"RIFF")
    (tmp_path / "c.txt").write_bytes(b"not audio")

    result = collect_negative_paths(tmp_path)

    assert sorted(p.name for p in result) == ["a.wav", "b.wav"]


def test_empty_dir_returns_empty_list(tmp_path):
    assert collect_negative_paths(tmp_path) == []
