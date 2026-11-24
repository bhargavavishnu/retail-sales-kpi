"""Interactive Streamlit & Plotly drill-through BI dashboard for Retail Sales & KPI Analytics."""

from __future__ import annotations

import json
from pathlib import Path

import plotly.express as px
import streamlit as st

from retail_kpi.analyze import ARTIFACTS_DIR, main as run_pipeline
from retail_kpi.clean import PROCESSED_CSV_PATH

import pandas as pd

st.set_page_config(page_title="Retail Sales & KPI Analytics", page_icon="📊", layout="wide")
st.title("Retail Sales & KPI Performance Analytics")
st.caption("Superstore transactions Star Schema (DuckDB + Pandas + Power BI DAX parity).")

if not PROCESSED_CSV_PATH.exists() or not (ARTIFACTS_DIR / "kpi_summary.json").exists():
    with st.spinner("Running cleaning & DuckDB KPI pipeline..."):
        run_pipeline()

df = pd.read_csv(PROCESSED_CSV_PATH)
summary = json.loads((ARTIFACTS_DIR / "kpi_summary.json").read_text(encoding="utf-8"))

with st.sidebar:
    st.header("Drill-Through Filters")
    regions = st.multiselect("Region", sorted(df["Region"].unique()), default=sorted(df["Region"].unique()))
    categories = st.multiselect("Category", sorted(df["Category"].unique()), default=sorted(df["Category"].unique()))
    years = st.multiselect("Order Year", sorted(df["order_year"].unique()), default=sorted(df["order_year"].unique()))

filtered = df[df["Region"].isin(regions) & df["Category"].isin(categories) & df["order_year"].isin(years)]

rev = float(filtered["Sales"].sum())
prof = float(filtered["Profit"].sum())
orders = int(filtered["Order ID"].nunique())
margin = (prof / rev * 100.0) if rev else 0.0
aov = (rev / orders) if orders else 0.0
avg_disc = float(filtered["Discount"].mean() * 100.0) if len(filtered) else 0.0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Total Revenue", f"${rev:,.0f}")
c2.metric("Total Profit", f"${prof:,.0f}")
c3.metric("Profit Margin %", f"{margin:.2f}%")
c4.metric("Order Volume", f"{orders:,}")
c5.metric("Avg Order Value", f"${aov:,.2f}", delta=f"Avg Disc {avg_disc:.1f}%")

tab_overview, tab_drill, tab_recs = st.tabs(["Regional & Category KPIs", "Sub-Category & Discount Drill-Through", "Pricing Recommendations"])

with tab_overview:
    col_a, col_b = st.columns(2)
    cat_agg = filtered.groupby("Category", as_index=False).agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"))
    cat_agg["Margin %"] = cat_agg["Profit"] / cat_agg["Sales"] * 100.0
    col_a.plotly_chart(
        px.bar(cat_agg, x="Category", y="Margin %", color="Margin %", color_continuous_scale="RdYlGn", title="Profit Margin % by Category"),
        use_container_width=True,
    )
    reg_agg = filtered.groupby(["Region", "Category"], as_index=False).agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"))
    col_b.plotly_chart(
        px.bar(reg_agg, x="Region", y="Sales", color="Category", barmode="group", title="Revenue Across 4 Regions & 3 Categories"),
        use_container_width=True,
    )

with tab_drill:
    sub_agg = (
        filtered.groupby(["Category", "Sub-Category"], as_index=False)
        .agg(Sales=("Sales", "sum"), Profit=("Profit", "sum"), Avg_Discount=("Discount", "mean"))
        .sort_values("Profit")
    )
    sub_agg["Avg_Discount_Pct"] = sub_agg["Avg_Discount"] * 100.0
    st.plotly_chart(
        px.bar(
            sub_agg,
            x="Profit",
            y="Sub-Category",
            color="Category",
            orientation="h",
            hover_data=["Sales", "Avg_Discount_Pct"],
            title="Sub-Category Profitability Drill-Through (Tables & Bookcases Drag)",
        ),
        use_container_width=True,
    )

with tab_recs:
    sim = summary["discount_simulation"]
    st.subheader("Estimated Margin Recovery Simulation")
    st.info(
        f"Baseline Margin: **{sim['baseline_profit_margin_pct']}%** | "
        f"Conservative Profit Recovery: **+${sim['combined_conservative_profit_recovery_usd']:,.2f}** "
        f"(~**{sim['estimated_overall_margin_recovery_pct']:.1f}%** relative overall margin lift)"
    )
    for rec in sim["recommendations"]:
        st.markdown(f"### {rec['title']}")
        st.write(f"**Finding:** {rec['rationale']}")
        st.success(f"**Estimated Impact:** {rec['estimated_impact']}")
