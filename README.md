---
title: TradingAgents
emoji: 📈
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
---

<p align="center">
  <img src="assets/TauricResearch.png" style="width: 60%; height: auto;">
</p>

<div align="center" style="line-height: 1;">
  <a href="https://arxiv.org/abs/2412.20138" target="_blank"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2412.20138-B31B1B?logo=arxiv"/></a>
  <a href="https://discord.com/invite/hk9PGKShPK" target="_blank"><img alt="Discord" src="https://img.shields.io/badge/Discord-TradingResearch-7289da?logo=discord&logoColor=white&color=7289da"/></a>
  <a href="https://huggingface.co/spaces/bullcardo/tradingagents" target="_blank"><img alt="HF Spaces" src="https://img.shields.io/badge/%F0%9F%A4%97%20HF%20Spaces-My%20Live%20Demo%20(fork)-blue"/></a>
  <a href="https://x.com/TauricResearch" target="_blank"><img alt="X Follow" src="https://img.shields.io/badge/X-TauricResearch-white?logo=x&logoColor=white"/></a>
</div>

---

# TradingAgents: Multi-Agents LLM Financial Trading Framework

> Fork of [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
> (arXiv:2412.20138). Several contributions from this branch have been adopted upstream.
> This fork runs ahead of the upstream release cadence with additional features documented below.
>
> **[My live demo →](https://huggingface.co/spaces/bullcardo/tradingagents)** — deployed from this
> fork, includes the Options Analyst, real sentiment dataflows, persistent memory log, and Gradio
> web UI — none of which are in the upstream release.

TradingAgents deploys a team of specialized LLM agents — analysts, researchers, trader, risk
advisors, and a portfolio manager — that debate market conditions and produce a structured trading
decision (Strong Buy → Strong Sell) for any ticker and date.

---

## Architecture

```
  ┌──────────────────────────────────────────────────────────────────┐
  │                         Data Sources                              │
  │  ┌──────────┐  ┌────────────────┐  ┌────────────┐  ┌──────────┐  │
  │  │ yfinance │  │    Finnhub     │  │ SEC EDGAR  │  │  Reddit  │  │
  │  │(fallback)│  │  (primary)     │  │(8-K filings│  │ CNN F&G  │  │
  │  └──────────┘  └────────────────┘  └────────────┘  └──────────┘  │
  └──────────────────────────────────────────────────────────────────┘
         │                │                   │               │
         ▼                ▼                   ▼               ▼
  ┌──────────┐  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐
  │  Market  │  │    Options       │  │ Fundamentals │  │  Sentiment   │
  │ Analyst  │  │    Analyst       │  │   Analyst    │  │   Analyst    │
  │          │  │  Vol/OI skew     │  │ + consensus  │  │ Reddit+F&G   │
  │          │  │  short interest  │  │ + earnings ↑ │  │              │
  └────┬─────┘  └────────┬─────────┘  └──────┬───────┘  └──────┬───────┘
       └─────────────────┴────────────────────┴──────────────────┘
                                     │
                           ┌─────────▼───────────┐
                           │    Research Debate   │
                           │   Bull ↔ Bear        │
                           │   Research Manager   │ ← structured output
                           └─────────┬────────────┘
                                     │ investment_plan
                           ┌─────────▼───────────┐
                           │       Trader         │ ← structured output
                           └─────────┬────────────┘
                                     │ trader_investment_plan
                           ┌─────────▼───────────┐
                           │     Risk Debate      │
                           │  Aggr/Cons/Neutral   │
                           └─────────┬────────────┘
                                     │
                    ┌────────────────▼──────────────────────────────┐
                    │            Portfolio Manager                   │
                    │            structured output                   │
                    │            reads TradingMemoryLog              │
                    │   (5 same-ticker + 3 cross-ticker entries)     │
                    └────────────────┬──────────────────────────────┘
                                     │
                    ┌────────────────▼──────────────────────────────┐
                    │   Strong Buy / Buy / Hold / Sell / Strong Sell │
                    └────────────────┬───────────────────────────────┘
                                     │
                    ┌────────────────▼───────────────────────────────────────────────┐
                    │                   TradingMemoryLog                              │
                    │                                                                 │
                    │  RUN 1  →  [pending]  NVDA · 2024-05-10 · Buy                 │
                    │                                                                 │
                    │  RUN 2+    same ticker triggers auto-resolution:               │
                    │            · fetch actual return via yfinance                  │
                    │            · compute alpha vs SPY                              │
                    │            · LLM writes reflection                             │
                    │  →  [resolved]  NVDA · Buy · +8.3% · alpha +2.1% · 7d        │
                    │                                                                 │
                    │  Portfolio Manager reads on every run:                         │
                    │  5 same-ticker resolved entries + 3 cross-ticker reflections   │
                    └─────────────────────────────────────────────────────────────────┘
  Access layers
  ┌──────────────────┐   ┌──────────────────────────────────────────────────────┐
  │   CLI (Rich TUI) │   │  Gradio Web UI                                       │
  │   (upstream)     │   │  SSE streaming · localStorage · history panel        │
  └──────────────────┘   │  S3 memory sync · HF Spaces deployment               │
                         └──────────────────────────────────────────────────────┘
```

---

## Contributions (this fork)

### Persistent decision memory with deferred return resolution *(design merged upstream — [PR #579](https://github.com/TauricResearch/TradingAgents/pull/579))*
Replaced the original BM25 memory — effectively dead code between runs — with `TradingMemoryLog`:
an append-only markdown log stored at `~/.tradingagents/memory/trading_memory.md`. After each run
a pending entry is written. Five or more trading days later, the next same-ticker run automatically
resolves it: fetches actual yfinance returns, computes alpha vs SPY, and writes an LLM-generated
reflection. The Portfolio Manager receives the 5 most-recent same-ticker entries plus 3 cross-ticker
reflections as context. Removed the `rank-bm25` dependency. 49 unit tests. The maintainer credited
the design and test suite by name in commit `ebd2e12`.

### Options Analyst — new analyst node
Added a 5th analyst (slotted between Market and Social) that reads the live options chain via
yfinance: call/put volume totals, highest Vol/OI contracts per expiration (7–60 DTE, capped at 4
expirations), call/put skew, OTM call concentration, and short interest % of float. All free, no
API key required. Extends `AgentState` with `options_report`.

### Finnhub + SEC EDGAR data vendors
Built `finnhub.py` as the primary vendor for all data categories (market, indicators, fundamentals,
news), with yfinance retained as fallback on any exception. Added `sec_edgar.py` for 8-K filing
metadata via the EDGAR `/submissions` endpoint — cached ticker→CIK mapping, no API key, US-listed
tickers only. Extended the fundamentals analyst with two new tools: `get_analyst_consensus`
(buy/hold/sell counts, mean price target) and `get_earnings_surprise` (actual vs estimate EPS,
last 4 quarters).

### Real sentiment analyst
Replaced the stub social media analyst with real dataflows: `reddit_sentiment.py` (Reddit public
JSON API across r/wallstreetbets, r/stocks, r/options — no OAuth required), `fear_greed.py` (CNN
dataviz API), and a local-only Unusual Whales Discord monitor (Discord HTTP v10, UW embed regex
parser). Rewrote the system prompt to accurately describe the analyst's actual data sources.
Mock-based tests for all three sources.

### Structured output for decision agents
Converted Portfolio Manager, Trader, and Research Manager from free-form text generation to typed
Pydantic output schemas, eliminating regex-based decision parsing. Standardized to a 5-tier rating
scale (Strong Buy / Buy / Hold / Sell / Strong Sell) across all agents for consistency with the
memory log tag schema.

### LangGraph checkpoint resume
Added SQLite-backed LangGraph checkpointing so a 5–15 minute analysis can resume from the last
completed node after a crash or process kill.

### Gradio web UI + Hugging Face Spaces deployment
Built `web/app.py`: a Gradio 6 streaming interface that yields SSE updates every 2 s during
analysis. Added `gr.BrowserState` localStorage persistence (result survives mobile app-switch and
server restart), an analysis history panel backed by `TradingMemoryLog` with click-to-fill,
S3 memory sync on startup for serverless environments, `TRADINGAGENTS_HOME` env var for portable
path config, and `GRADIO_AUTH_ENABLED` for unauthenticated public demos. Deployed on
[HF Spaces via Docker SDK](https://huggingface.co/spaces/bullcardo/tradingagents).

### Multi-provider LLM support
Extended the LLM factory with DeepSeek, Qwen (Alibaba DashScope), GLM (Zhipu AI), and Azure
OpenAI — each with correct client instantiation and key routing. Added dynamic OpenRouter model
search. Fixed `base_url` leaking into non-OpenAI provider clients. Added lazy-load fixtures so the
test suite runs cleanly without live API credentials.

### Docker + cross-platform reliability
Containerized the project; moved all runtime files to `~/.tradingagents/` to fix Docker UID
permission errors. Identified the incomplete scope of the Windows cp1252 encoding failures
([#543](https://github.com/TauricResearch/TradingAgents/issues/543)) — the maintainer credited
the diagnosis and applied `encoding="utf-8"` across all remaining file I/O in `872b063`. Fixed
yfinance end-date off-by-one bias in backtesting fetchers.

### Hallucination mitigations — filed and adopted upstream
Filed [#572](https://github.com/TauricResearch/TradingAgents/issues/572) with a detailed
reproduction showing agents fabricating past trade lessons on first runs, identified all five
affected agent prompts, and proposed the conditional injection fix. The maintainer implemented
it in `8e7654f` with explicit credit. Separately added grounding rules to both sides of the
research debate to prevent invented data citations in this branch.

---

## Installation

Clone and install:
```bash
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents
pip install -e .
```

Copy `.env.example` → `.env` and fill in your keys:
```bash
# Required: one LLM provider
OPENAI_API_KEY=...
DASHSCOPE_API_KEY=...    # Qwen / Alibaba
DEEPSEEK_API_KEY=...

# Optional: data vendors (yfinance works without any key)
FINNHUB_API_KEY=...      # recommended — 60 calls/min free tier
```

## Usage

**CLI (interactive wizard):**
```bash
tradingagents analyze
```

**Web UI:**
```bash
python web/app.py
```
Or visit the live deployment: <https://huggingface.co/spaces/bullcardo/tradingagents>

**Python API:**
```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

ta = TradingAgentsGraph(debug=True, config=DEFAULT_CONFIG.copy())
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

## LLM providers

`openai` · `anthropic` · `google` · `azure` · `xai` · `deepseek` · `qwen` · `glm` · `ollama` · `openrouter`

Set `deep_think_llm` (Research Manager + Portfolio Manager) and `quick_think_llm` (all other agents)
in `DEFAULT_CONFIG` or pass via CLI. See `tradingagents/default_config.py` for all knobs.

## Contributing

We welcome contributions from the community! If you are interested in this line of research, please
consider joining the open-source financial AI research community [Tauric Research](https://tauric.ai/).

## Citation

```bibtex
@misc{xiao2025tradingagentsmultiagentsllmfinancial,
      title={TradingAgents: Multi-Agents LLM Financial Trading Framework},
      author={Yijia Xiao and Edward Sun and Di Luo and Wei Wang},
      year={2025},
      eprint={2412.20138},
      archivePrefix={arXiv},
      primaryClass={q-fin.TR},
      url={https://arxiv.org/abs/2412.20138},
}
```
