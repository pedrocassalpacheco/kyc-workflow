"""Terminal chat over the bank's records through the MCP server.

    uv run main.py chat [--model M] [--guard-model M | --no-guard-llm] [--mcp URL|stdio] [--analyst ID] [-v]

Talks to the vgb-records MCP server started by `make up` (MCP_URL).

Type a question; /quit ends the session, /log shows the audit log path.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from contextlib import AsyncExitStack

from kyc_workflow.chat.examples import EXAMPLE_QUESTIONS
from kyc_workflow.chat.guardrails import Guardrails
from kyc_workflow.chat.mcp_client import RecordsClient
from kyc_workflow.chat.session import ChatSession, make_intent_classifier
from kyc_workflow.config import McpSettings, Settings
from kyc_workflow.gateway import HeliosGateway

BANNER = r"""
 __     ______ ____    ____                        _
 \ \   / / ___| __ )  |  _ \ ___  ___ ___  _ __ __| |___
  \ \ / / |  _|  _ \  | |_) / _ \/ __/ _ \| '__/ _` / __|
   \ V /| |_| | |_) | |  _ <  __/ (_| (_) | | | (_| \__ \
    \_/  \____|____/  |_| \_\___|\___\___/|_|  \__,_|___/
  Veridian Global Bank  ·  KYC records chat  ·  read-only, every step logged
"""

EXAMPLES = """\
  Ask about a customer's records. The assistant reads the five record systems
  through the MCP server and cites what it found. It will not rate, decide,
  close or draft; a named analyst does that.

  Try, for example:
{examples}

  Commands: /quit to end, /log for the audit log path. Ctrl+C during an
  answer cancels that turn; Ctrl+C at the prompt ends the session.
"""


def add_chat_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--model", help="model for the conversation (default KYC_MODEL from .env)")
    parser.add_argument("--guard-model", default=None,
                        help="model for the intent guardrail (default KYC_GUARD_MODEL from .env)")
    parser.add_argument("--no-guard-llm", action="store_true", help="regex guardrails only, no intent classifier")
    parser.add_argument("--mcp", default=None,
                        help="URL of the running MCP server (default MCP_URL, %s), or stdio to spawn one"
                             % McpSettings.from_env().url)
    parser.add_argument("--analyst", default="ANALYST", help="analyst id carried as metadata on every model call")
    parser.add_argument("--max-tool-rounds", type=int, default=8)
    parser.add_argument("-v", "--verbose", action="store_true", help="DEBUG: add full texts and tool previews to the log")
    parser.add_argument("-q", "--quiet", action="store_true", help="WARNING only: hide the step-by-step narration")


async def run_chat(args: argparse.Namespace) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stderr)
    chat_level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.getLogger("kyc_workflow.chat").setLevel(chat_level)
    for name in ("httpx", "httpx2"):
        logging.getLogger(name).setLevel(logging.WARNING)

    from kyc_workflow.gateway import AnthropicBackend

    settings = Settings.from_env()
    model = args.model or settings.model
    guard_model = args.guard_model or settings.guard_model
    settings = settings.with_model(guard_model).with_model(model)
    gateway = HeliosGateway(AnthropicBackend(), settings)

    async with AsyncExitStack() as stack:
        try:
            records = await stack.enter_async_context(RecordsClient(args.mcp))  # entered exactly once, closed on exit
        except Exception as err:
            target = args.mcp or McpSettings.from_env().url
            print(f"cannot reach the MCP server at {target}: {type(err).__name__}. Run `make up` first.", file=sys.stderr)
            return 1
        classifier = None
        if not args.no_guard_llm:
            classifier = make_intent_classifier(gateway, settings, guard_model, args.analyst, "CHAT-GUARD")
        guardrails = Guardrails(allowed_tools=records.names, max_tool_rounds=args.max_tool_rounds,
                                intent_classifier=classifier)
        session = ChatSession(gateway, records, settings, model=model, analyst_id=args.analyst, guardrails=guardrails)

        print(BANNER)
        print(f"  model {model}  |  guard {'regex + ' + guard_model if classifier else 'regex only'}  |  "
              f"mcp {records.target}  |  {len(records.tools)} tools")
        print(f"  audit log  {session.log_path}\n")
        print(EXAMPLES.format(examples="\n".join(f"    {q}" for q in EXAMPLE_QUESTIONS)))

        loop = asyncio.get_running_loop()
        while True:
            try:
                line = input("you> ").strip()  # default SIGINT handling here: Ctrl+C ends the session
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line in ("/quit", "/exit", "/q"):
                break
            if line == "/log":
                print(session.log_path)
                continue
            turn = asyncio.ensure_future(session.ask(line))
            loop.add_signal_handler(signal.SIGINT, turn.cancel)  # Ctrl+C cancels this turn only
            try:
                reply = await turn
            except asyncio.CancelledError:
                print("\n  [turn cancelled; nothing from it was kept]\n")
                continue
            finally:
                loop.remove_signal_handler(signal.SIGINT)
                signal.signal(signal.SIGINT, signal.default_int_handler)
            print(f"\nassistant> {reply}\n")
    tot = session.totals
    print(f"session ended after {session.turn} turn(s): {tot['model_calls']} model calls, {tot['tool_calls']} tool calls, "
          f"tokens in={tot['input_tokens']} out={tot['output_tokens']}")
    print(f"audit log: {session.log_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_chat_args(parser)
    return asyncio.run(run_chat(parser.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
