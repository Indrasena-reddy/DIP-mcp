"""Ask one question to the DIP parliamentary assistant and print the answer."""

import asyncio
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import logging
logging.disable(logging.CRITICAL)  # suppress httpx / tenacity INFO logs

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from dip_mcp.cli.chat import TOOL_SCHEMAS, _dispatch_tool
from dip_mcp.config import settings
from dip_mcp.llm.groq_client import CHAT_SYSTEM_PROMPT, GroqClient

QUESTION = "Wie ist die Fraktionsverteilung in der 20. Wahlperiode?"


async def run() -> None:
    console = Console()

    console.print(Panel(f"[bold cyan]You:[/bold cyan] {QUESTION}", border_style="cyan"))

    conversation: list[dict] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": QUESTION},
    ]

    async with GroqClient(settings) as llm:
        with Progress(SpinnerColumn(), TextColumn("Thinking..."),
                      console=console, transient=True) as prog:
            prog.add_task("", total=None)
            response = await llm.chat_with_tools(conversation, TOOL_SCHEMAS)

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls or []

            conversation.append({
                "role": "assistant",
                "content": choice.message.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                console.print(f"[dim]  → using tool: [cyan]{tc.function.name}[/cyan] ...[/dim]")
                args: dict = json.loads(tc.function.arguments)

                with Progress(SpinnerColumn(), TextColumn("Fetching data from DIP API..."),
                              console=console, transient=True) as prog:
                    prog.add_task("", total=None)
                    result_str = await _dispatch_tool(tc.function.name, args)

                conversation.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            with Progress(SpinnerColumn(), TextColumn("Composing answer..."),
                          console=console, transient=True) as prog:
                prog.add_task("", total=None)
                final = await llm.chat_with_tools(conversation, TOOL_SCHEMAS)

            answer = final.choices[0].message.content or ""
        else:
            answer = choice.message.content or ""

    console.print(Panel(answer, title="[bold green]Assistant[/bold green]", border_style="green"))


if __name__ == "__main__":
    asyncio.run(run())
