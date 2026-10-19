"""Serve the UI.

    python -m kyc_workflow.ui [--port 8002] [--no-guard-llm]

Needs the bank API and the MCP server running (`make up` starts all three).
"""

from __future__ import annotations

import argparse
import logging
import os

import uvicorn

from kyc_workflow.ui.app import UIState, create_app

DEFAULT_UI_PORT = 8002


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kyc_workflow.ui", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=int(os.environ.get("UI_PORT", DEFAULT_UI_PORT)))
    parser.add_argument("--no-guard-llm", action="store_true", help="regex guardrails only in the chat")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)

    app = create_app(UIState(use_guard_llm=not args.no_guard_llm))
    print(f"kyc-workflow ui at http://127.0.0.1:{args.port}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
