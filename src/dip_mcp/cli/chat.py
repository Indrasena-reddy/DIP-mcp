"""Interactive MCP tool-calling chat CLI for the DIP parliamentary analyser.

Provides a REPL that sends user messages to Groq with the three MCP tool schemas.
When the model requests a tool, the underlying function from tools.py is called
directly (in-process — no MCP transport overhead) and the result is fed back for
a final answer.
"""

# Standard library
import asyncio
import json
from typing import Any

# Third-party
import groq
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Local
from dip_mcp.config import settings
from dip_mcp.llm.groq_client import CHAT_SYSTEM_PROMPT, GroqClient
from dip_mcp.mcp.tools import (
    fetch_fraktion_distribution,
    fetch_fraktionen_list,
    fetch_person_info,
)

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
    {
        "type": "function",
        "function": {
            "name": "list_fraktionen",
            "description": (
                "List all parliamentary groups (Fraktionen) registered for a given Wahlperiode. "
                "Use this for questions about which parties are represented."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wahlperiode": {
                        "type": "integer",
                        "description": "The election period number. Defaults to 20.",
                    }
                },
                "required": [],
            },
        },
    },
]


async def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    """Execute the named MCP tool and return its result as a JSON string.

    Args:
        name: Tool name matching one of the three registered MCP tools.
        args: Parsed keyword arguments for the tool function.

    Returns:
        JSON-encoded result string, or a JSON error object for unknown tools.
    """
    if name == "get_fraktion_distribution":
        wahlperiode = int(args.get("wahlperiode", 20))
        report = await fetch_fraktion_distribution(wahlperiode)
        return json.dumps(report.model_dump())
    if name == "get_person_info":
        person_name = str(args.get("name", ""))
        wahlperiode = int(args.get("wahlperiode", 20))
        return json.dumps(await fetch_person_info(person_name, wahlperiode))
    if name == "list_fraktionen":
        wahlperiode = int(args.get("wahlperiode", 20))
        return json.dumps(await fetch_fraktionen_list(wahlperiode))
    return json.dumps({"error": f"Unknown tool: '{name}'"})


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
                    console.print("[dim]Auf Wiedersehen![/dim]")
                    break

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
                    console.print(
                        Panel(
                            f"[red]API Error:[/red] {exc}\n\n"
                            "The session is still active — type your next question or 'exit' to quit.",
                            title="Error",
                            border_style="red",
                        )
                    )

    except KeyboardInterrupt:
        console.print("\n[dim]Auf Wiedersehen![/dim]")
