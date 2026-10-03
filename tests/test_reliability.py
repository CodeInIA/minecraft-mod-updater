"""Retries of Modrinth requests and downloads, and the log file."""

import hashlib
import logging

import pytest
import requests

import updater_core as core


class FakeResponse:
    def __init__(self, status=200, data=None, headers=None, body=b""):
        self.status_code = status
        self._data = data
        self.headers = headers or {}
        self.text = str(data)
        self._body = body

    def json(self):
        return self._data

    # streaming downloads
    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)

    def iter_content(self, chunk_size):
        yield self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def client_with(responses):
    """A ModrinthClient whose session answers with `responses` in order (exceptions are raised)."""
    client = core.ModrinthClient()
    waits = []
    client.sleep = waits.append
    queue = list(responses)

    def answer(*_args, **_kwargs):
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    client.session.request = answer
    client.session.get = answer
    return client, waits, queue


def test_temporary_errors_are_retried():
    client, waits, _ = client_with([requests.ConnectionError("reset"), FakeResponse(503),
                                    FakeResponse(200, data=[{"version": "26.3"}])])
    assert client.game_versions() == [{"version": "26.3"}]
    assert waits == [1.0, 2.0]


def test_rate_limit_waits_what_modrinth_asks():
    client, waits, _ = client_with([FakeResponse(429, headers={"X-Ratelimit-Reset": "7"}), FakeResponse(200, data=[])])
    assert client.game_versions() == []
    assert waits == [7.0]


def test_gives_up_after_the_retries():
    client, waits, _ = client_with([FakeResponse(502)] * (core.RETRIES + 1))
    with pytest.raises(core.ModrinthError):
        client.game_versions()
    assert len(waits) == core.RETRIES


def test_client_errors_are_not_retried():
    client, waits, queue = client_with([FakeResponse(404, data="not found"), FakeResponse(200, data=[])])
    with pytest.raises(core.ModrinthError):
        client.game_versions()
    assert waits == [] and len(queue) == 1


def test_failed_and_corrupted_downloads_are_retried(tmp_path):
    good = b"the real jar"
    client, waits, _ = client_with([requests.ConnectionError("reset"), FakeResponse(body=b"garbage"),
                                    FakeResponse(body=good)])
    target = tmp_path / "mod.jar"
    client.download("https://cdn.example/mod.jar", str(target), hashlib.sha512(good).hexdigest())
    assert target.read_bytes() == good


def test_missing_files_are_not_retried(tmp_path):
    client, waits, queue = client_with([FakeResponse(404), FakeResponse(body=b"x")])
    with pytest.raises(core.ModrinthError):
        client.download("https://cdn.example/gone.jar", str(tmp_path / "gone.jar"), None)
    assert not (tmp_path / "gone.jar").exists() and len(queue) == 1


def test_log_file_is_written():
    core.setup_logging()
    try:
        core.log.info("hello from the tests")
        for handler in core.log.handlers:
            handler.flush()
        with open(core.LOG_FILE, encoding="utf-8") as f:
            text = f.read()
        assert "started on" in text and "hello from the tests" in text
    finally:
        for handler in list(core.log.handlers):
            handler.close()
            core.log.removeHandler(handler)
        core.log.setLevel(logging.NOTSET)


def test_detects_minecraft_running_with_the_folder(tmp_path, monkeypatch):
    game = tmp_path / ".minecraft"
    mods = game / "mods"
    mods.mkdir(parents=True)
    other = tmp_path / "other-instance"
    launcher = [("java -Xmx4G net.minecraft.client.main.Main --gameDir " + str(game) + " --version 26.3", "C:\\")]
    prism = [("java -cp NewLaunch.jar org.prismlauncher.EntryPoint", str(game))]
    unrelated = [("java -jar some-tool.jar", str(other))]
    for processes, running in ((launcher, True), (prism, True), (unrelated, False), ([], False)):
        monkeypatch.setattr(core, "_java_processes", lambda p=processes: iter(p))
        assert core.game_running(str(mods)) is running


def test_process_listing_works():
    assert isinstance(list(core._java_processes()), list)  # no errors on this system
