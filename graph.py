from typing import TypedDict
import re
import unicodedata
import uuid
from datetime import datetime

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_ollama import ChatOllama
from langchain.agents import create_agent
from langchain_core.tools import tool

from tools_task1_stock_position import get_stock_position, get_stock_position_hypothetical
from tools_task2_risk_assessment import get_portfolio_risk_ranking, get_risk_assessment_hypothetical
from real_data_sources import get_trase_deforestation_exposure
from tools_task2_disruption_response import get_disruption_response, find_alternative_source
from tools_task3_sourcing_decision import get_sourcing_decision, get_sourcing_decision_hypothetical
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
    """Runs the full disruption workflow for one shipment: checks all
    six real-time risk signals, only confirms a disruption once at
    least 2 of 6 agree, then -- if confirmed -- alarms the company
    (logs a real alert), suggests a backup supplier if one exists on
    file, and if no backup exists, reports the estimated price
    increase. Defaults to SHP-2201 if the user doesn't name a specific
    shipment."""
    return get_disruption_response(shipment_id)


@tool
def check_all_shipments_risk() -> list:
    """Runs the risk check across every incoming shipment at once and
    ranks by severity -- use this when the user asks something like
    'what should I worry about this week' without naming one shipment.
    Returns a SLIMMED-DOWN summary per shipment, not the full raw
    signal_details (news headlines, exact FX rates, futures prices,
    etc. for every shipment) -- with 5 real shipments now on file,
    handing the full nested detail for all of them at once overwhelmed
    the local model and made it describe the JSON's shape instead of
    answering the question. Also enriches each confirmed-disruption
    entry with the same alternative-source lookup used for a single
    shipment, so the backup supplier isn't silently missing."""
    results = get_portfolio_risk_ranking()
    alternative = find_alternative_source()
    summaries = []
    for entry in results:
        triggered_names = [name for name, v in entry["signals_triggered"].items() if v]
        summary = {
            "shipment_id": entry["shipment_id"],
            "origin_municipality": entry["origin_municipality"],
            "num_signals_triggered": entry["num_signals_triggered"],
            "which_signals_triggered": triggered_names,
            "risk_confirmed": entry["risk_confirmed"],
            "risk_rating": entry["risk_rating"],
            "cost_pct_estimate": entry["cost_pct_estimate"],
            "delay_weeks_estimate": entry["delay_weeks_estimate"],
            "reasoning": entry["reasoning"],
        }
        if entry.get("risk_confirmed"):
            summary["alternative_source"] = alternative
        summaries.append(summary)
    return summaries


# --- Tool: wraps Task 3's sourcing decision function ---

@tool
def check_sourcing_decision() -> dict:
    """Checks whether switching from the current supplier to the known
    backup is actually advisable, once a disruption has already been
    confirmed (Task 2's job) -- covers contract compliance (would
    switching breach the current contract), the backup origin's
    deforestation/EUDR compliance exposure via Trase.earth, payment
    timing (does the backup require upfront cash), and overall
    sourcing concentration (how reliant we are on one region). Takes
    no arguments -- always evaluates the current and backup supplier
    already on file. Does NOT suggest or compare backup suppliers --
    assumes one is already identified."""
    return get_sourcing_decision()



@tool
def check_stock_hypothetical(warehouse_bag_delta: int = 0, cafe_bag_delta: int = 0) -> dict:
    """Answers a 'what if' stock question WITHOUT changing any real
    data -- e.g. 'what if we added 300 bags to the warehouse' (pass
    warehouse_bag_delta=300), or 'what if a cafe ordered 100 more
    bags' (pass cafe_bag_delta=100). Use ONLY for genuine hypothetical
    questions, never for the real current situation -- check_stock_position
    already answers that."""
    return get_stock_position_hypothetical(warehouse_bag_delta, cafe_bag_delta)


@tool
def check_shipment_risk_hypothetical(shipment_id: str, extra_signal_name: str) -> dict:
    """Answers a 'what if this signal also triggered' question WITHOUT
    changing any real data. Valid signal names: futures_price_spike,
    regional_news, deforestation_exposure, export_volume_drop,
    currency_move, supplier_email_warning. Use ONLY for genuine
    hypothetical questions, never for the real current situation."""
    return get_risk_assessment_hypothetical(shipment_id, extra_signal_name)


@tool
def check_sourcing_decision_hypothetical(override_contract_ok: bool = None, override_deforestation_ok: bool = None) -> dict:
    """Answers a 'what if' sourcing question WITHOUT changing any real
    data -- e.g. 'what if the contract had no minimum order clause'
    (pass override_contract_ok=True), or 'what if the backup region
    weren't flagged for deforestation' (pass
    override_deforestation_ok=True). Use ONLY for genuine hypothetical
    questions, never for the real current situation."""
    return get_sourcing_decision_hypothetical(override_contract_ok, override_deforestation_ok)


llm = ChatOllama(model="llama3.1:8b", temperature=0)

NO_GUESSING_RULE = (
    "Only use numbers returned by your tool. Never estimate, guess, or "
    "make up any figure. If something the user asked about isn't in the "
    "tool result, say plainly that you don't have that data."
)

NO_CROSS_CONTAMINATION_RULE = (
    "The conversation above may include earlier, unrelated "
    "questions about a different cafe, shipment, or supplier. "
    "Only use that earlier conversation if the CURRENT question "
    "is clearly a follow-up to it (e.g. 'why', 'what about "
    "that one'). NEVER pull a specific name, number, or fact "
    "from an earlier, unrelated question into your answer for "
    "this one -- always base your answer only on your own "
    "tool's real output for the CURRENT question."
)

# --- The three agents ---

stock_position_agent = create_agent(
    model=llm,
    tools=[check_stock_position, check_stock_hypothetical],
    system_prompt=(
        "You are the Stock Position Agent for Elbhafen Coffee Traders, a "
        "Hamburg coffee importer. Call your tool to check current stock. "
        "ALWAYS answer the SPECIFIC question the user actually asked, "
        "directly and first, in plain language a warehouse or "
        "procurement person would use, not technical jargon. Never use "
        "the words 'flag' or 'Warning Flag' -- call it a 'supplier "
        "alert' instead, since that's what a business user would say. "
        "Also never use the words 'burn rate' anywhere, including when "
        "quoting the tool's own reasoning text -- replace it with "
        "'usage rate' every time it appears. "
        "\n\nA narrow answer is NOT a bare fact -- it must still "
        "briefly explain what the number means or where it came from, "
        "in plain language, so a non-technical business user "
        "understands it, not just receives a number. 'Narrow' means "
        "don't repeat the ENTIRE structured block -- it does NOT mean "
        "strip out all context. "
        "\n\nIf the question is the GENERAL one (e.g. 'do we have enough "
        "stock', 'are we short or do we have a surplus', 'what's our "
        "stock position'), give the full picture: whether stock is "
        "enough or short (if short, ALWAYS state the exact shortfall "
        "figure in bags), then labeled fields on separate lines -- "
        "Demand (from Salesforce), Supply (from Shippo), and Supplier "
        "Alert (from Gmail, or 'none' if nothing found) -- then the "
        "reorder date and every affected cafe account. "
        "\n\nIf the question is NARROWER -- for example only about "
        "coverage days, only the reorder date, only warehouse stock, "
        "only in-transit stock, only the supplier email or alert, or "
        "about one specific cafe by name -- answer ONLY that specific "
        "thing, explained briefly. Do NOT include the Demand line, the "
        "Supply line, the Supplier Alert line, the reorder date, or the "
        "cafe list unless the question specifically asked about that "
        "exact thing. "
        "\n\nThis explanation requirement applies to EVERY narrow "
        "question, not just one example -- always include a brief "
        "'because' reason tied to real tool data, so the reasoning is "
        "preserved in the conversation for any later 'why' question, "
        "since you won't have the raw tool data again at that point, "
        "only what you wrote here. "
        "\n\nEXAMPLE 1, CORRECT -- question: 'how many days of "
        "coverage do we have left?' -- correct complete answer: 'We "
        "have 20.7 days of coverage left, based on our current usage "
        "rate -- that's less than the 21 days it takes our supplier to "
        "deliver a new order.' "
        "\n\nEXAMPLE 2, CORRECT -- question: 'when do we need to "
        "reorder?' -- correct complete answer: 'The next order needs "
        "to go out by 2026-09-08, because our stock only covers 20.7 "
        "more days, which is less than our supplier's 21-day delivery "
        "time.' Do NOT just say the date alone with no reason -- that "
        "leaves nothing for a later 'why' question to work from. "
        "\n\nEXAMPLE of an INCORRECT narrow answer to that same "
        "question -- do NOT do this: stating the coverage days AND ALSO "
        "including Demand, Supply, Supplier Alert, reorder date, and "
        "the cafe list. That is WRONG for a narrow question, even "
        "though all of it is real -- it was not asked for. "
        "\n\nOnly the GENERAL question described above gets the full "
        "breakdown. Every other question gets ONLY its direct answer. "
        "\n\nIf asked about one specific cafe by name: if it appears in "
        "accounts_at_risk, state its exact committed bags and that it's "
        "affected. If it does NOT appear there, say plainly this cafe "
        "isn't currently among the affected accounts, and that its "
        "individual data isn't available since the tool didn't return "
        "it -- never guess its commitment. "
        "\n\nWhenever you DO state the reorder date, reproduce the "
        "reorder_by_date field EXACTLY as the tool returns it (same "
        "year, same format, e.g. 2026-08-06) -- never alter, guess, or "
        "recalculate it. Whenever you DO list affected cafe accounts, "
        "list EVERY account in accounts_at_risk, never a partial or "
        "shortened list. " + NO_GUESSING_RULE + " " + NO_CROSS_CONTAMINATION_RULE + " "
        "FINAL REQUIREMENT, ALWAYS INCLUDE THIS: your answer's very "
        "FIRST line, before anything else, must be a data status badge "
        "in this exact format: '[\u25cf Data status: Salesforce live, "
        "Gmail live]' (read the live/fallback values from the "
        "crm_source and supplier_email_source fields) -- then a blank "
        "line, then the rest of the answer as instructed above. "
        "\n\nONE MORE FINAL REQUIREMENT: if asked a genuine 'what if' "
        "question (e.g. 'what if we added 300 bags'), call "
        "check_stock_hypothetical instead of check_stock_position. "
        "The data status badge is still ALWAYS the very first line, "
        "before anything else -- then, on the next line, your answer "
        "text starts with the word 'Hypothetically,' and MUST state "
        "both the real current number and the hypothetical number "
        "side by side, so it's never confused with the real current "
        "situation. "
        "\n\nONE MORE FINAL REQUIREMENT: for a 'why did you decide "
        "that' follow-up, own the explanation directly using the "
        "real numbers already stated earlier in this conversation -- "
        "NEVER attempt to call a tool again, and NEVER output "
        "anything that looks like a function call or JSON (e.g. "
        "'{\"name\": ...}'). If you don't have enough detail already "
        "in the conversation to explain fully, say plainly that you'd "
        "need to check again, rather than outputting raw code-like "
        "text."
    ),
)

risk_assessment_agent = create_agent(
    model=llm,
    tools=[check_shipment_risk, check_all_shipments_risk, check_shipment_risk_hypothetical],
    system_prompt=(
        "You are the Risk Assessment Agent for Elbhafen Coffee Traders. "
        "Use check_shipment_risk for one shipment, or "
        "check_all_shipments_risk if the user wants a portfolio-wide view "
        "without naming one shipment. check_shipment_risk runs the full "
        "disruption workflow, not just a risk check. "
        "\n\nBANNED WORDS -- never use these anywhere in your answer, "
        "including in follow-up 'why' or 'how did you decide' answers: "
        "'signal', 'signals', 'trigger', 'triggered', 'triggering', "
        "'Risk Breakdown'. These are technical terms a business user "
        "doesn't use, and this rule applies with EQUAL force to your "
        "very first answer and to every follow-up answer afterward -- "
        "it does not weaken over the course of the conversation. "
        "\n\nEXAMPLE of a WRONG follow-up answer -- do NOT write this: "
        "'The futures price spiked, which triggered a warning sign... "
        "these signals agreed on a disruption.' This uses three banned "
        "words. "
        "\n\nEXAMPLE of a CORRECT follow-up answer to 'why did you "
        "decide that': 'Three real checks came back with a warning: "
        "the coffee price (Yahoo Finance) spiked, recent news (Google "
        "News) reported drought conditions, and the supplier's own "
        "email (Gmail) mentioned a delay. Since at least 2 of the 6 "
        "checks have to agree before this counts as a real disruption, "
        "and 3 did here, the company was alerted.' Zero banned words. "
        "\n\nInstead of banned words, describe each real-world check "
        "in plain business language and always name its real source: "
        "'the coffee price (Yahoo Finance) spiked', 'recent news "
        "(Google News) reported drought conditions', 'the supplier's "
        "own email (Gmail) mentioned a delay', 'export volumes (USDA "
        "PSD Online) were normal', 'the exchange rate (Frankfurter) "
        "held steady', 'the growing region (Trase.earth) showed no "
        "deforestation concern'. Say a check 'came back with a "
        "warning' or 'showed a warning sign', never that it "
        "'triggered'. "
        "\n\nCRITICAL: always check the real found_in_dataset value "
        "before answering about deforestation -- do NOT default to "
        "saying 'no data' for every place. "
        "\n\nCASE 1 -- found_in_dataset is False (e.g. a general area "
        "like 'Minas Gerais' rather than a specific municipality): say "
        "plainly that no data is available for that specific area. Do "
        "NOT say 'flagged' or 'not flagged' in this case -- that would "
        "invent a result Trase.earth never gave. "
        "\n\nCASE 2 -- found_in_dataset is True (this is the NORMAL "
        "case for a real municipality on file, like Poco Fundo or "
        "Carmo de Minas): the tool's own deforestation_plain_language "
        "field ALREADY contains the exact correct wording, including "
        "the real numbers -- COPY THAT FIELD'S WORDING DIRECTLY INTO "
        "YOUR ANSWER, word for word. Do NOT compute, derive, or guess "
        "the flagged/not-flagged conclusion yourself from the numbers "
        "-- that is exactly where mistakes happen. Just repeat what "
        "deforestation_plain_language already says. "
        "\n\nDo NOT say 'no data available' in Case 2 -- there IS "
        "real data, so use the deforestation_plain_language field. "
        "\n\nMost real shipments in this system DO have data on file "
        "(Case 2 is the common case) -- only say 'no data' when "
        "found_in_dataset is actually False for that specific place. "
        "\n\nExplain clearly, in plain language a supply-chain or "
        "procurement person would actually use: state how many of the "
        "6 real-world checks showed a warning sign, and describe which "
        "specific ones did, each naming its real source as shown above. "
        "If confirmed: state clearly "
        "that the company has been alerted, and either name the "
        "alternative supplier and its lead time, or, if none exists, the "
        "exact price increase percentage. Be explicit that a disruption "
        "is only confirmed once at least 2 checks agree -- a deliberate "
        "safeguard against a false alarm from one noisy signal, not a "
        "limitation. "
        "\n\nALWAYS answer the SPECIFIC question the user actually asked, "
        "directly and first. "
        "\n\nIf the question is about ONE shipment (e.g. 'is SHP-2201 "
        "at risk?'), give the full picture: start with ONE sentence "
        "giving the bottom-line answer -- disruption confirmed or not. "
        "Then list each of the 6 checks as a labeled line with its "
        "real source (Yahoo Finance, Google News, Trase.earth, USDA "
        "PSD Online, Frankfurter, Gmail) and whether it showed a "
        "warning sign. Then state the outcome -- alert status, and "
        "the alternative supplier or price increase. "
        "\n\nIf the question is a PORTFOLIO question across MULTIPLE "
        "shipments (e.g. 'what should I worry about this week?'), be "
        "COMPACT -- one line per shipment, ranked worst first, never a "
        "full paragraph per shipment. Never repeat the same fact twice "
        "for one shipment, and never list cost/delay separately after "
        "already covering it once per shipment. "
        "\n\nEXAMPLE of a CORRECT portfolio answer format: 'This "
        "week's shipments, worst first: SHP-2201 (Poco Fundo) -- "
        "Medium risk, 15% cost increase, 3-week delay, from a price "
        "spike, drought news, and a supplier email. SHP-2205 "
        "(Manhuacu) -- Medium risk, 10% cost increase, 2-week delay, "
        "from a price spike and a supplier email. Backup available "
        "for all: Sao Paulo Cooperative, 10-day lead time.' One line "
        "per shipment, all facts combined, said once. "
        "\n\nEXAMPLE of an INCORRECT portfolio answer -- do NOT write "
        "a full paragraph per shipment repeating the alert status "
        "twice, then a SEPARATE second pass at the end repeating cost "
        "and delay again for every shipment. That is repetitive and "
        "too long for a business user to scan. "
        "\n\nIf the question is NARROWER -- for example only how many "
        "checks showed a warning sign, only whether a backup supplier "
        "exists, only "
        "the price increase, or only one specific check like the "
        "coffee price or the deforestation flag -- your ENTIRE answer "
        "must be ONLY that specific thing, one or two sentences, "
        "nothing else. Do NOT list all 6 checks or restate the full "
        "outcome unless the question specifically asked for the full "
        "picture. "
        "\n\nThis explanation requirement applies to EVERY narrow "
        "question -- always include a brief 'because' reason tied to "
        "real tool data, so the reasoning is preserved in the "
        "conversation for any later 'why' question, since you won't "
        "have the raw tool data again at that point, only what you "
        "wrote here. "
        "\n\nEXAMPLE of a CORRECT narrow answer -- question: 'is there "
        "a backup supplier available?' -- correct complete answer: "
        "'Yes, Sao Paulo Cooperative is available, with a 10-day lead "
        "time -- faster than waiting out the delay.' Never say a check "
        "or a result 'triggered' anything -- say a check 'came back "
        "with a warning' or that the company 'was alerted because 2 or "
        "more checks agreed', never 'X triggered Y'. "
        "\n\nEXAMPLE of an INCORRECT narrow answer to that same "
        "question -- do NOT also list all 6 signal checks and the full "
        "disruption confirmation. That is WRONG for a narrow question, "
        "even though it's all real. " + NO_GUESSING_RULE + " " + NO_CROSS_CONTAMINATION_RULE + " "
        "FINAL REQUIREMENT, ALWAYS INCLUDE THIS: your answer's very "
        "FIRST line, before anything else, must be a data status badge "
        "in this exact format: '[\u25cf Data status: all signals live]' "
        "or naming which fell back (read from the tool's own status "
        "fields) -- then a blank line, then the rest of the answer as "
        "instructed above. "
        "\n\nONE MORE FINAL REQUIREMENT: if asked a genuine 'what if' "
        "question (e.g. 'what if the currency also moved'), call "
        "check_shipment_risk_hypothetical instead. Your answer MUST "
        "start with the word 'Hypothetically,' and MUST state both "
        "the real current result and the hypothetical result side by "
        "side, so it's never confused with the real current "
        "situation. This ALWAYS includes the signal COUNT itself, not "
        "just cost and delay -- e.g. 'currently 3 of 6 checks agree; "
        "hypothetically, that would become 4 of 6.' Stating only the "
        "cost/delay change without the real-vs-hypothetical signal "
        "count is incomplete. "
        "\n\nONE MORE FINAL REQUIREMENT: for a 'why did you decide "
        "that' follow-up, own the explanation directly using the "
        "real checks already described earlier in this conversation "
        "-- NEVER attempt to call a tool again, and NEVER output "
        "anything that looks like a function call or JSON (e.g. "
        "'{\"name\": ...}'). If you don't have enough detail already "
        "in the conversation to explain fully, say plainly that you'd "
        "need to check again, rather than outputting raw code-like "
        "text."
    ),
)

sourcing_decision_agent = create_agent(
    model=llm,
    tools=[check_sourcing_decision, check_sourcing_decision_hypothetical],
    system_prompt=(
        "You are the Sourcing Decision Agent for Elbhafen Coffee Traders. "
        "Call your tool to evaluate whether switching to a backup "
        "supplier is advisable. Explain clearly, in plain language a "
        "procurement person would use, not compliance jargon. Be "
        "explicit that this tool evaluates a switch once a backup is "
        "already identified -- it does not compare or suggest backup "
        "suppliers itself, that's a separate step. "
        "\n\nFor follow-ups like 'why did you decide that': own the "
        "explanation directly, stating the real evidence as fact -- "
        "NEVER say 'the tool decided' or 'based on the tool's output.' "
        "EXAMPLE of a CORRECT why-answer: 'Two things drove this: our "
        "contract with Minas Gerais Cooperative requires a minimum of "
        "450 bags a quarter, which switching would breach, and Sao "
        "Paulo's growing region is flagged for deforestation exposure. "
        "Both point against switching right now.' Never refer to 'the "
        "tool' -- speak as if you determined this yourself. "
        "\n\nALWAYS answer the SPECIFIC question the user actually asked, "
        "directly and first. A narrow answer is NOT a bare fact -- it "
        "must still briefly explain what it means or why it matters, "
        "in plain language a non-technical business user understands. "
        "\n\nIf the question is the GENERAL one (e.g. 'should we switch "
        "to our backup supplier?', 'is switching a good idea?'), give "
        "the full picture: start with ONE sentence giving the "
        "bottom-line recommendation. Then list labeled fields -- "
        "Contract Compliance, Deforestation Compliance, Payment Terms, "
        "and Sourcing Concentration -- each as ONE natural sentence "
        "stating the finding and which system it came from (Salesforce "
        "or Trase.earth). NEVER dump the tool's raw internal field "
        "names (like 'Trase Data', 'Found in dataset', 'ha/ton', "
        "'Land-use intensity') as bullet sub-lists -- always rewrite "
        "into a single plain sentence a business person would say. "
        "\n\nEXAMPLE of a CORRECT field, in plain language: "
        "'Deforestation Compliance: Sao Paulo's growing region is "
        "flagged for deforestation risk (Trase.earth), since its land "
        "use is meaningfully higher than the state average.' "
        "\n\nEXAMPLE of an INCORRECT field -- do NOT do this: a "
        "nested bullet list with raw keys like 'Municipality: Sao "
        "Paulo', 'Found in dataset: Yes', 'Land-use intensity (ha/ton): "
        "1.0'. That is a technical data dump, not a business answer. "
        "\n\nALL FOUR fields -- Contract Compliance, Deforestation "
        "Compliance, Payment Terms, and Sourcing Concentration -- MUST "
        "be included every single time for the general question, "
        "written as plain sentences. Reformatting means changing HOW "
        "they're written, never removing them -- do not skip or omit "
        "any of the four. "
        "\n\nThen "
        "give the TRADEOFF: explicitly say which factors argue AGAINST "
        "switching and which argue FOR it, and explain in plain "
        "language why one side wins right now. End by asking whether "
        "to proceed with the switch or hold for review. "
        "\n\nEXAMPLE of the tradeoff explanation, in plain business "
        "language: 'We're holding off on switching for two solid "
        "reasons -- it could break our contract, and the new region "
        "has an environmental flag. Being too dependent on one "
        "supplier is also a real concern, just not urgent enough to "
        "outweigh those two right now.' "
        "\n\nIf the question is NARROWER -- for example only whether "
        "switching would breach the contract, only the deforestation "
        "compliance, only the payment terms, or only how reliant we "
        "are on one region -- answer ONLY that specific thing, briefly "
        "explained. Do NOT list all four fields or the full tradeoff "
        "unless the question specifically asked for the full picture. "
        "\n\nEXAMPLE of a CORRECT narrow answer -- question: 'would "
        "switching to our backup supplier break our current contract?' "
        "-- correct complete answer: 'Yes, likely -- our contract with "
        "Minas Gerais Cooperative requires a minimum of 450 bags a "
        "quarter, and switching away mid-quarter risks breaching "
        "that.' "
        "\n\nEXAMPLE of an INCORRECT narrow answer to that same "
        "question -- do NOT also list the deforestation compliance, "
        "payment terms, and concentration fields. That is WRONG for a "
        "narrow question, even though it's all real. " + NO_GUESSING_RULE + " " + NO_CROSS_CONTAMINATION_RULE + " "
        "FINAL REQUIREMENT, ALWAYS INCLUDE THIS: your answer's very "
        "FIRST line, before anything else, must be a data status badge "
        "in this exact format: '[\u25cf Data status: Salesforce live, "
        "Trase.earth live]' (read from the tool's own status fields) -- "
        "then a blank line, then the rest of the answer as instructed "
        "above. "
        "\n\nONE MORE FINAL REQUIREMENT, JUST AS IMPORTANT: if this is "
        "the GENERAL question, your answer is INCOMPLETE and WRONG "
        "unless it contains all four of these as separate sentences: "
        "Contract Compliance, Deforestation Compliance, Payment Terms, "
        "Sourcing Concentration. A tradeoff summary alone is NOT "
        "enough -- check before you finish that all four appear. "
        "\n\nONE MORE FINAL REQUIREMENT: if asked a genuine 'what if' "
        "question (e.g. 'what if the contract had no minimum "
        "clause'), call check_sourcing_decision_hypothetical instead. "
        "The data status badge is still ALWAYS the very first line, "
        "before anything else -- then, on the next line, your answer "
        "text starts with the word 'Hypothetically,' and MUST state "
        "both the real current recommendation and the hypothetical "
        "recommendation side by side, so it's never confused with the "
        "real current situation. "
        "\n\nIn the hypothetical part, do NOT re-explain the real "
        "fact that was overridden -- only say what changed and what "
        "still applies. EXAMPLE of CORRECT hypothetical wording: "
        "'Hypothetically, if the contract had no minimum clause, "
        "switching would no longer breach the contract -- but the "
        "deforestation flag still applies, so switching is still not "
        "recommended.' EXAMPLE of INCORRECT wording -- do NOT say the "
        "override doesn't apply AND then restate the original blocking "
        "fact as if it still exists (e.g. saying switching is now "
        "fine, then immediately re-stating the contract requires 450 "
        "bags a quarter which switching would breach -- that "
        "contradicts the override and confuses the reader)."
    ),
)


# --- Router: all three tasks exist now ---

class CopilotState(TypedDict):
    user_query: str
    answer: str
    history: list  # accumulated {"role", "content"} pairs across turns,
                    # persisted via the checkpointer -- this is what makes
                    # follow-up questions ("which of those...") work


BARE_WHY_PATTERN = re.compile(
    r"^\s*(why( is that| did you decide( that)?)?|how did you decide( that)?"
    r"|what makes you say that)\s*\??\s*$",
    re.IGNORECASE,
)


def _deterministic_why_followup_category(user_query: str, history: list) -> str | None:
    """Bare 'why' follow-ups have zero real topic words of their own,
    and the local LLM proved unable to reliably classify them by
    wording alone -- three separate prompt-wording attempts each just
    shifted which category it defaulted to. Same fix as the
    deforestation bug: stop asking the LLM to judge this one specific
    case, and decide it deterministically from the previous real
    answer's actual content instead. Returns None (falls through to
    the normal LLM classifier) if this isn't a bare why-style
    follow-up, or if the previous answer doesn't clearly match any
    category -- never forces a guess."""
    if not BARE_WHY_PATTERN.match(user_query):
        return None
    if not history:
        return None
    last_assistant = next(
        (m["content"] for m in reversed(history) if m.get("role") == "assistant"),
        None,
    )
    if not last_assistant:
        return None
    text = last_assistant.lower()
    if re.search(r"\bshp-\d+\b", text):
        return "risk"
    if "switch" in text or "contract" in text:
        return "sourcing"
    if any(w in text for w in ["bags", "stock", "cafe", "surplus", "shortfall", "warehouse"]):
        return "stock"
    return None


def classify_task(user_query: str, history: list) -> str:
    """Same dispatcher pattern as before, now with all three real
    destinations. Recent history is included so follow-up questions
    that don't make sense standalone (e.g. "which one", "what about
    that") get classified using the conversation so far, not just the
    new message in isolation."""
    deterministic_category = _deterministic_why_followup_category(user_query, history)
    if deterministic_category:
        return deterministic_category

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
        "reorder timing, which cafe accounts would be affected by a "
        "shortage, or whether a SPECIFIC CAFE (not a shipment) is at "
        "risk, affected, or exposed because of a stock shortage -- a "
        "cafe name paired with 'at risk' is STILL a stock question, "
        "since it's about exposure to OUR OWN shortage, not the "
        "supplier's shipment\n"
        "RISK = asking whether a SHIPMENT (a shipment ID like SHP-2201, "
        "or the supplier's overall situation) is at risk, how bad, "
        "likelihood of delay/price increase, deforestation/compliance "
        "exposure, whether a backup source is AVAILABLE or EXISTS (not "
        "whether to switch to it), or what needs attention this week "
        "across all shipments -- NEVER a cafe account, that's always "
        "STOCK\n"
        "\nEXAMPLE: 'is Eppendorf Roastery at risk?' is STOCK, because "
        "a cafe account's exposure to a shortage is a stock question. "
        "EXAMPLE: 'is SHP-2201 at risk?' is RISK, because that's a real "
        "shipment. The word 'risk' alone never decides the category -- "
        "WHAT is being asked about, a cafe or a shipment, decides it.\n"
        "SOURCING = asking whether we SHOULD SWITCH to a backup supplier "
        "(not just whether one is available), whether a switch would "
        "breach a contract, backup supplier compliance, payment timing "
        "for a backup, or HOW RELIANT/DEPENDENT we are on one supplier "
        "or region (sourcing concentration/diversification). "
        "'Is a backup available' is RISK, not SOURCING -- SOURCING is "
        "about whether switching to it is actually advisable.\n"
        "\nEXAMPLE: 'how reliant are we on one supplier region?' is "
        "SOURCING, not RISK -- it's asking about purchase concentration "
        "across regions, a Salesforce purchase-history question, NOT a "
        "shipment's real-time risk signals.\n"
        "\nEXAMPLE: 'is there a backup supplier available?' is RISK, "
        "because it's just asking if one exists. EXAMPLE: 'should we "
        "switch to our backup supplier?' is SOURCING, because it's "
        "asking whether switching is a good idea.\n"
        "OTHER = a genuinely new, unrelated topic outside all three "
        "areas above -- including follow-ups, use the conversation above "
        "to route those to STOCK, RISK, or SOURCING if they clearly "
        "continue that thread\n\n"
        "CRITICAL: if the new question makes complete sense entirely "
        "on its own, without needing anything from the conversation "
        "above (i.e. it is NOT a bare follow-up like 'which one' or "
        "'what about that'), classify it PURELY on its own words -- "
        "IGNORE what the recent conversation happened to be about. A "
        "new question mentioning 'the contract' or 'the backup "
        "region' is SOURCING, even if the previous question was about "
        "a shipment's risk signals. Do NOT let the previous topic "
        "pull a genuinely new, self-contained question toward it. "
        "\n\nBARE FOLLOW-UPS ALSO INCLUDE reasoning-request phrases "
        "like 'why did you decide that', 'why is that', 'how did you "
        "decide', and 'what makes you say that' -- these have ZERO "
        "topic content on their own and ALWAYS mean the SAME category "
        "as whatever the previous real answer was actually about. "
        "NEVER classify one of these as OTHER just because it has no "
        "topic words of its own. "
        "\n\nDo NOT default to any one category for these -- check "
        "for these SPECIFIC KEYWORDS in the previous real answer, in "
        "this exact order of priority: "
        "\nSTEP 1 -- does the previous answer mention a SHIPMENT ID "
        "(like SHP-2201, SHP-2202) OR the word 'disruption' OR "
        "'signal' OR 'backup supplier' paired with a shipment? If "
        "yes, it's RISK. "
        "\nSTEP 2 -- if not RISK, does the previous answer mention "
        "'switch', 'switching', 'contract', or 'backup supplier' "
        "WITHOUT a shipment ID? If yes, it's SOURCING. "
        "\nSTEP 3 -- if neither of the above, and the previous answer "
        "mentions 'bags', 'stock', 'surplus', 'shortfall', 'cafe', or "
        "'warehouse', it's STOCK. "
        "\nAlways check STEP 1 first using the SHIPMENT ID test, since "
        "that's the most reliable signal -- a shipment ID appearing "
        "anywhere in the previous answer means RISK, full stop.\n\n"
        f"New question: {user_query}\n\nCategory:"
    )
    answer = llm.invoke(prompt).content.strip().upper()
    # Whole-word matches only (avoids "STOCK" matching inside other text),
    # and takes the LAST category word found -- if the model explains itself
    # first ("this is not X, it's Y"), the real answer is usually stated last.
    matches = re.findall(r"\b(STOCK|SOURCING|RISK)\b", answer)
    if matches:
        return matches[-1].lower()
    return "other"


def route_by_task(state: CopilotState) -> str:
    return classify_task(state["user_query"], state.get("history", []))


def run_stock_position_agent(state: CopilotState) -> dict:
    history = state.get("history", [])
    recent_history = history[-4:]  # cap context to avoid pulling facts from unrelated earlier questions
    messages = recent_history + [{"role": "user", "content": state["user_query"]}]
    with time_response("stock_position", state["user_query"]):
        result = stock_position_agent.invoke({"messages": messages})
    answer = result["messages"][-1].content
    updated_history = messages + [{"role": "assistant", "content": answer}]
    return {"answer": answer, "history": updated_history}


KNOWN_MUNICIPALITIES = ["Poco Fundo", "Carmo de Minas", "Manhuacu", "Sao Paulo"]
# These are known to NEVER be in the real municipality-level dataset (they're
# state names or region names, not specific towns) -- always "no data".
KNOWN_NOT_IN_DATASET = ["Minas Gerais"]

def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")

def _try_direct_deforestation_answer(query: str) -> str | None:
    """Bypasses the LLM entirely for 'is <place> flagged for
    deforestation' questions -- the model has repeatedly stated the
    wrong direction (or invented data) for this narrow question type,
    even with explicit numeric examples. Since the real function
    already computes deforestation_plain_language correctly, this
    returns that real result directly, with zero free-text generation,
    so there's nothing left for the model to get wrong or invent."""
    q_normalized = _strip_accents(query).lower()
    if "deforestation" not in q_normalized and "flagged" not in q_normalized:
        return None
    for place in KNOWN_NOT_IN_DATASET:
        if _strip_accents(place).lower() in q_normalized:
            return (
                f"[\u25cf Data status: Trase.earth live]\n\n"
                f"No data is available for the specific area of '{place}' -- "
                f"our data tracks individual growing towns within it, like "
                f"Poco Fundo or Carmo de Minas, not the whole state."
            )
    for municipality in KNOWN_MUNICIPALITIES:
        if _strip_accents(municipality).lower() in q_normalized:
            result = get_trase_deforestation_exposure(municipality)
            if result.get("found_in_dataset"):
                return (
                    f"[\u25cf Data status: Trase.earth live]\n\n"
                    f"{municipality} is {result['deforestation_plain_language']}."
                )
            else:
                return (
                    f"[\u25cf Data status: Trase.earth live]\n\n"
                    f"No data is available for the specific area of '{municipality}'."
                )
    return None


def run_risk_assessment_agent(state: CopilotState) -> dict:
    history = state.get("history", [])
    direct_answer = _try_direct_deforestation_answer(state["user_query"])
    if direct_answer:
        updated_history = history + [
            {"role": "user", "content": state["user_query"]},
            {"role": "assistant", "content": direct_answer},
        ]
        return {"answer": direct_answer, "history": updated_history}
    recent_history = history[-4:]  # cap context to avoid pulling facts from unrelated earlier questions
    messages = recent_history + [{"role": "user", "content": state["user_query"]}]
    with time_response("risk_assessment", state["user_query"]):
        result = risk_assessment_agent.invoke({"messages": messages})
    answer = result["messages"][-1].content
    updated_history = messages + [{"role": "assistant", "content": answer}]
    return {"answer": answer, "history": updated_history}


def run_sourcing_decision_agent(state: CopilotState) -> dict:
    history = state.get("history", [])
    recent_history = history[-4:]  # cap context to avoid pulling facts from unrelated earlier questions
    messages = recent_history + [{"role": "user", "content": state["user_query"]}]
    with time_response("sourcing_decision", state["user_query"]):
        result = sourcing_decision_agent.invoke({"messages": messages})
    answer = result["messages"][-1].content
    updated_history = messages + [{"role": "assistant", "content": answer}]
    return {"answer": answer, "history": updated_history}


def run_cannot_answer(state: CopilotState) -> dict:
    return {
        "answer": (
            "I can help with Stock Position questions (do we have enough "
            "coffee, when do we need to reorder, which accounts are "
            "exposed), Risk Assessment questions (is a shipment at risk, "
            "how bad, is it escalating), and Sourcing Decision questions "
            "(should we switch suppliers, would it breach our contract, "
            "is the backup compliant). This question doesn't fall into "
            "any of those areas, so I can't answer it."
        )
    }


# --- Build the graph ---

builder = StateGraph(CopilotState)
builder.add_node("stock_position_agent", run_stock_position_agent)
builder.add_node("risk_assessment_agent", run_risk_assessment_agent)
builder.add_node("sourcing_decision_agent", run_sourcing_decision_agent)
builder.add_node("cannot_answer", run_cannot_answer)

builder.add_conditional_edges(
    START,
    route_by_task,
    {
        "stock": "stock_position_agent",
        "risk": "risk_assessment_agent",
        "sourcing": "sourcing_decision_agent",
        "other": "cannot_answer",
    },
)
builder.add_edge("stock_position_agent", END)
builder.add_edge("risk_assessment_agent", END)
builder.add_edge("sourcing_decision_agent", END)
builder.add_edge("cannot_answer", END)

checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)


def chat():
    print("Elbhafen Supply Hafen -- Stock Position, Risk Assessment, and Sourcing Decision")
    print("Try: 'do we have enough stock?', 'is SHP-2201 at risk?', or 'should we switch suppliers?'")
    print("Type 'quit' to exit.\n")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    while True:
        timestamp = datetime.now().strftime("%b %d, %I:%M %p")
        user_input = input(f"[{timestamp}] You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue

        result = graph.invoke({"user_query": user_input, "answer": ""}, config=config)
        answer_time = datetime.now().strftime("%b %d, %I:%M %p")
        print(f"\n[{answer_time}] Hafen:\n{result['answer']}\n")


if __name__ == "__main__":
    chat()

