"""Tests for the Gunicorn settings of the image."""

import os
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlsplit

import pytest

from trs_filer import gunicorn_config
from trs_filer.gunicorn_config import _worker_tmp_dir
from tests.gunicorn_settings import DOCKERFILE, load_settings

APP = "trs_filer.app:create_app()"


def test_settings() -> None:
    """Gunicorn loads the settings, without preloading the app."""
    cfg = load_settings().cfg
    assert cfg.bind == ["0.0.0.0:8080"]
    assert cfg.worker_class_str == "gthread"
    assert (cfg.workers, cfg.threads) == (1, 4)
    assert (cfg.timeout, cfg.graceful_timeout) == (30, 20)
    assert cfg.limit_request_line == 4094
    assert cfg.limit_request_fields == 100
    assert cfg.limit_request_field_size == 8190
    assert (cfg.accesslog, cfg.errorlog) == (None, "-")
    assert cfg.control_socket_disable
    assert not cfg.preload_app
    assert cfg.worker_tmp_dir == gunicorn_config.worker_tmp_dir


def test_keepalive() -> None:
    """Idle keep-alive connections are kept longer than by proxies.

    That is, longer than by proxies in front of the app (60 seconds for
    ingress-nginx, 90 seconds for Traefik), so that proxies don't reuse
    connections that Gunicorn closes; they wait in the worker's poller, not
    in its threads, up to Gunicorn's limit of connections.
    """
    cfg = load_settings().cfg
    assert cfg.keepalive == 100
    assert cfg.keepalive > 90
    assert cfg.worker_connections - cfg.threads >= 100


def test_cmd_args() -> None:
    """`GUNICORN_CMD_ARGS` overrides the settings."""
    args = shlex.join(["--workers", "2", "--threads", "8", "--timeout", "60"])
    cfg = load_settings(args).cfg
    assert (cfg.workers, cfg.threads, cfg.timeout) == (2, 8, 60)
    assert cfg.graceful_timeout == 20


def test_app_uri() -> None:
    """The image's command creates the app with the factory."""
    assert load_settings().app_uri == APP


def test_health_check_port() -> None:
    """The image's health check probes the port Gunicorn listens on."""
    (bind,) = load_settings().cfg.bind
    (url,) = re.findall(r"^ENV HEALTHCHECK_URL=(\S+)$", DOCKERFILE.read_text(), re.M)
    assert urlsplit(url).port == int(bind.rpartition(":")[2])


def test_load_settings_restores(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Loading the settings restores the arguments and the environment.

    That is, the arguments, `GUNICORN_CMD_ARGS` and the current directory.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.setenv("GUNICORN_CMD_ARGS", "--workers 3")
    assert load_settings("--chdir /").cfg.workers == 1
    assert load_settings().cfg.workers == 1
    assert (os.getcwd(), sys.argv) == (str(tmp_path), ["pytest"])
    assert os.environ["GUNICORN_CMD_ARGS"] == "--workers 3"
    monkeypatch.delenv("GUNICORN_CMD_ARGS")
    load_settings("--workers 2")
    assert "GUNICORN_CMD_ARGS" not in os.environ


def test_worker_tmp_dir_shm(tmp_path: Path) -> None:
    """A writable memory-backed directory is used for heartbeat files."""
    assert _worker_tmp_dir(tmp_path) == str(tmp_path)


@pytest.mark.parametrize("mode", [0o500, None])
def test_worker_tmp_dir_default(tmp_path: Path, mode: int | None) -> None:
    """Without a writable memory-backed directory, Gunicorn's default is used.

    That is, `None`, the temporary directory.
    """
    shm = tmp_path / "shm"
    if mode is not None:
        shm.mkdir(mode=mode)
    try:
        if mode is not None and os.access(shm, os.W_OK):
            pytest.skip("directory permissions are not enforced (e.g., root)")
        assert _worker_tmp_dir(shm) is None
    finally:
        if mode is not None:
            shm.chmod(0o700)
