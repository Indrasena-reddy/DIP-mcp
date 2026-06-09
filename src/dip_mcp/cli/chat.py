"""Interactive MCP tool-calling chat CLI for the DIP parliamentary analyser.

Provides a REPL that sends user messages to Groq with the two MCP tool schemas.
When the model requests a tool, the call is routed through the FastMCP server
instance (mcp.call_tool) so it genuinely flows through the MCP protocol layer
rather than bypassing it with direct function calls.
"""

# Standard library
import asyncio
import json
import logging
from typing import Any

# Third-party
import groq
from mcp.types import TextContent
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Local
from dip_mcp.config import get_logger, settings
from dip_mcp.llm.groq_client import CHAT_SYSTEM_PROMPT, GroqClient
from dip_mcp.mcp.server import mcp

log: logging.Logger = get_logger(__name__)

EXIT_COMMANDS: frozenset[str] = frozenset({"exit", "quit", "q", "bye"})

WELCOME_MESSAGE: str = (
    "[bold]Welcome to the DIP Parliamentary Chat Assistant[/bold]\n\n"
    "Ask questions about the German Bundestag — Fraktion distributions, "
    "politician biographies, and parliamentary group membership.\n\n"
    "[dim]Commands: exit · quit · q · bye — or press Ctrl+C to quit.[/dim]"
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_fraktion_distribution",
            "description": (
                "Fetch the parliamentary group (Fraktion) distribution for a given Wahlperiode "
                "(election period). Returns the percentage and count of politicians per Fraktion. "
                "Use this for questions about group distribution or election period statistics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wahlperiode": {
                        "type": "integer",
                        "description": (
                            "The election period number, e.g. 20 for the 20th Wahlperiode (2021-2025)."
                        ),
                    }
                },
                "required": ["wahlperiode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_person_info",
            "description": (
                "Look up biographical and parliamentary information for a specific politician "
                "by name. Returns Fraktion membership, biographical data, and election periods. "
                "Use this for questions about specific individuals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Full or partial name of the politician to search for.",
                    },
                    "wahlperiode": {
                        "type": "integer",
                        "description": "Election period to search within. Defaults to 20.",
                    },
                },
                "required": ["name"],
            },
        },
    },
]


async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    """Execute a tool via the MCP server and return its result as a JSON string.

    Routes the call through FastMCP.call_tool so it genuinely flows through
    the MCP protocol layer. Handles both dict and ContentBlock return types.

    Args:
        name: Tool name registered on the MCP server.
        args: Parsed keyword arguments for the tool.

    Returns:
        JSON-encoded result string, or a JSON error object on failure.
    """
    log.info("MCP tool call: %s with args %s", name, list(args.keys()))
    result = await mcp.call_tool(name, args)

    # FastMCP.call_tool returns (Sequence[ContentBlock], raw_dict) tuple.
    # Take the ContentBlock list (index 0) and extract text from each block.
    content_blocks = result[0] if isinstance(result, tuple) else result
    if isinstance(content_blocks, dict):
        return json.dumps(content_blocks)

    texts = [block.text for block in content_blocks if isinstance(block, TextContent)]
    combined = "".join(texts)
    return combined if combined else json.dumps({"error": f"No result from tool '{name}'"})


def chat_command() -> None:
    """Start the interactive MCP tool-calling chat session."""
    asyncio.run(run_chat())


async def run_chat() -> None:
    """Run the interactive chat REPL with Groq tool-calling.

    Maintains a conversation history across turns. When the model requests a
    tool call, the corresponding function from tools.py is invoked directly and
    the result is appended to the history before the model produces its final
    answer. Handles groq.APIError per turn (session continues) and
    KeyboardInterrupt at the top level (session exits cleanly).
    """
    log.info("Chat session started")
    console = Console()
    console.print(
        Panel(WELCOME_MESSAGE, title="DIP Parliamentary Assistant", border_style="blue")
    )

    conversation_history: list[dict[str, Any]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT}
    ]

    try:
        async with GroqClient(settings) as llm:
            while True:
                try:
                    user_input = console.input("\n[bold cyan]You:[/bold cyan] ")
                except EOFError:
                    break

                stripped = user_input.strip()
                if not stripped:
                    continue
                if stripped.lower() in EXIT_COMMANDS:
                    log.info("Chat session ended by user command")
                    console.print("[dim]Auf Wiedersehen![/dim]")
                    break

                log.info("LLM called: processing user turn (%d chars)", len(stripped))
                conversation_history.append({"role": "user", "content": stripped})

                try:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                        transient=True,
                    ) as progress:
                        progress.add_task("Thinking...", total=None)
                        response = await llm.chat_with_tools(
                            conversation_history, TOOL_SCHEMAS
                        )

                    choice = response.choices[0]

                    if choice.finish_reason == "tool_calls":
                        tool_calls = choice.message.tool_calls or []

                        # Append assistant's tool-request message to history
                        conversation_history.append(
                            {
                                "role": "assistant",
                                "content": choice.message.content or "",
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "type": "function",
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments,
                                        },
                                    }
                                    for tc in tool_calls
                                ],
                            }
                        )

                        # Execute each tool and feed results back
                        for tc in tool_calls:
                            console.print(
                                f"[dim]  → calling [cyan]{tc.function.name}[/cyan]...[/dim]"
                            )
                            with Progress(
                                SpinnerColumn(),
                                TextColumn("[progress.description]{task.description}"),
                                console=console,
                                transient=True,
                            ) as prog:
                                prog.add_task("Fetching data...", total=None)
                                tool_args: dict[str, Any] = json.loads(
                                    tc.function.arguments
                                )
                                result_str = await _dispatch_tool(
                                    tc.function.name, tool_args
                                )

                            conversation_history.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tc.id,
                                    "content": result_str,
                                }
                            )

                        # Get the final answer after tool results are available
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            console=console,
                            transient=True,
                        ) as prog:
                            prog.add_task("Composing answer...", total=None)
                            final = await llm.chat_with_tools(
                                conversation_history, TOOL_SCHEMAS
                            )

                        answer = final.choices[0].message.content or ""
                    else:
                        answer = choice.message.content or ""

                    conversation_history.append(
                        {"role": "assistant", "content": answer}
                    )
                    console.print(
                        Panel(answer, title="Assistant", border_style="green")
                    )

                except groq.APIError as exc:
                    log.error("Groq API error during chat turn: %s", exc)
                    console.print(
                        Panel(
                            f"[red]API Error:[/red] {exc}\n\n"
                            "The session is still active — type your next question or 'exit' to quit.",
                            title="Error",
                            border_style="red",
                        )
                    )

    except KeyboardInterrupt:
        log.info("Chat session interrupted by user (KeyboardInterrupt)")
        console.print("\n[dim]Auf Wiedersehen![/dim]")
