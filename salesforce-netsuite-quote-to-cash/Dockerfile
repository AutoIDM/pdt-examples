FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
# meltano.yml installs plugins from git.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY . /workspace
WORKDIR /workspace/salesforce-netsuite-quote-to-cash
ENV PDT_PROJECT=/workspace NO_COLOR=1
RUN uv sync --script run.py
RUN uv run --script run.py --install-only
ENTRYPOINT ["uv", "run", "--script", "run.py"]
