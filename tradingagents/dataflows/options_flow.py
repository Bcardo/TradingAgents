"""
Options flow dataflow — fetches and formats the live options chain for a ticker
via yfinance. Returns a human-readable summary suitable for LLM analysis.

Covers up to 4 expirations in the 7-60 DTE window. No API key required.
"""

import logging
from datetime import date, datetime

import yfinance as yf

logger = logging.getLogger(__name__)

_MAX_EXPIRATIONS = 4
_MIN_DTE = 7
_MAX_DTE = 60
_TOP_CONTRACTS = 3
_MIN_VOL_FOR_VOL_OI = 10  # ignore contracts with fewer than 10 trades when ranking by Vol/OI


def _safe_int(v, default: int = 0) -> int:
    try:
        f = float(v)
        return int(f) if f == f else default
    except (TypeError, ValueError):
        return default


def _safe_float(v, default: float = 0.0) -> float:
    try:
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def get_options_flow_data(ticker: str) -> str:
    """
    Fetch live options chain for a ticker and return a formatted summary.

    Filters expirations to 7-60 DTE, caps at 4 expirations, and for each
    computes: call/put volume totals, top contracts by Vol/OI ratio, call/put
    skew, and OTM call concentration. Appends an overall cross-expiration
    summary with a directional signal interpretation.

    Returns an informative message (not empty string) when options exist but
    fall outside the DTE window — absence of near-term options is itself
    meaningful. Returns empty string only on hard failure.
    """
    ticker = ticker.upper()

    try:
        tk = yf.Ticker(ticker)
        expirations = tk.options
    except Exception as e:
        logger.warning("options_flow %s: failed to fetch expirations: %s", ticker, e)
        return ""

    if not expirations:
        return f"No options data found for {ticker}. The ticker may not have listed options (ETFs, some foreign listings)."

    today = date.today()
    valid_exps = []
    for exp_str in expirations:
        try:
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
            dte = (exp - today).days
            if _MIN_DTE <= dte <= _MAX_DTE:
                valid_exps.append((exp_str, dte))
        except ValueError:
            continue

    if not valid_exps:
        return (
            f"No options expirations found for {ticker} in the {_MIN_DTE}-{_MAX_DTE} DTE window. "
            f"Nearest expiration: {expirations[0] if expirations else 'none'}."
        )

    valid_exps = valid_exps[:_MAX_EXPIRATIONS]

    lines = [f"Options Flow — {ticker} (as of {today})"]
    exp_labels = [f"{e} ({d} DTE)" for e, d in valid_exps]
    lines.append(f"Expirations analyzed: {', '.join(exp_labels)}\n")

    total_call_vol = 0
    total_put_vol = 0
    total_otm_call_vol = 0

    for exp_str, dte in valid_exps:
        try:
            opt = tk.option_chain(exp_str)
        except Exception as e:
            logger.warning("options_flow %s @ %s: chain fetch failed: %s", ticker, exp_str, e)
            continue

        calls_df = opt.calls.copy() if opt.calls is not None else None
        puts_df = opt.puts.copy() if opt.puts is not None else None

        if calls_df is None or calls_df.empty:
            exp_call_vol = 0
        else:
            calls_df = calls_df[calls_df["volume"].fillna(0) > 0]
            exp_call_vol = _safe_int(calls_df["volume"].sum())

        if puts_df is None or puts_df.empty:
            exp_put_vol = 0
        else:
            puts_df = puts_df[puts_df["volume"].fillna(0) > 0]
            exp_put_vol = _safe_int(puts_df["volume"].sum())

        total_call_vol += exp_call_vol
        total_put_vol += exp_put_vol

        # OTM calls — inTheMoney == False means the call is out of the money
        if calls_df is not None and not calls_df.empty and "inTheMoney" in calls_df.columns:
            otm_calls = calls_df[calls_df["inTheMoney"] == False]
        else:
            otm_calls = calls_df if calls_df is not None else None
        exp_otm_vol = _safe_int(otm_calls["volume"].sum()) if (otm_calls is not None and not otm_calls.empty) else 0
        total_otm_call_vol += exp_otm_vol

        exp_total = exp_call_vol + exp_put_vol
        call_pct = int(exp_call_vol / exp_total * 100) if exp_total else 50
        if call_pct > 55:
            skew_str = f"{call_pct}% calls (bullish bias)"
        elif call_pct < 45:
            skew_str = f"{100 - call_pct}% puts (bearish bias)"
        else:
            skew_str = f"{call_pct}% calls (neutral)"

        block = [f"=== {exp_str} ({dte} DTE) ==="]
        block.append(f"Volume — Calls: {exp_call_vol:,} | Puts: {exp_put_vol:,} | Skew: {skew_str}")

        # Top calls by Vol/OI
        if calls_df is not None and not calls_df.empty and "openInterest" in calls_df.columns:
            calls_df["vol_oi"] = calls_df["volume"] / calls_df["openInterest"].replace(0, float("nan"))
            top_calls = (
                calls_df[calls_df["volume"] >= _MIN_VOL_FOR_VOL_OI]
                .dropna(subset=["vol_oi"])
                .nlargest(_TOP_CONTRACTS, "vol_oi")
            )
            if not top_calls.empty:
                block.append(f"Top {len(top_calls)} calls by Vol/OI (unusual activity):")
                for _, row in top_calls.iterrows():
                    strike = _safe_float(row.get("strike"))
                    vol = _safe_int(row.get("volume"))
                    oi = _safe_int(row.get("openInterest"))
                    vol_oi = _safe_float(row.get("vol_oi"))
                    iv = _safe_float(row.get("impliedVolatility"))
                    last = _safe_float(row.get("lastPrice"))
                    tag = " [OTM]" if row.get("inTheMoney") is False else " [ITM]"
                    block.append(
                        f"  ${strike:.0f} Call{tag} — Vol: {vol:,} | OI: {oi:,} | "
                        f"Vol/OI: {vol_oi:.1f}x | IV: {iv:.0%} | Last: ${last:.2f}"
                    )

        if exp_call_vol > 0:
            otm_pct = int(exp_otm_vol / exp_call_vol * 100)
            block.append(f"OTM call volume: {otm_pct}% of total calls this expiration")

        lines.append("\n".join(block))

    # Overall summary
    grand_total = total_call_vol + total_put_vol
    if grand_total == 0:
        lines.append("No volume data available across analyzed expirations.")
        return "\n\n".join(lines)

    overall_call_pct = int(total_call_vol / grand_total * 100)
    otm_overall_pct = int(total_otm_call_vol / total_call_vol * 100) if total_call_vol else 0

    if overall_call_pct >= 65:
        positioning = "Strong bullish — calls heavily dominate flow"
    elif overall_call_pct >= 55:
        positioning = "Moderate bullish bias"
    elif overall_call_pct <= 35:
        positioning = "Strong bearish — puts heavily dominate flow"
    elif overall_call_pct <= 45:
        positioning = "Moderate bearish bias"
    else:
        positioning = "Neutral — balanced call/put flow"

    if otm_overall_pct >= 60:
        otm_signal = "High OTM call concentration — speculative directional betting"
    elif otm_overall_pct >= 40:
        otm_signal = "Mixed OTM/ITM activity"
    else:
        otm_signal = "Mostly ITM calls — hedging or covered-call activity"

    summary = [
        "=== Overall Summary ===",
        f"Total call volume: {total_call_vol:,} | Total put volume: {total_put_vol:,}",
        f"Overall call/put skew: {overall_call_pct}% calls",
        f"Positioning signal: {positioning}",
        f"OTM call concentration: {otm_overall_pct}% — {otm_signal}",
    ]
    lines.append("\n".join(summary))

    return "\n\n".join(lines)
