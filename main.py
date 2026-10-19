"""Thin CLI for the KYC workflow prototype.

    uv run main.py ping [--model MODEL]   one structured call through Helios -> Claude
    uv run main.py chat [--model MODEL]   chat over the bank's records via the MCP server, with guardrails
    uv run main.py pack <review_id>       build the evidence pack for a review (--no-model for code-only)
"""

from __future__ import annotations

import argparse
import sys

from pydantic import BaseModel, Field

from kyc_workflow.config import Settings
from kyc_workflow.gateway import GatewayError, HeliosGateway, ModelRequest


class Ping(BaseModel):
    document_date: str = Field(description="Date the document is dated, as an ISO date YYYY-MM-DD")
    issuer: str = Field(description="Organisation that issued the document, as written")


def cmd_ping(args: argparse.Namespace) -> int:
    from kyc_workflow.gateway import AnthropicBackend

    settings = Settings.from_env()
    if args.model:
        settings = settings.with_model(args.model)
    gateway = HeliosGateway(AnthropicBackend(), settings)
    request = ModelRequest(
        case_id="PING",
        analyst_id="CLI",
        system="You extract fields from bank documents. Answer only with the fields requested.",
        user="Document:\nSTRAITS MARINE LOGISTICS PTE LTD\nEMPLOYMENT CONFIRMATION\nDated: 5 June 2026\n",
        output_schema=Ping,
        max_tokens=256,
    )
    try:
        resp = gateway.complete(request)
    except GatewayError as err:
        print(f"gateway error: {err}", file=sys.stderr)
        return 1
    print(f"model        {resp.model}")
    print(f"request id   {resp.request_id}")
    print(f"attempts     {resp.attempts}")
    print(f"latency      {resp.latency_ms:.0f} ms")
    print(f"tokens       in={resp.usage.input_tokens} out={resp.usage.output_tokens} "
          f"cache_read={resp.usage.cache_read_input_tokens} cache_write={resp.usage.cache_creation_input_tokens}")
    print(f"parsed       {resp.parsed}")
    print(f"metadata log {settings.audit_dir / 'helios_metadata.jsonl'}")
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    import asyncio
    import logging
    from pathlib import Path

    from kyc_workflow.chat.mcp_client import RecordsClient
    from kyc_workflow.workflow import build_pack, pack_markdown

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)
    settings = Settings.from_env()
    if args.model:
        settings = settings.with_model(args.model)
    gateway = None
    if not args.no_model:
        from kyc_workflow.gateway import AnthropicBackend

        gateway = HeliosGateway(AnthropicBackend(), settings)

    async def run():
        async with RecordsClient(args.mcp) as records:
            return await build_pack(args.review_id, records, gateway, settings=settings, model=args.model, use_model=not args.no_model)

    try:
        pack = asyncio.run(run())
    except Exception as err:
        print(f"pack failed: {type(err).__name__}: {err}", file=sys.stderr)
        return 1
    md = pack_markdown(pack)
    out_dir = Path(args.out) / pack.review_id.replace("/", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pack.json").write_text(pack.model_dump_json(indent=2))
    (out_dir / "pack.md").write_text(md)
    print(md)
    print(f"written {out_dir}/pack.json and pack.md", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    ping = sub.add_parser("ping", help="one structured call through the Helios gateway")
    ping.add_argument("--model", help="model to ask for (added to the allowlist for this run)")
    ping.set_defaults(func=cmd_ping)

    from kyc_workflow.chat.cli import add_chat_args, run_chat

    chat = sub.add_parser("chat", help="chat over the bank's records through the MCP server")
    add_chat_args(chat)
    chat.set_defaults(func=lambda a: __import__("asyncio").run(run_chat(a)))

    pack = sub.add_parser("pack", help="build the evidence pack for a review")
    pack.add_argument("review_id")
    pack.add_argument("--model", help="model for the reading steps (default KYC_MODEL)")
    pack.add_argument("--no-model", action="store_true", help="deterministic steps only")
    pack.add_argument("--mcp", default=None, help="MCP server URL (default MCP_URL)")
    pack.add_argument("--out", default="output", help="folder for pack.json and pack.md")
    pack.add_argument("-v", "--verbose", action="store_true")
    pack.set_defaults(func=cmd_pack)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
