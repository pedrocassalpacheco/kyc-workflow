"""Run the MCP server, or list its tools.

    python -m kyc_workflow.mcp_server                      serve over stdio
    python -m kyc_workflow.mcp_server --transport http     serve over streamable HTTP at /mcp
    python -m kyc_workflow.mcp_server --list               print the tools and exit
    python -m kyc_workflow.mcp_server --check              connect to a running http server and count its tools

The bank's HTTP API must be running for tool calls (make bank-api). Its
address and key come from VGB_API_URL and VGB_API_KEY (defaults
http://127.0.0.1:8000 and vgb-demo-key). The HTTP transport listens on
127.0.0.1:MCP_PORT (default 8001).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from kyc_workflow.config import BankApiSettings
from kyc_workflow.mcp_server.http_client import BankApi
from kyc_workflow.mcp_server.server import build_server

DEFAULT_MCP_PORT = 8001


async def _describe(server) -> None:
    print(f"{server.name}")
    for tool in await server.list_tools():
        params = ", ".join(tool.input_schema.get("properties", {}).keys())
        first_line = (tool.description or "").strip().splitlines()[0]
        print(f"  {tool.name}({params})")
        print(f"      {first_line}")


def _check(port: int) -> int:
    """Client-side probe of a running http transport. Retries briefly so it can
    run right after the server was started."""
    import time

    from mcp.client import Client

    url = f"http://127.0.0.1:{port}/mcp"

    async def probe() -> int:
        async with Client(url) as client:
            return len((await client.list_tools()).tools)

    last: Exception | None = None
    for _ in range(20):
        try:
            count = asyncio.run(probe())
            print(f"mcp       up    {count} tools at {url}")
            return 0
        except Exception as err:  # connection refused while starting, mostly
            last = err
            time.sleep(0.25)
    print(f"mcp       DOWN  {url}: {type(last).__name__}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m kyc_workflow.mcp_server", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list the tools, then exit")
    parser.add_argument("--check", action="store_true",
                        help="connect to the http transport on --port as a client, print the tool count, exit")
    parser.add_argument("--transport", choices=("stdio", "http"), default="stdio",
                        help="stdio for an MCP host that spawns the process; http for a long-running service")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", DEFAULT_MCP_PORT)),
                        help="port for the http transport (default MCP_PORT or 8001)")
    args = parser.parse_args(argv)

    if args.check:
        return _check(args.port)

    settings = BankApiSettings.from_env()
    server = build_server(BankApi(settings.url, settings.api_key))

    if args.list:
        asyncio.run(_describe(server))
        return 0

    if args.transport == "http":
        print(f"{server.name}: MCP over streamable HTTP at http://127.0.0.1:{args.port}/mcp, "
              f"delegating to {settings.url}", file=sys.stderr, flush=True)
        server.run(transport="streamable-http", host="127.0.0.1", port=args.port)
    else:
        print(f"{server.name}: MCP over stdio, delegating to {settings.url}", file=sys.stderr, flush=True)
        server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
