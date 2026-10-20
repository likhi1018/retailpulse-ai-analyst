"""RetailPulse AI Analyst — ask the Olist star schema questions in plain English."""
import os

import streamlit as st

from app.charts import suggest_chart
from app.db import TABLES, Database
from app.engine import Analyst
from app.llm import LLMClient

st.set_page_config(page_title="RetailPulse AI Analyst", page_icon="📊", layout="wide")

EXAMPLES = [
    "What was total revenue and average order value in 2018?",
    "Show monthly revenue for 2017 and 2018",
    "Top 10 categories by revenue with their share of total",
    "Which 5 states have the worst late-delivery rate?",
    "How does average review score change with delivery delay?",
    "What share of customers are repeat buyers?",
    "Revenue by RFM segment",
    "Which payment types are most common?",
]


@st.cache_resource
def get_analyst(api_key: str, base_url: str, model: str) -> Analyst:
    return Analyst(LLMClient(api_key=api_key, base_url=base_url, model=model), Database())


with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("API key", value=os.getenv("LLM_API_KEY", ""), type="password")
    base_url = st.text_input("Base URL", value=os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/"))
    model = st.text_input("Model", value=os.getenv("LLM_MODEL", "gemini-3.8-flash"))
    st.caption("Works with any OpenAI-compatible API (Gemini, OpenAI, Groq, Ollama).")
    st.divider()
    st.subheader("Try asking")
    for q in EXAMPLES:
        if st.button(q, width="stretch"):
            st.session_state.pending = q
    st.divider()
    with st.expander("Tables available"):
        st.markdown("\n".join(f"- `{t}`" for t in TABLES))
    if st.button("Clear conversation"):
        st.session_state.messages = []

st.title("RetailPulse AI Analyst")
st.caption("Natural-language questions → validated DuckDB SQL → results, chart and summary. "
           "Data: Olist Brazilian e-commerce, 2016–2018 (R$).")

if "messages" not in st.session_state:
    st.session_state.messages = []


def render(ans):
    if not ans.ok:
        st.error(f"Couldn't answer after {ans.attempts} attempt(s): {ans.error}")
        with st.expander("Last SQL tried"):
            st.code(ans.sql, language="sql")
        return
    if ans.summary:
        st.markdown(ans.summary)
    chart = suggest_chart(ans.data)
    if chart:
        kind, x, y = chart
        data = ans.data.set_index(x)[[y]]
        if kind == "line":
            st.line_chart(data)
        else:
            st.bar_chart(data)
    st.dataframe(ans.data, width="stretch", hide_index=True)
    with st.expander(f"SQL · {ans.attempts} attempt(s) · {ans.seconds}s"):
        st.code(ans.sql, language="sql")
    st.download_button("Download CSV", ans.data.to_csv(index=False), "result.csv", key=f"dl{id(ans)}")


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            render(m["answer"])

question = st.chat_input("Ask a question about sales, customers, delivery or reviews…")
question = question or st.session_state.pop("pending", None)

if question:
    if not api_key:
        st.warning("Add an API key in the sidebar first.")
        st.stop()
    analyst = get_analyst(api_key, base_url, model)
    with st.chat_message("user"):
        st.markdown(question)
    history = []
    for m in st.session_state.messages[-6:]:
        if m["role"] == "user":
            history.append({"role": "user", "content": m["content"]})
        elif m["answer"].ok:
            history.append({"role": "assistant", "content": f"```sql\n{m['answer'].sql}\n```"})
    with st.chat_message("assistant"):
        with st.spinner("Writing and checking SQL…"):
            ans = analyst.ask(question, history=history)
        render(ans)
    st.session_state.messages += [{"role": "user", "content": question},
                                  {"role": "assistant", "answer": ans}]
