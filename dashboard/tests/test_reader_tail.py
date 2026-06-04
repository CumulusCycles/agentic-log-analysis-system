from pathlib import Path

import pytest

from log_dashboard.ingest.reader import LogReaderError, tail_lines


def test_returns_last_n_lines_exact(tmp_path: Path) -> None:
    f = tmp_path / "log.txt"
    f.write_text("\n".join(f"line-{i}" for i in range(50)) + "\n")
    out = tail_lines(f, 5)
    assert out == ["line-45", "line-46", "line-47", "line-48", "line-49"]


def test_returns_all_when_file_shorter_than_n(tmp_path: Path) -> None:
    f = tmp_path / "log.txt"
    f.write_text("a\nb\nc\n")
    assert tail_lines(f, 100) == ["a", "b", "c"]


def test_returns_empty_for_empty_file(tmp_path: Path) -> None:
    f = tmp_path / "log.txt"
    f.write_text("")
    assert tail_lines(f, 10) == []


def test_raises_log_reader_error_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LogReaderError):
        tail_lines(tmp_path / "does-not-exist.log", 10)


def test_drops_truncated_first_line_when_seek_lands_mid_line(tmp_path: Path) -> None:
    # Force a small seek chunk by writing many long lines so tail_lines has to
    # seek backward multiple times. The first line in the returned window will
    # be partial relative to the file start — it must be discarded.
    f = tmp_path / "log.txt"
    long_line = "x" * 1000
    f.write_text("\n".join(f"{long_line}-{i}" for i in range(100)) + "\n")
    out = tail_lines(f, 5)
    assert len(out) == 5
    # Each returned line must START with the full prefix — i.e. not be truncated.
    for line in out:
        assert line.startswith(long_line)
