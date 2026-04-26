"""
TradingAgents Web UI
====================
Run:
    py web/app.py

Then expose globally with:
    ngrok http 7860

Configure via .env (see .env.example):
    GRADIO_USERS=alice:password1,bob:password2
    GRADIO_PORT=7860
    WEB_LLM_PROVIDER=openai          # openai | anthropic | google | ollama | ...
    WEB_DEEP_MODEL=gpt-4o            # deep-think agent model
    WEB_QUICK_MODEL=gpt-4o-mini      # quick-think agent model
    WEB_BACKEND_URL=                 # optional, e.g. http://localhost:11434/v1 for Ollama
"""

import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure project root is on sys.path when run as `py web/app.py`
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

# ---------------------------------------------------------------------------
# S3 memory sync (optional — skipped if env vars not set)
# ---------------------------------------------------------------------------

_S3_BUCKET = os.environ.get("S3_MEMORY_BUCKET")
_S3_KEY    = os.environ.get("S3_MEMORY_KEY")
_S3_CLIENT = None

def _get_s3():
    global _S3_CLIENT
    if _S3_CLIENT is None and _S3_BUCKET and _S3_KEY:
        try:
            import boto3
            _S3_CLIENT = boto3.client(
                "s3",
                region_name=os.environ.get("AWS_REGION"),
            )
        except Exception as exc:
            logger.warning("S3 client init failed (memory will not persist): %s", exc)
    return _S3_CLIENT


def _s3_download_memory(local_path: Path) -> None:
    """Download trading_memory.md from S3 to local_path. No-op if not configured or key missing."""
    s3 = _get_s3()
    if not s3:
        return
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        s3.download_file(_S3_BUCKET, _S3_KEY, str(local_path))
        logger.info("Memory downloaded from s3://%s/%s", _S3_BUCKET, _S3_KEY)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if code in ("404", "403", "NoSuchKey"):
            logger.info("No existing memory in S3 — starting fresh.")
        else:
            logger.warning("S3 download failed (memory will start fresh): %s", exc)


def _s3_upload_memory(local_path: Path) -> None:
    """Upload trading_memory.md from local_path to S3. No-op if not configured or file missing."""
    s3 = _get_s3()
    if not s3 or not local_path.exists():
        return
    try:
        s3.upload_file(str(local_path), _S3_BUCKET, _S3_KEY)
        logger.info("Memory uploaded to s3://%s/%s", _S3_BUCKET, _S3_KEY)
    except Exception as exc:
        logger.warning("S3 upload failed (memory saved locally only): %s", exc)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Download memory from S3 on startup (no-op if S3 not configured)
_MEMORY_PATH = Path(DEFAULT_CONFIG["memory_log_path"])
_s3_download_memory(_MEMORY_PATH)

LLM_PROVIDER = os.environ.get("WEB_LLM_PROVIDER", DEFAULT_CONFIG["llm_provider"])
DEEP_MODEL    = os.environ.get("WEB_DEEP_MODEL",    DEFAULT_CONFIG["deep_think_llm"])
QUICK_MODEL   = os.environ.get("WEB_QUICK_MODEL",   DEFAULT_CONFIG["quick_think_llm"])
BACKEND_URL   = os.environ.get("WEB_BACKEND_URL",   DEFAULT_CONFIG.get("backend_url"))
PORT          = int(os.environ.get("GRADIO_PORT", "7860"))

def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = LLM_PROVIDER
    config["deep_think_llm"] = DEEP_MODEL
    config["quick_think_llm"] = QUICK_MODEL
    if BACKEND_URL:
        config["backend_url"] = BACKEND_URL
    return config


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _parse_users() -> list[tuple[str, str]] | None:
    """Parse GRADIO_USERS env var.

    Format: "alice:pw1,bob:pw2"
    Returns None (no auth) if the variable is unset or empty.
    """
    raw = os.environ.get("GRADIO_USERS", "").strip()
    if not raw:
        return None
    users = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            username, password = entry.split(":", 1)
            users.append((username.strip(), password.strip()))
    return users or None


# ---------------------------------------------------------------------------
# Analysis runner
# ---------------------------------------------------------------------------

ANALYST_CHOICES = ["market", "options", "social", "news", "fundamentals"]

PHASES = [
    "Analyst Team working...",
    "Research Team debating...",
    "Trader synthesizing...",
    "Risk Management assessing...",
    "Portfolio Manager deciding...",
]

SIGNAL_EMOJI = {
    "buy":         "🟢",
    "overweight":  "🟢",
    "hold":        "🟡",
    "underweight": "🔴",
    "sell":        "🔴",
}


def _format_result(final_state: dict, signal: str) -> str:
    emoji = SIGNAL_EMOJI.get(signal.lower(), "⚪")
    parts = [f"# {emoji} Decision: **{signal.upper()}**"]

    if final_state.get("final_trade_decision"):
        parts.append(
            f"---\n## Portfolio Manager Decision\n\n{final_state['final_trade_decision']}"
        )

    analyst_sections = [
        ("Market Analysis",       final_state.get("market_report")),
        ("Options Analysis",      final_state.get("options_report")),
        ("Social Sentiment",      final_state.get("sentiment_report")),
        ("News Analysis",         final_state.get("news_report")),
        ("Fundamentals Analysis", final_state.get("fundamentals_report")),
    ]
    for title, content in analyst_sections:
        if content:
            parts.append(f"---\n## {title}\n\n{content}")

    if final_state.get("investment_plan"):
        parts.append(f"---\n## Research Team Decision\n\n{final_state['investment_plan']}")

    if final_state.get("trader_investment_plan"):
        parts.append(f"---\n## Trader Plan\n\n{final_state['trader_investment_plan']}")

    return "\n\n".join(parts)


def _detect_phase(state: dict) -> str:
    """Map accumulated graph state to a human-readable phase label.

    stream_mode="values" means every chunk is the full state so far,
    making it safe to check any field at any point.
    """
    risk = state.get("risk_debate_state") or {}
    debate = state.get("investment_debate_state") or {}

    if risk.get("judge_decision", "").strip():
        return "Portfolio Manager deciding..."
    if state.get("trader_investment_plan", "").strip():
        return "Risk Management assessing..."
    if debate.get("judge_decision", "").strip():
        return "Trader synthesizing..."
    if debate.get("bull_history", "").strip() or debate.get("bear_history", "").strip():
        return "Research Team debating..."
    analyst_fields = ("market_report", "options_report", "sentiment_report",
                      "news_report", "fundamentals_report")
    if any(state.get(f, "").strip() for f in analyst_fields):
        return "Analyst Team working..."
    return "Initializing..."


def run_analysis(ticker: str, date: str, analysts: list[str]):
    """Generator — yields (status_md, result_md) tuples while analysis runs."""

    # --- Input validation ---
    ticker = ticker.strip().upper()
    if not ticker:
        yield "❌ Please enter a ticker symbol.", ""
        return
    if not analysts:
        yield "❌ Please select at least one analyst.", ""
        return
    try:
        datetime.strptime(date.strip(), "%Y-%m-%d")
    except ValueError:
        yield "❌ Invalid date — use YYYY-MM-DD format.", ""
        return
    if datetime.strptime(date.strip(), "%Y-%m-%d").date() > datetime.now().date():
        yield "❌ Analysis date cannot be in the future.", ""
        return

    # --- Background worker — streams graph chunks to update phase in real time ---
    shared: dict = {"done": False, "result": None, "error": None, "phase": "Initializing..."}

    def worker():
        try:
            config = _build_config()
            ta = TradingAgentsGraph(selected_analysts=analysts, config=config)

            # Replicate the pre-flight steps from propagate()
            ta.ticker = ticker
            ta._resolve_pending_entries(ticker)
            past_context = ta.memory_log.get_past_context(ticker)
            init_state = ta.propagator.create_initial_state(
                ticker, date.strip(), past_context=past_context
            )
            args = ta.propagator.get_graph_args()

            # Stream instead of invoke — each chunk is the full accumulated state
            final_state = None
            for chunk in ta.graph.stream(init_state, **args):
                final_state = chunk
                shared["phase"] = _detect_phase(chunk)

            # Replicate the post-flight steps from propagate()
            ta._log_state(date.strip(), final_state)
            ta.memory_log.store_decision(
                ticker=ticker,
                trade_date=date.strip(),
                final_trade_decision=final_state["final_trade_decision"],
            )
            _s3_upload_memory(_MEMORY_PATH)
            signal = ta.process_signal(final_state["final_trade_decision"])
            shared["result"] = (final_state, signal)
        except Exception as exc:
            shared["error"] = str(exc)
        finally:
            shared["done"] = True

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    # --- Disable button, then stream real phase every 2s ---
    yield gr.update(interactive=False), "", ""

    start = time.time()
    while not shared["done"]:
        elapsed = int(time.time() - start)
        yield (
            gr.update(interactive=False),
            f"⏳ **{shared['phase']}** &nbsp;&nbsp; `{elapsed}s elapsed`\n\n"
            "_Analysis takes 5–15 minutes depending on your LLM provider._",
            "",
        )
        time.sleep(2)

    if shared["error"]:
        yield gr.update(interactive=True), f"❌ **Error:** {shared['error']}", ""
        return

    final_state, signal = shared["result"]
    elapsed = int(time.time() - start)
    yield gr.update(interactive=True), f"✅ **Done** in {elapsed}s", _format_result(final_state, signal)


# ---------------------------------------------------------------------------
# UI layout
# ---------------------------------------------------------------------------

today = datetime.now().strftime("%Y-%m-%d")

with gr.Blocks(title="TradingAgents") as demo:

    gr.Markdown(
        "# TradingAgents\n"
        "Multi-agent LLM financial analysis — enter a ticker and date to get a trading decision."
    )

    with gr.Row():
        ticker_box = gr.Textbox(
            label="Ticker Symbol",
            value="SPY",
            placeholder="e.g. NVDA, AAPL, 0700.HK",
        )
        date_box = gr.Textbox(
            label="Analysis Date",
            value=today,
            placeholder="YYYY-MM-DD",
        )

    analysts_box = gr.CheckboxGroup(
        choices=ANALYST_CHOICES,
        value=["market", "social", "news", "fundamentals"],
        label="Analysts",
    )

    analyze_btn = gr.Button("Analyze", variant="primary", size="lg")

    status_box = gr.Markdown(value="")
    result_box = gr.Markdown(value="")

    analyze_btn.click(
        fn=run_analysis,
        inputs=[ticker_box, date_box, analysts_box],
        outputs=[analyze_btn, status_box, result_box],
    )

demo.queue(max_size=5)  # serialize requests; friends queue rather than collide

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    users = _parse_users()

    if users:
        print(f"Auth enabled — {len(users)} user(s) configured.")
    else:
        print("Warning: GRADIO_USERS not set — running without authentication.")

    print(f"Provider : {LLM_PROVIDER} / deep={DEEP_MODEL} / quick={QUICK_MODEL}")
    print(f"Listening: http://0.0.0.0:{PORT}")

    demo.launch(
        server_name="0.0.0.0",
        server_port=PORT,
        auth=users,
        auth_message="TradingAgents — sign in to continue",
        show_error=True,
        theme=gr.themes.Soft(),
    )
