"""Runtime settings, read from the environment and the project's .env file.

Nothing model-specific lives in code: the model string, the Helios allowlist
and the pinned region all come from here so the bank's values can be swapped
in without touching the workflow.

Environment variables (see .env.example; fallbacks shown):

    KYC_MODEL             claude-sonnet-4-6   model the workflow and the chat ask Helios for
    KYC_GUARD_MODEL       claude-haiku-5-5    small model for the chat's intent guardrail
    KYC_EVAL_MODEL        claude-haiku-5-5    small model for evals and the live test
    KYC_MODEL_ALLOWLIST   the three above     comma-separated models Helios will serve
    HELIOS_REGION         asia-southeast1     the one region Helios is pinned to
    HELIOS_MAX_RETRIES    2                   retries after a transient failure
    HELIOS_RETRY_BACKOFF  0.5                 seconds; doubles per retry
    HELIOS_CALLER_ID      kyc-workflow-harness
    KYC_AUDIT_DIR         <project>/audit     where metadata and audit logs go
    ANTHROPIC_API_KEY     (required for live calls; read by the SDK itself)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Last-resort fallbacks only. The values that matter live in .env (see .env.example).
DEFAULT_MODEL = "claude-sonnet-4-6"  # newest Claude served from a single Vertex region
DEFAULT_SMALL_MODEL = "claude-haiku-5-5"
DEFAULT_REGION = "asia-southeast1"


def load_env(dotenv_path: Path | None = None) -> None:
    """Load the project's .env into the process environment (does not override)."""
    load_dotenv(dotenv_path or PROJECT_ROOT / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    model: str = DEFAULT_MODEL
    guard_model: str = DEFAULT_SMALL_MODEL
    eval_model: str = DEFAULT_SMALL_MODEL
    model_allowlist: tuple[str, ...] = (DEFAULT_MODEL, DEFAULT_SMALL_MODEL)
    region: str = DEFAULT_REGION
    max_retries: int = 2
    retry_backoff_s: float = 0.5
    caller_id: str = "kyc-workflow-harness"
    audit_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "audit")

    @classmethod
    def from_env(cls) -> "Settings":
        load_env()
        model = os.environ.get("KYC_MODEL", DEFAULT_MODEL)
        guard_model = os.environ.get("KYC_GUARD_MODEL", DEFAULT_SMALL_MODEL)
        eval_model = os.environ.get("KYC_EVAL_MODEL", DEFAULT_SMALL_MODEL)
        raw_allow = os.environ.get("KYC_MODEL_ALLOWLIST", "")
        allowlist = tuple(m.strip() for m in raw_allow.split(",") if m.strip())
        for configured in (model, guard_model, eval_model):
            if configured not in allowlist:
                allowlist = (*allowlist, configured)
        return cls(
            model=model,
            guard_model=guard_model,
            eval_model=eval_model,
            model_allowlist=allowlist,
            region=os.environ.get("HELIOS_REGION", DEFAULT_REGION),
            max_retries=int(os.environ.get("HELIOS_MAX_RETRIES", "2")),
            retry_backoff_s=float(os.environ.get("HELIOS_RETRY_BACKOFF", "0.5")),
            caller_id=os.environ.get("HELIOS_CALLER_ID", "kyc-workflow-harness"),
            audit_dir=Path(os.environ.get("KYC_AUDIT_DIR", PROJECT_ROOT / "audit")),
        )

    def with_model(self, model: str) -> "Settings":
        """Same settings asking for a different model, added to the allowlist."""
        allow = self.model_allowlist if model in self.model_allowlist else (*self.model_allowlist, model)
        return Settings(
            model=model,
            guard_model=self.guard_model,
            eval_model=self.eval_model,
            model_allowlist=allow,
            region=self.region,
            max_retries=self.max_retries,
            retry_backoff_s=self.retry_backoff_s,
            caller_id=self.caller_id,
            audit_dir=self.audit_dir,
        )


@dataclass(frozen=True)
class McpSettings:
    """Where the vgb-records MCP server is listening (make up starts it)."""

    url: str = "http://127.0.0.1:8001/mcp"

    @classmethod
    def from_env(cls) -> "McpSettings":
        load_env()
        port = os.environ.get("MCP_PORT", "8001")
        return cls(url=os.environ.get("MCP_URL", f"http://127.0.0.1:{port}/mcp"))


@dataclass(frozen=True)
class BankApiSettings:
    """Where the bank's reference data API (bank_api/server.py) is listening."""

    url: str = "http://127.0.0.1:8000"
    api_key: str = "vgb-demo-key"

    @classmethod
    def from_env(cls) -> "BankApiSettings":
        load_env()
        port = os.environ.get("VGB_PORT", "8000")
        return cls(
            url=os.environ.get("VGB_API_URL", f"http://127.0.0.1:{port}"),
            api_key=os.environ.get("VGB_API_KEY", "vgb-demo-key"),
        )
