FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-cache --python 3.12

COPY certs* /certs/
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

CMD ["fastapi", "run", "app/main.py", "--port", "5009", "--host", "0.0.0.0"]
