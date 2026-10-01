FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
# meltano.yml installs the MeltanoLabs plugins from GitHub.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY . /workspace
WORKDIR /workspace/salesforce-netsuite-customer-sync
ENV PDT_PROJECT=/workspace NO_COLOR=1
RUN uv sync --script run.py
RUN uv sync --script scripts/sf-refresh-token-keyvault.py
RUN uv run --script run.py --install-only
ENTRYPOINT ["uv", "run", "--script", "run.py"]
