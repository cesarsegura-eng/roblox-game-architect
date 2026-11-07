FROM rust:1.88-bookworm AS rojo-builder
RUN cargo install rojo --version 7.7.1 --locked

FROM python:3.11-slim-bookworm

WORKDIR /srv/rga
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps ./apps
COPY --from=rojo-builder /usr/local/cargo/bin/rojo /usr/local/bin/rojo
RUN python -m pip install --no-cache-dir . \
    && mkdir -p /var/lib/rga \
    && groupadd --system --gid 10002 rga \
    && useradd --system --uid 10002 --gid 10002 --home-dir /var/lib/rga rga \
    && chown -R 10002:10002 /var/lib/rga

ENV RGA_ROBLOX_MCP_HOST=0.0.0.0 \
    RGA_ROBLOX_MCP_PORT=8790 \
    RGA_ROBLOX_LEDGER=/var/lib/rga/validation.sqlite3 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10002:10002
EXPOSE 8790
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8790/healthz', timeout=3).read()"]
CMD ["python", "-m", "apps.roblox_mcp_server.server"]
