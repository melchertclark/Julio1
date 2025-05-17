import os
import tempfile
from datetime import datetime
from unittest import mock

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


def test_julio_trigger_once_per_run():
    alerted = set()
    with mock.patch("polling.requests.post") as mock_post:
        triggered = False
        triggered = polling.handle_trigger("hello Julio", "12:00", alerted, triggered)
        triggered = polling.handle_trigger("Julio again", "12:01", alerted, triggered)
        assert mock_post.call_count == 1
        # Ensure timestamp included in payload
        args, kwargs = mock_post.call_args_list[0]
        assert b"12:00" in kwargs["data"]


def test_julio_trigger_resets_next_run():
    alerted = set()
    with mock.patch("polling.requests.post") as mock_post:
        triggered = False
        triggered = polling.handle_trigger("Julio here", "08:00", alerted, triggered)
        assert mock_post.call_count == 1
        # New run should trigger again
        triggered = False
        triggered = polling.handle_trigger("Another Julio", "09:00", alerted, triggered)
        assert mock_post.call_count == 2
