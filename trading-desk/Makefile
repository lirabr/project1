# Trading desk — common tasks. Requires: uv (https://astral.sh/uv)
# All commands are laptop-local and paper-only. Nothing here contacts a live broker.

.PHONY: help setup setup-graph test test-fast lint fmt clean \
        download features backtest compare cycle reflect graph

help:
	@echo "setup        install runtime + dev deps"
	@echo "setup-graph  also install the optional LangGraph extra"
	@echo "test         run the full pytest suite"
	@echo "lint         ruff check src + tests"
	@echo "fmt          ruff format"
	@echo "download     fetch OHLCV bars into data/raw"
	@echo "features     build the feature panel"
	@echo "backtest     walk-forward all strategies with costs"
	@echo "compare      print tear sheets side by side"
	@echo "cycle        run one paper-desk cycle (intents only)"
	@echo "reflect      write lessons for submitted paper fills"
	@echo "graph        run the LangGraph desk (needs setup-graph)"

setup:
	uv sync --locked --extra dev

setup-graph:
	uv sync --locked --extra dev --extra graph

test:
	uv run --locked --extra dev --extra graph pytest -q

test-fast:
	uv run --locked --extra dev pytest -q -k "not langgraph"

lint:
	uv run --locked --extra dev ruff check src tests

fmt:
	uv run --locked --extra dev ruff format src tests

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__

download:
	uv run --no-sync desk-research download

features:
	uv run --no-sync desk-research features

backtest:
	uv run --no-sync desk-research backtest

compare:
	uv run --no-sync desk-research compare

cycle:
	uv run --no-sync desk-research cycle

reflect:
	uv run --no-sync desk-research reflect

graph:
	uv run --locked --extra graph desk-research graph --thread desk-$$(date -u +%Y%m%dT%H%M%SZ)
