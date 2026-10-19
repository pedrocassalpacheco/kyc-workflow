"""Shared pytest fixtures. Everything here runs offline (localhost only)."""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

from kyc_workflow.config import Settings
from kyc_workflow.gateway import (
    BackendResult,
    FakeBackend,
    HeliosGateway,
    ModelRequest,
    TokenUsage,
)

# Markers used to prove content never reaches the metadata log.
SECRET_SYSTEM = "SYSTEM-PROMPT-MARKER policy text that must never be logged"
SECRET_USER = "USER-CONTENT-MARKER case material that must never be logged"
SECRET_ANSWER = "ANSWER-MARKER model output that must never be logged"


@pytest.fixture
def make_settings():
    def _make(**overrides) -> Settings:
        base = dict(
            model="claude-sonnet-4-6",
            model_allowlist=("claude-sonnet-4-6",),
            region="asia-southeast1",
            max_retries=2,
            retry_backoff_s=0.1,
            caller_id="harness-test",
        )
        base.update(overrides)
        return Settings(**base)

    return _make


@pytest.fixture
def make_request():
    def _make(**overrides) -> ModelRequest:
        base = dict(case_id="PR-88214", analyst_id="AN-SAM", system=SECRET_SYSTEM, user=SECRET_USER)
        base.update(overrides)
        return ModelRequest(**base)

    return _make


@pytest.fixture
def ok_result():
    def _make(text=SECRET_ANSWER, parsed=None) -> BackendResult:
        return BackendResult(
            model="claude-sonnet-4-6",
            text=text,
            parsed=parsed,
            stop_reason="end_turn",
            usage=TokenUsage(input_tokens=120, output_tokens=30, cache_read_input_tokens=100),
        )

    return _make


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    return tmp_path / "helios.jsonl"


@pytest.fixture
def make_gateway(make_settings, log_path):
    """Build a HeliosGateway over a FakeBackend with a fake clock and a
    recording sleep, so retries and backoff are observable and instant."""

    def _make(backend: FakeBackend | None = None, **settings_overrides) -> HeliosGateway:
        sleeps: list[float] = []
        gw = HeliosGateway(
            backend or FakeBackend(),
            make_settings(**settings_overrides),
            log_path=log_path,
            clock=iter(range(0, 1_000_000)).__next__,
            sleep=sleeps.append,
        )
        gw.sleeps = sleeps  # type: ignore[attr-defined]  # exposed for assertions
        return gw

    return _make


# -- the bank's HTTP API over the synthetic fixture export -----------------------

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "bank_export"
BANK_API_KEY = "test-key"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def bank_api_url():
    """Start bank_api/server.py over tests/fixtures/bank_export for the test session."""
    port = free_port()
    env = {**os.environ, "VGB_DATA_DIR": str(FIXTURES), "VGB_PORT": str(port), "VGB_API_KEY": BANK_API_KEY}
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "bank_api" / "server.py")],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            with urllib.request.urlopen(url + "/", timeout=1) as resp:
                if json.load(resp).get("datasets"):
                    break
        except Exception:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("bank api did not start: " + (proc.stdout.read() if proc.stdout else ""))
    yield url
    proc.terminate()
    proc.wait(timeout=5)


@pytest.fixture
def anyio_backend():
    return "asyncio"
