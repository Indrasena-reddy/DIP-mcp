# DIP Parliamentary Analyser

A production-quality proof-of-concept that connects to the **German Bundestag DIP API**, analyses Fraktion (parliamentary group) membership distribution, and exposes the analysis through an **MCP (Model Context Protocol)** server with **Groq LLM** tool-calling.

Built for the PwC AIMoS Coding Challenge.

---

## Quickstart (no install required)

```bash
# 1. Create a .env file with your API keys
cp .env.example .env   # then edit .env

# 2. Pull and run the pre-built image from GHCR
docker run --env-file .env ghcr.io/indrasena-reddy/dip-mcp:latest
```

That's it — no Python, no Poetry, no build step.

---

## Project Overview

The system fetches real politician data from the official German Bundestag open-data API, determines each politician's Fraktion membership, computes percentage distribution across all parliamentary groups, and uses a large language model to generate a human-readable German-language summary.

The architecture has four modes of interaction:

- **`BundesBot UI`** — a Streamlit chat interface for asking natural language questions about the Bundestag
- **`analyse`** — a one-shot CLI command that fetches data, computes distribution, and generates an LLM summary
- **`serve`** — exposes MCP tools over stdio transport so any MCP-compatible client (e.g. Claude Desktop) can call them
- **`chat`** — an interactive REPL where the LLM automatically selects and calls the right tool based on your natural language question

**Key technologies:** Python 3.11, FastMCP, Groq (`llama-3.3-70b-versatile`), httpx, Pydantic v2, Rich, Typer, Poetry, Docker.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.11+ | 3.12 recommended for Docker |
| Poetry | 1.8+ | Dependency and packaging manager |
| Docker | 24+ | Optional — for containerised runs |
| DIP API key | — | German Bundestag open-data portal |
| Groq API key | — | Free at console.groq.com |

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Indrasena-reddy/DIP-mcp.git
cd DIP-mcp

# 2. Copy the environment file and fill in your API keys
cp .env.example .env

# 3. Install dependencies
poetry install
```

Open `.env` in any text editor and replace the placeholder values:

```
DIP_API_KEY=your_dip_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

---

## Configuration

All configuration is read from environment variables (or the `.env` file). Never commit `.env` to version control — it is listed in `.gitignore`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `DIP_API_KEY` | Yes | — | German Bundestag DIP API key |
| `GROQ_API_KEY` | Yes | — | Groq LLM API key |
| `DIP_API_BASE_URL` | No | `https://search.dip.bundestag.de/api/v1` | DIP API base URL |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model identifier |
| `LOG_LEVEL` | No | `INFO` | Python logging level |
| `REQUEST_TIMEOUT_SECONDS` | No | `30` | HTTP request timeout |
| `MAX_CONCURRENT_REQUESTS` | No | `5` | Max parallel DIP API requests |

**Where to get your keys:**
- **DIP API key:** Register at [dip.bundestag.de](https://dip.bundestag.de) or use the public demo key available in the portal documentation.
- **Groq API key:** Create a free account at [console.groq.com](https://console.groq.com) and generate an API key under *API Keys*.

---

## Usage

### BundesBot UI — Streamlit chat interface

```bash
poetry run streamlit run frontend/app.py
```

Opens the chat UI at **http://localhost:8501**. Ask questions in natural language (German or English) — BundesBot selects the right MCP tool, fetches live data from the DIP API, and returns a formatted answer.

Example questions:
- *Fraktion split in WP 20?*
- *Who is Friedrich Merz?*
- *How many MdBs in WP 20?*

The UI runs on port 8501 by default. To change the port:

```bash
poetry run streamlit run frontend/app.py --server.port 8502
```

---

### Analyse — fetch distribution and generate LLM summary

```bash
poetry run dip-mcp analyse --wahlperiode 20
```

Fetches all politicians for Wahlperiode 20 (2021–2025), computes the Fraktion distribution table, and generates a German-language summary via Groq. The `--wahlperiode` / `-w` flag accepts any valid election period number.

```bash
# Example: analyse Wahlperiode 19 (2017–2021)
poetry run dip-mcp analyse --wahlperiode 19
```

### Serve — start the MCP server

```bash
poetry run dip-mcp serve
```

Starts the MCP server on stdio transport. Connect any MCP-compatible client (e.g. Claude Desktop, an MCP inspector) to this process. Two tools are registered:

| Tool | Description |
|---|---|
| `get_fraktion_distribution` | Fraktion distribution for a given Wahlperiode |
| `get_person_info` | Biographical and parliamentary data for a politician by name |

### Chat — interactive natural language assistant

```bash
poetry run dip-mcp chat
```

Starts an interactive REPL. Ask questions in natural language (German or English). The LLM automatically selects the correct tool, fetches live data from the DIP API, and returns a formatted answer.

Example questions:
- *Wie ist die Fraktionsverteilung in der 20. Wahlperiode?*
- *Wer ist Friedrich Merz?*
- *Which parties are in the Bundestag?*

Type `exit`, `quit`, or press `Ctrl+C` to quit.

---

## Docker

### Pre-built image (recommended)

```bash
# Run the default analyse command (Wahlperiode 20)
docker run --env-file .env ghcr.io/indrasena-reddy/dip-mcp:latest

# Run with a specific Wahlperiode
docker run --env-file .env ghcr.io/indrasena-reddy/dip-mcp:latest analyse --wahlperiode 19

# Interactive chat (requires a TTY)
docker run --env-file .env -it ghcr.io/indrasena-reddy/dip-mcp:latest chat

# Streamlit UI
docker run --env-file .env -p 8501:8501 ghcr.io/indrasena-reddy/dip-mcp:latest streamlit
```

### Build locally

Ensure Docker Desktop is running, then:

```bash
# Build the image
docker build -t dip-mcp:latest .

# Run the analyse command (default)
docker run --env-file .env dip-mcp:latest

# Run with a specific Wahlperiode
docker run --env-file .env dip-mcp:latest analyse --wahlperiode 19
```

### Docker Compose

```bash
docker compose up
```

This builds the image and runs `analyse --wahlperiode 20` by default.

For the interactive chat, run with a TTY:

```bash
docker compose run --rm -it dip-mcp chat
```

---

## Development

### Install development dependencies

```bash
poetry install
```

### Quality gates

Run all checks before committing:

```bash
# Static type checking (strict mode)
poetry run mypy src/ --strict

# Linting and formatting
poetry run ruff check src/

# Docstring style
poetry run pydocstyle src/

# Security scan
poetry run bandit -r src/

# Tests
poetry run pytest tests/ -v
```

### Project structure

```
src/dip_mcp/
├── api/
│   ├── client.py       # Async DIP API client with pagination and retries
│   └── models.py       # Pydantic v2 data models
├── cli/
│   ├── app.py          # Typer root application and command registration
│   ├── analyse.py      # analyse command — end-to-end pipeline
│   └── chat.py         # chat command — interactive MCP tool-calling REPL
├── core/
│   └── analytics.py    # Fraktion counting and percentage calculation
├── llm/
│   └── groq_client.py  # Groq async client — summarisation and tool-calling
├── mcp/
│   ├── server.py       # FastMCP server with three registered tools
│   └── tools.py        # Business logic functions called by MCP tools
└── config.py           # Pydantic Settings — env var loading and validation
```

---

## Architecture

The system is organised into four independent layers:

**DIP API layer** (`api/`) — An async httpx client with cursor-based pagination, a tenacity retry decorator (retries only on 5xx server errors), and an anyio semaphore for bounded concurrency. Pydantic v2 validates every document returned by the API.

**Analytics layer** (`core/`) — Pure Python functions that count Fraktion membership using a `Counter`, calculate percentage shares, and build a validated `DistributionReport` model. No external dependencies.

**MCP layer** (`mcp/`) — A FastMCP server that exposes two tools over stdio transport. All tool calls — both from the chat REPL and from external MCP clients — are routed through `FastMCP.call_tool()`, so every invocation genuinely flows through the MCP protocol layer. Person data is cached in-process per Wahlperiode to avoid redundant API fetches.

**LLM layer** (`llm/`) — An async Groq client that supports two interaction patterns: (1) single-shot summarisation of a finished distribution report, and (2) multi-turn tool-calling where Groq selects which MCP tool to invoke and composes the final answer from the tool result.

### Data flow (chat mode)

```
User question
    → Groq (tool selection)          — first LLM call
    → _dispatch_tool()
    → FastMCP.call_tool()            — MCP protocol layer
    → tools.py (_get_persons cache)
        → DipApiClient → DIP API     — cursor-paginated fetch (first request only)
        → client-side WP filter      — keeps only members of requested period
    → analytics.py                   — WP-specific Fraktion distribution
    → Groq (answer composition)      — second LLM call
    → displayed to user
```

---

## Bonus: Interactive Chat

The `chat` command implements a full MCP tool-calling loop in a terminal REPL. The LLM receives your natural language question alongside the three tool schemas, autonomously decides which tool to invoke and with what arguments, receives the live DIP API result, and composes a final answer — all without any hardcoded routing logic.

```bash
poetry run dip-mcp chat
```

The session maintains full conversation history, so follow-up questions work naturally. Type `exit` or press `Ctrl+C` to quit.
