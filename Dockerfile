FROM python:3.11-slim AS builder

RUN pip install pipx --quiet \
    && pipx install poetry

ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --without dev --no-root --no-interaction

COPY src/ ./src/

RUN poetry install --without dev --no-interaction


FROM python:3.11-slim AS runtime

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app/src ./src/

RUN useradd --create-home --shell /bin/bash appuser
USER appuser

CMD ["python", "-m", "dip_mcp.cli.app"]
