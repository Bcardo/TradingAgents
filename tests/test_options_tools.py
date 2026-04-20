"""Mock-based unit tests for options_flow.py and short_interest.py dataflows."""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, timedelta

from tradingagents.dataflows.options_flow import get_options_flow_data
from tradingagents.dataflows.short_interest import get_short_interest_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exp_str(days_out: int) -> str:
    return (date.today() + timedelta(days=days_out)).strftime("%Y-%m-%d")


def _make_calls_df(rows):
    """Build a minimal calls/puts DataFrame."""
    return pd.DataFrame(rows, columns=[
        "strike", "lastPrice", "volume", "openInterest",
        "impliedVolatility", "inTheMoney",
    ])


def _make_option_chain(calls_rows, puts_rows):
    oc = MagicMock()
    oc.calls = _make_calls_df(calls_rows)
    oc.puts = _make_calls_df(puts_rows)
    return oc


# ---------------------------------------------------------------------------
# options_flow — get_options_flow_data
# ---------------------------------------------------------------------------

class TestOptionsFlow:

    def _mock_ticker(self, expirations, chain_by_exp):
        tk = MagicMock()
        type(tk).options = PropertyMock(return_value=expirations)
        tk.option_chain.side_effect = lambda exp: chain_by_exp[exp]
        return tk

    def test_happy_path_returns_call_put_volumes(self):
        exp = _exp_str(14)
        calls = [
            (280, 3.50, 5000, 1000, 0.45, False),
            (275, 5.20, 2000, 800,  0.42, True),
        ]
        puts = [
            (270, 2.10, 1500, 600, 0.40, False),
        ]
        chain = {exp: _make_option_chain(calls, puts)}

        with patch("tradingagents.dataflows.options_flow.yf.Ticker", return_value=self._mock_ticker([exp], chain)):
            result = get_options_flow_data("NVDA")

        assert "Calls: 7,000" in result
        assert "Puts: 1,500" in result
        assert "Vol/OI" in result
        assert "Overall" in result

    def test_no_expirations_returns_informative_message(self):
        tk = MagicMock()
        type(tk).options = PropertyMock(return_value=[])

        with patch("tradingagents.dataflows.options_flow.yf.Ticker", return_value=tk):
            result = get_options_flow_data("NVDA")

        assert "No options" in result
        assert result != ""

    def test_all_expirations_outside_dte_window_returns_informative_message(self):
        # All expirations > 60 DTE
        exp_far = _exp_str(90)
        tk = MagicMock()
        type(tk).options = PropertyMock(return_value=[exp_far])

        with patch("tradingagents.dataflows.options_flow.yf.Ticker", return_value=tk):
            result = get_options_flow_data("NVDA")

        assert "7-60" in result or "No options expirations" in result
        assert result != ""

    def test_yfinance_exception_returns_empty_string(self):
        with patch("tradingagents.dataflows.options_flow.yf.Ticker", side_effect=Exception("network error")):
            result = get_options_flow_data("NVDA")

        assert result == ""

    def test_call_put_skew_reported_correctly(self):
        exp = _exp_str(14)
        # Heavy call dominance
        calls = [(280, 3.0, 9000, 1000, 0.45, False)]
        puts =  [(270, 2.0, 1000, 500,  0.40, False)]
        chain = {exp: _make_option_chain(calls, puts)}

        with patch("tradingagents.dataflows.options_flow.yf.Ticker", return_value=self._mock_ticker([exp], chain)):
            result = get_options_flow_data("NVDA")

        assert "90% calls" in result or "bullish" in result.lower()

    def test_caps_at_four_expirations(self):
        exps = [_exp_str(d) for d in [10, 17, 24, 31, 38, 45]]
        calls = [(280, 3.0, 1000, 500, 0.45, False)]
        puts  = [(270, 2.0, 500,  200, 0.40, False)]
        chain = {e: _make_option_chain(calls, puts) for e in exps}

        call_count = []

        def counting_chain(exp):
            call_count.append(exp)
            return chain[exp]

        tk = MagicMock()
        type(tk).options = PropertyMock(return_value=exps)
        tk.option_chain.side_effect = counting_chain

        with patch("tradingagents.dataflows.options_flow.yf.Ticker", return_value=tk):
            get_options_flow_data("NVDA")

        assert len(call_count) <= 4


# ---------------------------------------------------------------------------
# short_interest — get_short_interest_data
# ---------------------------------------------------------------------------

class TestShortInterest:

    def _mock_ticker(self, info_dict):
        tk = MagicMock()
        type(tk).info = PropertyMock(return_value=info_dict)
        return tk

    def test_happy_path_returns_formatted_percentage(self):
        with patch("tradingagents.dataflows.short_interest.yf.Ticker",
                   return_value=self._mock_ticker({"shortPercentOfFloat": 0.183, "shortRatio": 4.2})):
            result = get_short_interest_data("NVDA")

        assert "18.3%" in result
        assert "4.2" in result
        assert "NVDA" in result

    def test_key_missing_returns_fallback_message(self):
        with patch("tradingagents.dataflows.short_interest.yf.Ticker",
                   return_value=self._mock_ticker({})):
            result = get_short_interest_data("NVDA")

        assert "unavailable" in result.lower()
        assert "NVDA" in result

    def test_yfinance_exception_returns_fallback_message(self):
        with patch("tradingagents.dataflows.short_interest.yf.Ticker",
                   side_effect=Exception("timeout")):
            result = get_short_interest_data("NVDA")

        assert "unavailable" in result.lower()

    def test_high_short_interest_context(self):
        with patch("tradingagents.dataflows.short_interest.yf.Ticker",
                   return_value=self._mock_ticker({"shortPercentOfFloat": 0.30})):
            result = get_short_interest_data("GME")

        assert "squeeze" in result.lower() or "Very high" in result

    def test_low_short_interest_context(self):
        with patch("tradingagents.dataflows.short_interest.yf.Ticker",
                   return_value=self._mock_ticker({"shortPercentOfFloat": 0.02})):
            result = get_short_interest_data("AAPL")

        assert "Low" in result or "low" in result
