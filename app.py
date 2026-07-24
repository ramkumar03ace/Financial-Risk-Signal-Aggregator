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
    "Critical": "#9B1C1C",
    "High": "#B45309",
    "Medium": "#8A6D1B",
    "Low": "#166534",
}
TIER_ORDER = ["Critical", "High", "Medium", "Low"]
OK_COLOR = "#166534"
WARN_COLOR = "#B45309"

st.set_page_config(
    page_title="Financial Risk Signal Aggregator",
    page_icon=None,
    layout="wide",
)


def inject_theme() -> None:
    """Custom type system + a small colored-chip indicator language, used in
    place of emoji throughout (status, tiers, KPIs)."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,600;8..60,700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

        :root {
            --ink: #14171C;
            --slate: #5B6472;
            --accent: #1B2A4A;
            --hairline: #DDD9CF;
        }
        html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
        h1, h2, h3, .stMarkdown h3, .stMarkdown h4 {
            font-family: 'Source Serif 4', Georgia, serif !important;
            font-weight: 600;
            letter-spacing: -0.01em;
        }
        [data-testid="stHeader"] { height: 2rem; background: transparent; }
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1200px; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }
        [data-testid="stSidebar"] h1 {
            font-size: 1.3rem;
            border-bottom: 1px solid var(--hairline);
            padding-bottom: 0.6rem;
        }
        .stButton > button, .stDownloadButton > button {
            font-family: 'IBM Plex Sans', sans-serif;
            font-weight: 500;
            letter-spacing: 0.01em;
            border-radius: 4px;
        }
        [data-testid="stTabs"] button[role="tab"] {
            font-family: 'IBM Plex Sans', sans-serif;
            font-weight: 500;
            font-size: 0.85rem;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        [data-testid="stTabs"] [data-baseweb="tab-highlight"] {
            background-color: var(--accent) !important;
        }
        [data-testid="stMetricValue"] { font-family: 'IBM Plex Mono', monospace; }
        [data-testid="stMetricLabel"] {
            font-family: 'IBM Plex Sans', sans-serif;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.05em;
            color: var(--slate);
        }
        [data-testid="stDataFrame"] thead tr th, [data-testid="stTable"] thead tr th {
            font-family: 'IBM Plex Sans', sans-serif;
            text-transform: uppercase;
            font-size: 0.7rem;
            letter-spacing: 0.04em;
            color: var(--slate);
        }
        .rag-chip {
            display: inline-flex; align-items: center; gap: 0.5rem;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 0.76rem; letter-spacing: 0.03em;
            padding: 0.5rem 0.7rem;
            border: 1px solid var(--hairline); border-radius: 4px;
            background: #FFFFFF;
        }
        .rag-dot { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
        .kpi-row { display: flex; gap: 0; margin-bottom: 0.5rem; flex-wrap: wrap; }
        .kpi-tile {
            flex: 1; min-width: 110px;
            padding: 0 1.4rem 0 0; margin-right: 1.4rem;
            border-right: 1px solid var(--hairline);
        }
        .kpi-tile:last-child { border-right: none; margin-right: 0; }
        .kpi-label {
            display: flex; align-items: center; gap: 0.4rem;
            font-family: 'IBM Plex Sans', sans-serif; text-transform: uppercase;
            font-size: 0.7rem; letter-spacing: 0.05em; color: var(--slate);
            margin-bottom: 0.3rem;
        }
        .kpi-value {
            font-family: 'IBM Plex Mono', monospace; font-size: 1.9rem;
            font-weight: 600; color: var(--ink);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def chip(label: str, color: str) -> str:
    return (
        f'<span class="rag-chip"><span class="rag-dot" '
        f'style="background:{color}"></span>{label}</span>'
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
    st.sidebar.title("Risk Aggregator")
    st.sidebar.caption("Structured + unstructured signals → prioritised risk view")

    if llm.is_available():
        st.sidebar.markdown(
            chip("Gemini connected — AI reasoning on", OK_COLOR),
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            chip("No Gemini key — rules + fallback mode", WARN_COLOR),
            unsafe_allow_html=True,
        )

    st.sidebar.subheader("1 · Load data")
    if st.sidebar.button("Load sample dataset", use_container_width=True):
        _load_sample_into_state()

    if st.session_state.get("sample_loaded"):
        n_cust = len(st.session_state.get("customers", []))
        n_txn = len(st.session_state.get("txns_df", []))
        st.sidebar.markdown(
            chip(f"Sample loaded — {n_cust} customers, {n_txn} transactions", OK_COLOR),
            unsafe_allow_html=True,
        )

    txn_file = st.sidebar.file_uploader("Transactions (CSV)", type=["csv"])
    cust_file = st.sidebar.file_uploader("Customer records (JSON)", type=["json"])
    if "alert_text" not in st.session_state:
        st.session_state["alert_text"] = ""
    alert_text = st.sidebar.text_area(
        "External alerts / adverse media (paste text)",
        height=160,
        key="alert_text",
    )

    st.sidebar.subheader("2 · Analyse")
    if st.sidebar.button("Run risk analysis", type="primary", use_container_width=True):
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

    tiles = [("Customers", len(register), None)] + [
        (t, counts[t], TIER_COLORS[t]) for t in TIER_ORDER
    ]
    tiles_html = ""
    for label, value, color in tiles:
        dot = f'<span class="rag-dot" style="background:{color}"></span>' if color else ""
        tiles_html += (
            f'<div class="kpi-tile"><div class="kpi-label">{dot}{label}</div>'
            f'<div class="kpi-value">{value}</div></div>'
        )
    st.markdown(f'<div class="kpi-row">{tiles_html}</div>', unsafe_allow_html=True)

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
        fig.update_layout(showlegend=False, font_family="IBM Plex Sans")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        flagged = [e for e in register if e.score > 0][:20]
        chart_title = (
            f"Top {len(flagged)} flagged customers (of {len(register)} reviewed)"
            if flagged
            else "Risk score by customer"
        )
        scores = pd.DataFrame(
            [{"Customer": e.name, "Score": e.score, "Tier": e.tier} for e in flagged]
        )
        if scores.empty:
            st.info("No customers were flagged — nothing to chart.")
        else:
            fig2 = px.bar(
                scores, x="Score", y="Customer", color="Tier", orientation="h",
                color_discrete_map=TIER_COLORS, title=chart_title,
            )
            fig2.update_layout(
                yaxis={"categoryorder": "total ascending"}, font_family="IBM Plex Sans"
            )
            st.plotly_chart(fig2, use_container_width=True)


def register_tab(result: Dict[str, Any]) -> None:
    register: List[EntityRisk] = result["register"]
    n_flagged = sum(1 for e in register if e.score > 0)
    st.subheader("Prioritised risk register")

    show_all = True
    if n_flagged and n_flagged < len(register):
        show_all = st.checkbox(
            f"Show all {len(register)} customers (default: {n_flagged} flagged only)",
            value=False,
        )
    shown = register if show_all else [e for e in register if e.score > 0]
    df = register_to_df(shown)

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
            chip(f"{er.tier} — score {er.score}/100", TIER_COLORS[er.tier])
            + f"&nbsp;&nbsp; **Recommended action:** {er.recommended_action} "
            f"&nbsp;|&nbsp; **Confidence:** {er.confidence}",
            unsafe_allow_html=True,
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
        "Download register (CSV)",
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
        "Download full findings (JSON)",
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
                    {"range": [0, 25], "color": "#E4ECE4"},
                    {"range": [25, 50], "color": "#EFE8D6"},
                    {"range": [50, 75], "color": "#F1E2CE"},
                    {"range": [75, 100], "color": "#F0D9D6"},
                ],
            },
        )
    )
    fig.update_layout(
        height=220, margin=dict(l=10, r=10, t=40, b=10), font_family="IBM Plex Sans"
    )
    return fig


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    inject_theme()
    sidebar()
    st.title("Financial Risk Signal Aggregator")
    st.caption(
        "Aggregates transaction records, account activity and external alerts into a "
        "prioritised, risk-scored view — deterministic rules score, Gemini explains."
    )

    if "result" not in st.session_state:
        st.info(
            "Click **Load sample dataset**, then **Run risk analysis** to see the "
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
        ["Overview", "Risk Register", "Drill-down", "Ask", "Export"]
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
