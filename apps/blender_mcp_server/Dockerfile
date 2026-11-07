FROM python:3.11-slim-bookworm

ARG BLENDER_VERSION=5.2.3

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl xz-utils \
    libdbus-1-3 libegl1 libfontconfig1 libfreetype6 libgl1 libglib2.0-0 \
    libgomp1 libharfbuzz0b libsm6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 \
    libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxinerama1 libxkbcommon0 \
    libxrandr2 libxrender1 libxss1 libxt6 libxxf86vm1 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eu; \
    base="https://download.blender.org/release/Blender5.2"; \
    archive="blender-${BLENDER_VERSION}-linux-x64.tar.xz"; \
    curl --fail --location --silent --show-error "$base/$archive" -o /tmp/blender.tar.xz; \
    curl --fail --location --silent --show-error "$base/blender-${BLENDER_VERSION}.sha256" -o /tmp/blender.sha256; \
    grep "$archive" /tmp/blender.sha256 | sha256sum --check --status -; \
    mkdir -p /opt/blender; \
    tar --extract --xz --file /tmp/blender.tar.xz --directory /opt/blender --strip-components=1; \
    rm /tmp/blender.tar.xz /tmp/blender.sha256

WORKDIR /srv/rga
COPY pyproject.toml README.md LICENSE ./
COPY packages ./packages
COPY apps ./apps
COPY tools/smoke_blender_extension.py ./tools/smoke_blender_extension.py
COPY examples/worlds/mistral-coast-lookout-v2/scene-recipe.json ./examples/worlds/mistral-coast-lookout-v2/scene-recipe.json
RUN python -m pip install --no-cache-dir . \
    && mkdir -p /var/lib/rga/artifacts \
    && groupadd --system --gid 10001 rga \
    && useradd --system --uid 10001 --gid 10001 --home-dir /var/lib/rga rga \
    && chown -R 10001:10001 /var/lib/rga

ENV BLENDER_EXECUTABLE=/opt/blender/blender \
    BLENDER_MCP_HOST=0.0.0.0 \
    BLENDER_MCP_PORT=8788 \
    BLENDER_MCP_OUTPUT_DIR=/var/lib/rga/artifacts \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
EXPOSE 8788
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8788/healthz', timeout=3).read()"]
CMD ["python", "apps/blender_mcp_server/server.py"]
