from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Create a custom config
config = DEFAULT_CONFIG.copy()
config["deep_think_llm"] = "qwen3.6-plus"   # Qwen3.6 (commercial)
config["quick_think_llm"] = "qwen3.5-flash"  # Qwen3.5 (commercial)
config["max_debate_rounds"] = 1  # Increase debate rounds
config["max_recur_limit"] = 300  # Increase recursion limit for deeper thinking
config["llm_provider"] = "qwen"


# Configure data vendors (default uses yfinance, no extra API keys needed)
config["data_vendors"] = {
    "core_stock_apis": "yfinance",           # Options: alpha_vantage, yfinance
    "technical_indicators": "yfinance",      # Options: alpha_vantage, yfinance
    "fundamental_data": "yfinance",          # Options: alpha_vantage, yfinance
    "news_data": "yfinance",                 # Options: alpha_vantage, yfinance
}

# Initialize with custom config
ta = TradingAgentsGraph(debug=True, config=config)

# forward propagate
_, decision = ta.propagate("MSFT", "2024-06-10")
print(decision)
print("\n--- Memory log entries:", len(ta.memory_log.load_entries()), "---")
print(ta.memory_log.get_past_context("MSFT") or "(no past context yet)")
