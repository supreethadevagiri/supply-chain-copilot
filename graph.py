from typing import TypedDict
import uuid

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool

from tools_task1_stock_position import get_stock_position
from tools_task2_risk_assessment import get_risk_assessment, get_portfolio_risk_ranking
from latency_tracker import time_response


# --- Tool: wraps Task 1's combined 7-check function ---

@tool
def check_stock_position() -> dict:
    """Runs all seven Task 1 checks -- warehouse stock across both
    Hamburg sites, CRM commitments, freight tracker, supplier emails,
    seasonal benchmark (UN Comtrade + USDA FAS PSD Online), reorder
    timing, and allocation priority -- and returns the full stock
    position answer."""
    return get_stock_position()


# --- Tool: wraps Task 2's combined risk assessment function ---

@tool
def check_shipment_risk(shipment_id: str = "SHP-2201") -> dict:
    """Runs all six real-time risk signals for one shipment -- futures
    price, regional news, deforestation exposure, export volume,
    currency movement, and supplier emails -- plus the shipment's own
    risk trend. Only confirms a risk rating once at least 2 signals
    agree. The shipment's origin municipality is looked up from the
    freight tracker itself, not guessed. Defaults to SHP-2201 if the
    user doesn't name a specific shipment."""
    return get_risk_assessment(shipment_id)


@tool
def check_all_shipments_risk() -> list:
    """Runs the risk check across every incoming shipment at once and
    ranks by severity -- use this when the user asks something like
    'what should I worry about this week' without naming one shipment."""
    return get_portfolio_risk_ranking()


llm = ChatOllama(model="llama3.1:8b", temperature=0)

NO_GUESSING_RULE = (
    "Only use numbers returned by your tool. Never estimate, guess, or "
    "make up any figure. If something the user asked about isn't in the "
    "tool result, say plainly that you don't have that data."
)

# --- The one agent that's actually built so far ---

stock_position_agent = create_agent(
    model=llm,
    tools=[check_stock_position],
    system_prompt=(
        "You are the Stock Position Agent for Elbhafen Coffee Traders, a "
        "Hamburg coffee importer. Call your tool to check current stock, "
        "then explain clearly: whether stock is enough or short (if "
        "short, ALWAYS state the exact shortfall figure in bags, not "
        "just 'short'), how many days of coverage remain, when the next "
        "order needs to go out, and -- if stock is short -- which cafe "
        "accounts would be affected first and why. " + NO_GUESSING_RULE
    ),
)

risk_assessment_agent = create_agent(
    model=llm,
    tools=[check_shipment_risk, check_all_shipments_risk],
    system_prompt=(
        "You are the Risk Assessment Agent for Elbhafen Coffee Traders. "
        "Use check_shipment_risk for one shipment, or "
        "check_all_shipments_risk if the user wants a portfolio-wide view "
        "without naming one shipment. Explain clearly: whether risk is "
        "confirmed (ALWAYS state how many of the 6 signals triggered, "
        "not just 'yes/no'), which specific signals triggered, the "
        "estimated cost % and delay in weeks if risk is confirmed, and "
        "whether the trend is escalating or stabilizing since the last "
        "check. Be explicit that a rating is only issued once at least 2 "
        "signals agree -- this is a deliberate safeguard against a false "
        "alarm from one noisy signal, not a limitation. " + NO_GUESSING_RULE
    ),
)


# --- Router: Task 1 and Task 2 exist now, Task 3 gets a clear ---
# --- "not built yet" answer instead of a wrong/hallucinated one ---

class CopilotState(TypedDict):
    user_query: str
    answer: str
    history: list  # accumulated {"role", "content"} pairs across turns,
                    # persisted via the checkpointer -- this is what makes
                    # follow-up questions ("which of those...") work


def classify_task(user_query: str, history: list) -> str:
    """Task 3 (Sourcing Decision) will be added here in a later phase --
    same dispatcher pattern, one more destination to add. Recent history
    is included so follow-up questions that don't make sense standalone
    (e.g. "which one", "what about that") get classified using the
    conversation so far, not just the new message in isolation."""
    context = ""
    if history:
        recent = history[-4:]  # last couple of exchanges is enough context
        context = "Recent conversation:\n" + "\n".join(
            f"{m['role']}: {m['content']}" for m in recent
        ) + "\n\n"

    prompt = (
        context
        + "Classify this NEW question into exactly one category. If it's "
        "a follow-up that only makes sense given the conversation above "
        "(e.g. 'which one', 'what about that'), use the conversation to "
        "decide. Reply with ONLY the category word.\n\n"
        "STOCK = asking about current stock, inventory, coverage, "
        "reorder timing, or which cafe accounts would be affected by a "
        "shortage\n"
        "RISK = asking whether a shipment is at risk, how bad, likelihood "
        "of delay/price increase, deforestation/compliance exposure, or "
        "what needs attention this week across all shipments\n"
        "OTHER = a genuinely new, unrelated topic (sourcing decisions, or "
        "anything outside stock position and risk assessment) -- including "
        "follow-ups, use the conversation above to route those to STOCK "
        "or RISK if they clearly continue that thread\n\n"
        f"New question: {user_query}\n\nCategory:"
    )
    answer = llm.invoke(prompt).content.strip().upper()
    if "STOCK" in answer:
        return "stock"
    if "RISK" in answer:
        return "risk"
    return "other"


def route_by_task(state: CopilotState) -> str:
    return classify_task(state["user_query"], state.get("history", []))


def run_stock_position_agent(state: CopilotState) -> dict:
    history = state.get("history", [])
    messages = history + [{"role": "user", "content": state["user_query"]}]
    with time_response("stock_position", state["user_query"]):
        result = stock_position_agent.invoke({"messages": messages})
    answer = result["messages"][-1].content
    updated_history = messages + [{"role": "assistant", "content": answer}]
    return {"answer": answer, "history": updated_history}


def run_risk_assessment_agent(state: CopilotState) -> dict:
    history = state.get("history", [])
    messages = history + [{"role": "user", "content": state["user_query"]}]
    with time_response("risk_assessment", state["user_query"]):
        result = risk_assessment_agent.invoke({"messages": messages})
    answer = result["messages"][-1].content
    updated_history = messages + [{"role": "assistant", "content": answer}]
    return {"answer": answer, "history": updated_history}


def run_not_yet_built(state: CopilotState) -> dict:
    return {
        "answer": (
            "I can answer Stock Position questions (do we have enough "
            "coffee, when do we need to reorder, which accounts are "
            "exposed) and Risk Assessment questions (is a shipment at "
            "risk, how bad, is it escalating). Sourcing Decision is "
            "being built next."
        )
    }


# --- Build the graph ---

builder = StateGraph(CopilotState)
builder.add_node("stock_position_agent", run_stock_position_agent)
builder.add_node("risk_assessment_agent", run_risk_assessment_agent)
builder.add_node("not_yet_built", run_not_yet_built)

builder.add_conditional_edges(
    START,
    route_by_task,
    {"stock": "stock_position_agent", "risk": "risk_assessment_agent", "other": "not_yet_built"},
)
builder.add_edge("stock_position_agent", END)
builder.add_edge("risk_assessment_agent", END)
builder.add_edge("not_yet_built", END)

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)


def chat():
    print("Coffee Supply Risk Copilot -- Task 1 (Stock Position) only, for now")
    print("Try: 'do we have enough stock?' or 'is SHP-2201 at risk?'")
    print("Type 'quit' to exit.\n")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        result = graph.invoke({"user_query": user_input, "answer": ""}, config=config)
        print(f"\nCopilot:\n{result['answer']}\n")


if __name__ == "__main__":
    chat()
