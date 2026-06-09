"""Analyse command implementation for the DIP MCP CLI.

Runs the complete end-to-end pipeline: fetch DIP API data, compute Fraktion
distribution, generate a Groq LLM summary, and render results with Rich.
"""

# Standard library
import asyncio
import logging
from datetime import datetime
from typing import Annotated

# Third-party
import groq
import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Local
from dip_mcp.api.client import DipApiClient
from dip_mcp.config import get_logger, settings
from dip_mcp.core.analytics import build_distribution_report
from dip_mcp.llm.groq_client import GroqClient

DEFAULT_WAHLPERIODE: int = 20

log: logging.Logger = get_logger(__name__)


def analyse_command(
    wahlperiode: Annotated[
        int,
        typer.Option("--wahlperiode", "-w", help="Election period number to analyse"),
    ] = DEFAULT_WAHLPERIODE,
) -> None:
    """Fetch Fraktion distribution and generate an LLM summary.

    Args:
        wahlperiode: Election period number to analyse.
    """
    asyncio.run(run_analysis(wahlperiode))


async def run_analysis(wahlperiode: int) -> None:
    """Execute the end-to-end analysis pipeline and render results to the terminal.

    Fetches person data from the DIP API, computes Fraktion distribution,
    generates a German-language LLM summary via Groq, then renders a Rich table
    and summary panel. HTTP errors abort the pipeline; LLM errors show the table
    but skip the summary panel.

    Args:
        wahlperiode: Election period number to fetch and analyse.
    """
    log.info("Analysis pipeline started for Wahlperiode %d", wahlperiode)
    console = Console()

    console.print(
        Panel(
            f"[bold]DIP Parliamentary Analyser[/bold]\n"
            f"Wahlperiode: [cyan]{wahlperiode}[/cyan]\n"
            f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            title="DIP-MCP",
            border_style="blue",
        )
    )

    try:
        async with DipApiClient(settings) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                fetch_task = progress.add_task(
                    "Fetching persons from DIP API...", total=None
                )
                persons = await client.get_persons(wahlperiode)
                progress.update(
                    fetch_task,
                    description=f"[green]✓ Fetched {len(persons)} persons",
                )
        log.info("Fetched %d persons from DIP API", len(persons))
    except httpx.HTTPStatusError as exc:
        log.error("HTTP error fetching persons for Wahlperiode %d: %s", wahlperiode, exc)
        console.print(
            Panel(
                f"[red]HTTP {exc.response.status_code}:[/red] {exc.request.url}\n{exc}",
                title="API Error",
                border_style="red",
            )
        )
        raise typer.Exit(code=1) from exc

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        dist_task = progress.add_task(
            "Computing Fraktion distribution...", total=None
        )
        report = build_distribution_report(persons, wahlperiode)
        progress.update(dist_task, description="[green]✓ Distribution computed")
    log.info("Distribution computed: %d Fraktionen", len(report.distribution))

    table = Table(
        title=f"Fraktion Distribution — Wahlperiode {wahlperiode}",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Fraktion", style="cyan", no_wrap=True)
    table.add_column("Persons", justify="right")
    table.add_column("Percentage", justify="right")

    for entry in report.distribution:
        table.add_row(
            entry.fraktion_name,
            str(entry.person_count),
            f"{entry.percentage:.2f}%",
        )

    console.print(table)
    console.print(
        f"[dim]Total: {report.total_persons} persons "
        f"({report.unaffiliated_count} unaffiliated)[/dim]"
    )

    summary: str | None = None
    log.info("LLM called: generating distribution summary via Groq")
    try:
        async with GroqClient(settings) as llm:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                transient=True,
            ) as progress:
                llm_task = progress.add_task(
                    "Generating LLM summary...", total=None
                )
                summary = await llm.generate_distribution_summary(report)
                progress.update(llm_task, description="[green]✓ Summary generated")
        log.info("LLM summary generated successfully")
    except groq.APIError as exc:
        log.error("Groq API error during summary generation: %s", exc)
        console.print(
            f"[yellow]Warning:[/yellow] LLM summary unavailable — {exc}"
        )

    if summary:
        console.print(
            Panel(summary, title="AI Analysis", border_style="green")
        )
