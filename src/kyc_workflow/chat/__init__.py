"""Chat over the bank's records through the MCP server, with our own guardrails.

Not part of the proof-of-concept deliverable (the evidence pack and the
check report). It exists to explore the data and to exercise the gateway,
the MCP server, the guardrails and the audit logging end to end.
"""

from kyc_workflow.chat.examples import EXAMPLE_QUESTIONS
from kyc_workflow.chat.guardrails import Guardrails, Intent, IntentResult, Verdict
from kyc_workflow.chat.mcp_client import RecordsClient, ToolResult
from kyc_workflow.chat.session import SYSTEM_PROMPT, ChatSession, make_intent_classifier

__all__ = ["ChatSession", "EXAMPLE_QUESTIONS", "Guardrails", "Intent", "IntentResult", "RecordsClient", "SYSTEM_PROMPT",
           "ToolResult", "Verdict", "make_intent_classifier"]
