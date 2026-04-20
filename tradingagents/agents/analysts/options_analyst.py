from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
from tradingagents.agents.utils.options_tools import get_options_flow, get_short_interest
from tradingagents.dataflows.config import get_config


def create_options_analyst(llm):
    def options_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = build_instrument_context(state["company_of_interest"])

        tools = [
            get_options_flow,
            get_short_interest,
        ]

        system_message = (
            "You are an Options Flow Analyst. Your job is to read the options market for a "
            "specific stock and determine what informed and institutional participants are "
            "signalling through their positioning.\n\n"
            "Use get_options_flow(ticker) to fetch the live options chain. Analyze:\n"
            "  - Call/put skew: >65% calls = strong bullish positioning; >65% puts = bearish\n"
            "  - Vol/OI ratio: a ratio >3x on a specific strike means fresh unusual activity "
            "(new bets being placed, not existing OI being traded) — this is the strongest signal\n"
            "  - OTM call concentration: high OTM call % = speculative directional bets ahead "
            "of a move; low OTM % = hedging or covered-call writing (less directional)\n"
            "  - DTE (days to expiration): very short DTE (7-14 days) with high volume = urgency, "
            "likely an event play (earnings, catalyst); longer DTE = strategic positioning\n\n"
            "Use get_short_interest(ticker) to check short interest % of float. Interpret it as:\n"
            "  - >25%: Very high — combine with bullish call flow to assess squeeze potential\n"
            "  - 15-25%: High — notable squeeze risk on upward moves\n"
            "  - <8%: Low — shorts are not a significant market factor\n\n"
            "Write a comprehensive options report covering:\n"
            "1. Overall positioning bias (bullish / bearish / neutral) with supporting evidence\n"
            "2. Notable contracts — specific strikes with unusual Vol/OI that suggest informed bets\n"
            "3. Urgency signals — short-dated high-volume activity that suggests event positioning\n"
            "4. Squeeze assessment — combine short interest with call flow to judge squeeze risk\n"
            "5. Key risk — what the options market implies could go wrong for the prevailing thesis\n\n"
            "If get_options_flow returns an informative message (no near-term expirations, no "
            "options listed), state that clearly — it is relevant context for the team.\n\n"
            "Append a Markdown table summarising key metrics (skew %, top Vol/OI strike, "
            "short interest %, DTE of highest-activity expiration)."
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " If you or any other assistant has the FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** or deliverable,"
                    " prefix your response with FINAL TRANSACTION PROPOSAL: **BUY/HOLD/SELL** so the team knows to stop."
                    " You have access to the following tools: {tool_names}.\n{system_message}"
                    "For your reference, the current date is {current_date}. {instrument_context}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        chain = prompt | llm.bind_tools(tools)

        result = chain.invoke(state["messages"])

        report = ""
        if len(result.tool_calls) == 0:
            report = result.content

        return {
            "messages": [result],
            "options_report": report,
        }

    return options_analyst_node
