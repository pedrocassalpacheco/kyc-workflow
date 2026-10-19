"""The MCP server over the bank's reference data API.

    from kyc_workflow.mcp_server import BankApi, build_server

Run it over stdio with `python -m kyc_workflow.mcp_server`.
"""

from kyc_workflow.mcp_server.http_client import BankApi, BankApiError, BankApiUnavailable
from kyc_workflow.mcp_server.server import HIDDEN_DATASETS, SERVER_NAME, build_server

__all__ = ["BankApi", "BankApiError", "BankApiUnavailable", "HIDDEN_DATASETS", "SERVER_NAME", "build_server"]
