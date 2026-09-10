import streamlit as st
import uuid
import re
from datetime import datetime
from graph import graph, classify_task

st.set_page_config(page_title="Elbhafen Supply Hafen", page_icon="☕", layout="wide")

col1, col2 = st.columns([3, 1])
with col1:
    st.title("☕ Elbhafen Supply Hafen")
    st.caption("Stock Position · Risk Assessment · Sourcing Decision")
with col2:
    st.write("")
    st.write(f"**{datetime.now().strftime('%A, %b %d')}**")
    st.write(datetime.now().strftime("%I:%M %p"))
st.divider()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "history" not in st.session_state:
    st.session_state.history = []


def extract_metrics(text: str) -> list:
    """Pulls out ONLY real 'Label: number bags/%' pairs that already
    exist verbatim in the real answer text -- never invents or guesses
    a value. If nothing matches, returns an empty list and the full
    real text is shown underneath regardless."""
    pattern = r"([A-Z][a-zA-Z ]{2,30}):\s*([\d,]+)\s*(bags|%|days)"
    found = re.findall(pattern, text)
    seen = set()
    metrics = []
    for label, value, unit in found:
        label = label.strip()
        if label in seen:
            continue
        seen.add(label)
        metrics.append((label, f"{value} {unit}"))
    return metrics[:4]


def render_answer(full_text: str):
    """Displays exactly what the real agent said. The badge becomes a
    green success box, real labeled numbers already in the text are
    shown as metric cards, the bottom-line sentence shows immediately,
    and everything after it collapses into an expander -- real
    progressive disclosure, using only real text that's already there."""
    lines = full_text.split("\n")
    first_line = lines[0]
    body = full_text
    if first_line.startswith("[") and "Data status:" in first_line:
        body = full_text[len(first_line):].strip()
        st.success(first_line.strip("[]"))

    metrics = extract_metrics(body)
    if metrics:
        cols = st.columns(len(metrics))
        for col, (label, value) in zip(cols, metrics):
            col.metric(label, value)

    paragraphs = body.split("\n\n")
    summary = paragraphs[0]
    rest = "\n\n".join(paragraphs[1:])
    st.markdown(summary)
    if rest.strip():
        with st.expander("View full breakdown", expanded=True):
            st.markdown(rest)


for msg in st.session_state.messages:
    avatar = "☕" if msg["role"] == "assistant" else "🗣️"
    with st.chat_message(msg["role"], avatar=avatar):
        if msg["role"] == "assistant":
            render_answer(msg["content"])
        else:
            st.markdown(msg["content"])

if prompt := st.chat_input("Ask about stock, risk, or sourcing..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="🗣️"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar="☕"):
        st.markdown("""
            <style>
            .thinking-dots { display: inline-flex; gap: 5px; align-items: center; }
            .thinking-dots span {
                width: 8px; height: 8px; border-radius: 50%;
                background-color: #d4a24c; display: inline-block;
                animation: hafen-bounce 1.2s infinite ease-in-out both;
            }
            .thinking-dots span:nth-child(1) { animation-delay: -0.32s; }
            .thinking-dots span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes hafen-bounce {
                0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
                40% { transform: scale(1); opacity: 1; }
            }
            </style>
            <div class="thinking-dots"><span></span><span></span><span></span></div>
        """, unsafe_allow_html=True)
        with st.status("Thinking...", expanded=True) as status:
            st.write("Reading your question...")
            category = classify_task(prompt, st.session_state.history)
            task_names = {
                "stock": "Checking Stock Position -- Salesforce, Shippo, and Gmail.",
                "risk": "Checking Risk Assessment -- this involves 6 real sources: "
                        "Yahoo Finance, Google News, Trase.earth, USDA PSD Online, "
                        "Frankfurter, and Gmail.",
                "sourcing": "Checking Sourcing Decision -- Salesforce and Trase.earth.",
                "other": "This doesn't match any of the three tasks.",
            }
            st.write(task_names.get(category, "Working..."))

            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            result = graph.invoke({"user_query": prompt, "answer": ""}, config=config)
            answer = result["answer"]
            st.session_state.history = result.get("history", st.session_state.history)
            status.update(label="Done", state="complete", expanded=False)

        render_answer(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})

with st.sidebar:
    st.markdown("### Try asking")
    st.markdown("""
**Stock Position**
- Do we have enough stock?
- When do we need to reorder?

**Risk Assessment**
- Is SHP-2201 at risk?
- What should I worry about this week?

**Sourcing Decision**
- Should we switch to our backup supplier?

**What if...**
- What if we added 300 bags to the warehouse?
- What if the currency also moved for SHP-2201?
- What if the contract had no minimum order clause?
""")
    st.divider()
    if st.button("Start new conversation", type="primary", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.history = []
        st.rerun()
