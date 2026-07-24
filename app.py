"""
Financial Risk Signal Aggregator — Streamlit dashboard.

Data in (CSV + JSON + free text)  ->  rules + LLM  ->  prioritised risk view.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

import config
from src import llm
from src.ingestion import build_entities, load_alerts, load_customers, load_transactions
from src.scoring import build_risk_register
from src.schemas import EntityRisk

load_dotenv()

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def md_safe(text: str) -> str:
    """Escape lone $ so Streamlit's markdown renderer doesn't treat dollar
    amounts (e.g. "$250,000") as LaTeX math delimiters."""
    return (text or "").replace("$", "\\$")


TIER_COLORS = {
    "Critical": "#b91c1c",
    "High": "#ea580c",
    "Medium": "#ca8a04",
    "Low": "#16a34a",
}
TIER_ORDER = ["Critical", "High", "Medium", "Low"]

st.set_page_config(
    page_title="Financial Risk Signal Aggregator",
    page_icon="🛡️",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_analysis(
    txns_df: pd.DataFrame, customers: List[Dict[str, Any]], alert_text: str
) -> Dict[str, Any]:
    entities = build_entities(txns_df, customers)
    name_map = {c["customer_id"]: c.get("name", c["customer_id"]) for c in customers}

    # 1) LLM (or fallback) turns unstructured alerts into structured hits.
    hits = llm.extract_alerts(alert_text or "", name_map)

    # 2) Deterministic rules + scoring produce the ranked register.
    register = build_risk_register(entities, hits)

    # 3) LLM (or fallback) writes a rationale + recommended action per entity.
    for er in register:
        profile = entities[er.customer_id]["profile"]
        result = llm.entity_rationale(er, profile)
        er.rationale = result["rationale"]
        er.recommended_action = result["recommended_action"]
        er.confidence = result["confidence"]

    summary = llm.exec_summary(register)
    return {
        "register": register,
        "summary": summary,
        "entities": entities,
        "hits": hits,
        "ai_used": llm.is_available(),
    }


def register_to_df(register: List[EntityRisk]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Rank": i,
                "Customer": er.name,
                "Score": er.score,
                "Tier": er.tier,
                "Signals": er.num_signals,
                "Top Signals": ", ".join(er.signal_codes) or "—",
                "Recommended Action": er.recommended_action or "—",
            }
            for i, er in enumerate(register, 1)
        ]
    )


# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------
def sidebar() -> None:
    st.sidebar.title("🛡️ Risk Aggregator")
    st.sidebar.caption("Structured + unstructured signals → prioritised risk view")

    if llm.is_available():
        st.sidebar.success("Gemini connected — AI reasoning ON")
    else:
        st.sidebar.warning(
            "No Gemini key — running in rules + heuristic fallback mode. "
            "Set GEMINI_API_KEY to enable full AI narrative."
        )

    st.sidebar.subheader("1 · Load data")
    if st.sidebar.button("📂 Load sample dataset", use_container_width=True):
        _load_sample_into_state()

    txn_file = st.sidebar.file_uploader("Transactions (CSV)", type=["csv"])
    cust_file = st.sidebar.file_uploader("Customer records (JSON)", type=["json"])
    alert_text = st.sidebar.text_area(
        "External alerts / adverse media (paste text)",
        value=st.session_state.get("alert_text", ""),
        height=160,
        key="alert_text",
    )

    st.sidebar.subheader("2 · Analyse")
    if st.sidebar.button("▶ Run risk analysis", type="primary", use_container_width=True):
        _run_from_inputs(txn_file, cust_file, alert_text)


def _load_sample_into_state() -> None:
    st.session_state["txns_df"] = load_transactions(
        os.path.join(DATA_DIR, "transactions.csv")
    )
    st.session_state["customers"] = load_customers(
        os.path.join(DATA_DIR, "customers.json")
    )
    st.session_state["alert_text"] = load_alerts(
        os.path.join(DATA_DIR, "external_alerts.txt")
    )
    st.session_state["sample_loaded"] = True
    st.rerun()


def _run_from_inputs(txn_file, cust_file, alert_text) -> None:
    try:
        if txn_file is not None:
            txns_df = load_transactions(txn_file)
        elif "txns_df" in st.session_state:
            txns_df = st.session_state["txns_df"]
        else:
            st.sidebar.error("Provide a transactions CSV (or load the sample dataset).")
            return

        if cust_file is not None:
            customers = load_customers(cust_file)
        elif "customers" in st.session_state:
            customers = st.session_state["customers"]
        else:
            st.sidebar.error("Provide a customers JSON (or load the sample dataset).")
            return

        with st.spinner("Aggregating signals and scoring risk…"):
            st.session_state["result"] = run_analysis(txns_df, customers, alert_text)
    except Exception as exc:  # surface ingestion/format errors to the user
        st.sidebar.error(f"Could not analyse inputs: {exc}")


# ---------------------------------------------------------------------------
# Main views
# ---------------------------------------------------------------------------
def overview_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    counts = {t: sum(1 for e in register if e.tier == t) for t in TIER_ORDER}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Customers", len(register))
    c2.metric("🔴 Critical", counts["Critical"])
    c3.metric("🟠 High", counts["High"])
    c4.metric("🟡 Medium", counts["Medium"])
    c5.metric("🟢 Low", counts["Low"])

    st.subheader("Executive summary")
    tag = "AI-generated" if result["ai_used"] else "auto-generated (no API key)"
    st.info(md_safe(result["summary"]))
    st.caption(f"Summary source: {tag}")

    left, right = st.columns(2)
    with left:
        dist = pd.DataFrame(
            {"Tier": list(counts.keys()), "Count": list(counts.values())}
        )
        fig = px.bar(
            dist, x="Tier", y="Count", color="Tier",
            color_discrete_map=TIER_COLORS, title="Risk tier distribution",
        )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with right:
        scores = pd.DataFrame(
            [{"Customer": e.name, "Score": e.score, "Tier": e.tier} for e in register]
        )
        fig2 = px.bar(
            scores, x="Score", y="Customer", color="Tier", orientation="h",
            color_discrete_map=TIER_COLORS, title="Risk score by customer",
        )
        fig2.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig2, use_container_width=True)


def register_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    st.subheader("Prioritised risk register")
    df = register_to_df(register)

    def _row_style(row):
        color = TIER_COLORS.get(row["Tier"], "#666")
        return [f"background-color: {color}22"] * len(row)

    st.dataframe(
        df.style.apply(_row_style, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        "Ranked by score, then by number of independent signals, then heaviest signal."
    )


def drilldown_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    entities = result["entities"]
    names = [f"{e.name} — {e.tier} ({e.score})" for e in register]
    idx = st.selectbox(
        "Select a customer", range(len(register)), format_func=lambda i: names[i]
    )
    er = register[idx]
    profile = entities[er.customer_id]["profile"]

    head, gauge = st.columns([2, 1])
    with head:
        st.markdown(f"### {er.name}")
        st.markdown(
            f"**Tier:** :{'red' if er.tier in ('Critical','High') else 'orange'}"
            f"[{er.tier}] &nbsp;|&nbsp; **Score:** {er.score}/100 "
            f"&nbsp;|&nbsp; **Recommended action:** {er.recommended_action} "
            f"&nbsp;|&nbsp; **Confidence:** {er.confidence}"
        )
        st.markdown("**Profile**")
        st.json(profile, expanded=False)
    with gauge:
        st.plotly_chart(_score_gauge(er.score, er.tier), use_container_width=True)

    st.markdown("#### AI rationale")
    st.write(md_safe(er.rationale) or "—")

    st.markdown("#### Risk signals & evidence")
    if er.signals:
        st.table(
            pd.DataFrame(
                [
                    {"Signal": s.label, "Points": s.weight, "Evidence": md_safe(s.evidence)}
                    for s in er.signals
                ]
            )
        )
    else:
        st.success("No risk signals triggered — activity matches expected profile.")

    if er.alert_hits:
        st.markdown("#### External alert hits")
        st.table(
            pd.DataFrame(
                [
                    {
                        "Type": h.alert_type,
                        "Severity": h.severity,
                        "Summary": md_safe(h.summary),
                    }
                    for h in er.alert_hits
                ]
            )
        )

    st.markdown("#### Transactions")
    txns = entities[er.customer_id]["txns"]
    if not txns.empty:
        st.dataframe(
            txns[
                ["timestamp", "txn_type", "amount", "counterparty",
                 "counterparty_country", "channel"]
            ],
            use_container_width=True,
            hide_index=True,
        )


def ask_tab(result: Dict[str, Any]) -> None:
    st.subheader("Ask the risk data")
    st.caption("Natural-language questions answered from the risk register (needs Gemini key).")
    q = st.text_input(
        "e.g. Which customers have sanctions exposure? Why is Ravi Menon critical?"
    )
    if q:
        with st.spinner("Thinking…"):
            answer = llm.nl_query(q, result["register"])
        st.write(md_safe(answer))


def export_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    st.subheader("Export results")
    df = register_to_df(register)
    st.download_button(
        "⬇ Download register (CSV)",
        df.to_csv(index=False).encode("utf-8"),
        file_name="risk_register.csv",
        mime="text/csv",
    )
    detailed = [
        {
            "customer_id": e.customer_id,
            "name": e.name,
            "score": e.score,
            "tier": e.tier,
            "recommended_action": e.recommended_action,
            "confidence": e.confidence,
            "rationale": e.rationale,
            "signals": [s.model_dump() for s in e.signals],
            "alert_hits": [h.model_dump() for h in e.alert_hits],
        }
        for e in register
    ]
    st.download_button(
        "⬇ Download full findings (JSON)",
        json.dumps(detailed, indent=2).encode("utf-8"),
        file_name="risk_findings.json",
        mime="application/json",
    )
    st.json(detailed, expanded=False)


def _score_gauge(score: int, tier: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": tier},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": TIER_COLORS.get(tier, "#666")},
                "steps": [
                    {"range": [0, 25], "color": "#dcfce7"},
                    {"range": [25, 50], "color": "#fef9c3"},
                    {"range": [50, 75], "color": "#ffedd5"},
                    {"range": [75, 100], "color": "#fee2e2"},
                ],
            },
        )
    )
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    sidebar()
    st.title("Financial Risk Signal Aggregator")
    st.caption(
        "Aggregates transaction records, account activity and external alerts into a "
        "prioritised, risk-scored view — deterministic rules score, Gemini explains."
    )

    if "result" not in st.session_state:
        st.info(
            "👈 Click **Load sample dataset**, then **Run risk analysis** to see the "
            "prototype end-to-end. You can also upload your own CSV/JSON and paste alerts."
        )
        with st.expander("How scoring works"):
            st.markdown(
                "- **Rules engine** (transparent, in `config.py`) fires weighted signals "
                "such as structuring, pass-through layering, sanctioned-jurisdiction "
                "exposure, velocity spikes, PEP and adverse media.\n"
                "- Weights sum to a **0–100 score** → tier "
                "(**Low <25 · Medium <50 · High <75 · Critical ≥75**).\n"
                "- **Gemini** parses unstructured alerts into signals and writes the "
                "rationale — it never invents the score."
            )
        return

    result = st.session_state["result"]
    tabs = st.tabs(
        ["📊 Overview", "📋 Risk Register", "🔎 Drill-down", "💬 Ask", "⬇ Export"]
    )
    with tabs[0]:
        overview_tab(result)
    with tabs[1]:
        register_tab(result)
    with tabs[2]:
        drilldown_tab(result)
    with tabs[3]:
        ask_tab(result)
    with tabs[4]:
        export_tab(result)


if __name__ == "__main__":
    main()
