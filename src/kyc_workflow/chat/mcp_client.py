"""MCP client for the vgb-records server.

Nothing about the tools is known here: the client asks the server for its
tool list at connect time and forwards every call. Connects to:

  - a URL: the MCP server already running over streamable HTTP (`make up`).
    This is the default, from MCP_URL.
  - "stdio": spawn `python -m kyc_workflow.mcp_server` and talk over pipes.
  - "inproc": build the server inside this process and use the SDK's memory
    transport. For tests only; it still goes through the MCP protocol.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from kyc_workflow.config import BankApiSettings, McpSettings
from kyc_workflow.gateway import ToolDef


@dataclass
class ToolResult:
    text: str
    is_error: bool
    request_ids: list[str]


class RecordsClient:
    def __init__(self, target: str | None = None, bank_api: BankApiSettings | None = None) -> None:
        """`target` is the URL of a running MCP server (default MCP_URL), "stdio", or "inproc"."""
        self.target = target or McpSettings.from_env().url
        self._bank_api = bank_api or BankApiSettings.from_env()
        self._client: Client | None = None
        self.tools: list[ToolDef] = []
        self.instructions: str = ""

    async def __aenter__(self) -> "RecordsClient":
        if self._client is not None:
            raise RuntimeError("RecordsClient is already connected; enter it once")
        if self.target == "inproc":
            from kyc_workflow.mcp_server import BankApi, build_server  # tests only; see module docstring

            server = build_server(BankApi(self._bank_api.url, self._bank_api.api_key))
            self._client = Client(server)
        elif self.target == "stdio":
            self._client = Client(StdioServerParameters(
                command=sys.executable, args=["-m", "kyc_workflow.mcp_server"],
                env={"VGB_API_URL": self._bank_api.url, "VGB_API_KEY": self._bank_api.api_key},
            ))
        else:
            self._client = Client(self.target)
        await self._client.__aenter__()
        listed = await self._client.list_tools()
        self.tools = [ToolDef(name=t.name, description=t.description or "", input_schema=t.input_schema) for t in listed.tools]
        self.instructions = self._client.instructions or ""
        return self

    async def __aexit__(self, *exc) -> None:
        if self._client is not None:
            client, self._client = self._client, None
            await client.__aexit__(*exc)

    @property
    def names(self) -> set[str]:
        return {t.name for t in self.tools}

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        assert self._client is not None, "use `async with`"
        result = await self._client.call_tool(name, arguments)
        if result.structured_content:
            payload = result.structured_content
            text = json.dumps(payload, indent=1)
        else:
            text = "\n".join(getattr(b, "text", "") for b in result.content)
            try:
                payload = json.loads(text)
            except (ValueError, TypeError):
                payload = {}
        request_ids = list((payload.get("source") or {}).get("request_ids", [])) if isinstance(payload, dict) else []
        return ToolResult(text=text, is_error=bool(result.is_error), request_ids=request_ids)
