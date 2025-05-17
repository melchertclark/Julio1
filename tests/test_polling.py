import os
from datetime import datetime

import pytest

import polling


def test_transcript_path_creates_folders(tmp_path):
    polling.TRANSCRIPT_ROOT = str(tmp_path)
    now = datetime(2024, 5, 4, tzinfo=polling.TZ)
    path = polling.transcript_path(now)
    assert os.path.exists(os.path.dirname(path))
    assert os.path.basename(path) == "2024-05-04.md"


def test_trigger_detection_and_highlight():
    text = "This is about Julio and something else"
    highlighted = polling.TRIGGER_PATTERN.sub(lambda m: f"**{m.group(0)}**", text)
    assert "**Julio**" in highlighted


def test_rollover_dst(tmp_path):
    polling.TRANSCRIPT_ROOT = str(tmp_path)
    before = datetime(2024, 3, 9, 23, 59, tzinfo=polling.TZ)
    after = datetime(2024, 3, 10, 0, 1, tzinfo=polling.TZ)
    path_before = polling.transcript_path(before)
    path_after = polling.transcript_path(after)
    assert path_before != path_after


def test_deduplicate_transcript(tmp_path):
    file_path = tmp_path / "test.md"
    file_path.write_text(
        "# transcript for 2024-05-04\n\n"
        "## 10:00:00 -- title\n\nhello\n\n"
        "## 11:00:00 -- title\n\nhello\n\n"
    )
    polling.deduplicate_transcript(str(file_path))
    content = file_path.read_text()
    assert content.count("hello") == 1

