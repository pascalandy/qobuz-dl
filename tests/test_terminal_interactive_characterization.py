import io
import logging

import pytest

from qobuz_dl import color
from qobuz_dl.core import QobuzDL


def test_exported_color_constants_are_strings():
    for name in [
        "DF",
        "BG",
        "RESET",
        "OFF",
        "RED",
        "BLUE",
        "GREEN",
        "YELLOW",
        "CYAN",
        "MAGENTA",
    ]:
        assert isinstance(getattr(color, name), str)


def test_colored_log_messages_reset_after_each_record():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("qobuz_dl.tests.color_reset")
    old_handlers = logger.handlers[:]
    old_propagate = logger.propagate
    old_level = logger.level
    try:
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)

        logger.info(f"{color.YELLOW}colored")

        assert stream.getvalue() == f"{color.YELLOW}colored{color.RESET}\n"
    finally:
        logger.handlers = old_handlers
        logger.propagate = old_propagate
        logger.setLevel(old_level)


def test_interactive_builtin_prompts_return_selected_urls_without_download(
    tmp_path, monkeypatch
):
    answers = iter(
        [
            "2",  # Tracks
            "alpha beta",
            "1",
            "n",
            "2",  # Lossless quality
        ]
    )
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    qdl = QobuzDL(directory=tmp_path, interactive_limit=3)
    qdl.search_by_type = lambda query, item_type, limit: [
        {"text": f"{query} result", "url": "https://play.qobuz.com/track/123"}
    ]
    downloaded = []
    qdl.download_list_of_urls = lambda urls: downloaded.append(urls)

    assert qdl.interactive(download=False) == ["https://play.qobuz.com/track/123"]
    assert qdl.quality == 6
    assert downloaded == []
    assert "I'll search for" in prompts[0]
    assert "Items to download" in prompts[2]


def test_interactive_quality_prompt_defaults_to_current_quality(tmp_path, monkeypatch):
    answers = iter(
        [
            "1",  # Albums
            "alpha beta",
            "1",
            "n",
            "",  # accept current quality default
        ]
    )
    prompts = []

    def fake_input(prompt):
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    qdl = QobuzDL(directory=tmp_path, quality=27, interactive_limit=1)
    qdl.search_by_type = lambda query, item_type, limit: [
        {"text": f"{query} result", "url": "https://play.qobuz.com/album/123"}
    ]

    assert qdl.interactive(download=False) == ["https://play.qobuz.com/album/123"]
    assert qdl.quality == 27
    assert "Quality [default 4]" in prompts[-1]


def test_interactive_multiselect_accepts_commas_and_ranges(tmp_path, monkeypatch):
    answers = iter(["2", "alpha beta", "1,3-4", "n", "2"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    qdl = QobuzDL(directory=tmp_path, interactive_limit=4)
    qdl.search_by_type = lambda query, item_type, limit: [
        {"text": f"result {index}", "url": f"https://play.qobuz.com/track/{index}"}
        for index in range(1, 5)
    ]

    assert qdl.interactive(download=False) == [
        "https://play.qobuz.com/track/1",
        "https://play.qobuz.com/track/3",
        "https://play.qobuz.com/track/4",
    ]


def test_interactive_search_loop_retries_empty_selection_and_dedupes_in_order(
    tmp_path, monkeypatch
):
    answers = iter(
        [
            "2",  # Tracks
            "alpha beta",
            "",  # no selection retries the search loop
            "gamma delta",
            "3,1-2,2,3",  # preserves first-seen order while deduping
            "n",
            "",  # accept current quality default
        ]
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    qdl = QobuzDL(directory=tmp_path, quality=6, interactive_limit=4)
    search_calls = []

    def fake_search(query, item_type, limit):
        search_calls.append((query, item_type, limit))
        return [
            {
                "text": f"{query} result {index}",
                "url": f"https://play.qobuz.com/track/{index}",
            }
            for index in range(1, 5)
        ]

    qdl.search_by_type = fake_search
    qdl.download_list_of_urls = lambda urls: pytest.fail(
        f"download dispatched in no-download mode: {urls}"
    )

    assert qdl.interactive(download=False) == [
        "https://play.qobuz.com/track/3",
        "https://play.qobuz.com/track/1",
        "https://play.qobuz.com/track/2",
    ]
    assert search_calls == [
        ("alpha beta", "track", 4),
        ("gamma delta", "track", 4),
    ]
    assert qdl.quality == 6


def test_interactive_keyboard_interrupt_cancels_cleanly(tmp_path, monkeypatch):
    def fake_input(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", fake_input)

    qdl = QobuzDL(directory=tmp_path)
    qdl.search_by_type = lambda *args, **kwargs: pytest.fail(
        "search dispatched after keyboard interrupt"
    )
    qdl.download_list_of_urls = lambda urls: pytest.fail(
        f"download dispatched after keyboard interrupt: {urls}"
    )

    assert qdl.interactive(download=False) is None
