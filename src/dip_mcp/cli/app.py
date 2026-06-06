"""CLI entrypoint for dip-mcp.

Registers all commands (analyse, serve, chat) with the root Typer application
and provides the package entrypoint used by ``poetry run dip-mcp``.
"""

# Third-party
import typer

# Local
from dip_mcp.cli.analyse import analyse_command
from dip_mcp.cli.chat import chat_command
from dip_mcp.mcp.server import run_server

app = typer.Typer(
    name="dip-mcp",
    help="Parliamentary data analyser powered by MCP and Groq.",
)

app.command("analyse")(analyse_command)
app.command("chat")(chat_command)


@app.command("serve")
def serve_command() -> None:
    """Start the MCP server using stdio transport."""
    run_server()


if __name__ == "__main__":
    app()
