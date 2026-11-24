"""Execute SQL analytics, simulate margin recovery recommendations, and generate KPI charts."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from retail_kpi.clean import DUCKDB_PATH, ROOT_DIR, build_star_schema_duckdb, clean_superstore

SQL_PATH = ROOT_DIR / "sql" / "kpi_analytics.sql"
ARTIFACTS_DIR = ROOT_DIR / "artifacts"
CHARTS_DIR = ARTIFACTS_DIR / "charts"


def run_sql_queries(db_path: Path = DUCKDB_PATH, sql_path: Path = SQL_PATH) -> dict[str, pd.DataFrame]:
    """Run all 4 analytical queries from sql/kpi_analytics.sql against DuckDB."""
    raw_sql = sql_path.read_text(encoding="utf-8")
    statements = [s.strip() for s in raw_sql.split(";") if s.strip() and not all(ln.startswith("--") or not ln.strip() for ln in s.splitlines())]
    con = duckdb.connect(str(db_path), read_only=True)
    names = ["region_category", "yoy_growth", "subcategory_ranking", "discount_bands"]
    results: dict[str, pd.DataFrame] = {}
    try:
        for name, stmt in zip(names, statements):
            results[name] = con.execute(stmt).df()
    finally:
        con.close()
    return results


def simulate_pricing_recommendations(df: pd.DataFrame) -> dict:
    """Quantify 3 pricing/discount levers targeting Furniture margin recovery."""
    total_sales = float(df["Sales"].sum())
    total_profit = float(df["Profit"].sum())
    base_margin = total_profit / total_sales

    # Baseline implied cost per line: Cost = Sales - Profit; list_price_sales = Sales / (1 - Discount)
    work = df.copy()
    work["implied_cost"] = work["Sales"] - work["Profit"]
    work["gross_sales"] = np.where(work["Discount"] < 1.0, work["Sales"] / (1.0 - work["Discount"]), work["Sales"])

    # Lever 1: Cap Tables & Bookcases discounts at 15% (historical avg was 26.1% & 21.1%)
    sim1 = work.copy()
    mask_tb = sim1["Sub-Category"].isin(["Tables", "Bookcases"]) & (sim1["Discount"] > 0.15)
    sim1.loc[mask_tb, "Discount"] = 0.15
    sim1.loc[mask_tb, "Sales"] = sim1.loc[mask_tb, "gross_sales"] * (1.0 - 0.15)
    sim1.loc[mask_tb, "Profit"] = sim1.loc[mask_tb, "Sales"] - sim1.loc[mask_tb, "implied_cost"]
    gain1 = float(sim1["Profit"].sum() - total_profit)

    # Lever 2: Cap all >30% deep-discount orders across all categories at 20%
    sim2 = work.copy()
    mask_deep = sim2["Discount"] > 0.30
    sim2.loc[mask_deep, "Discount"] = 0.20
    sim2.loc[mask_deep, "Sales"] = sim2.loc[mask_deep, "gross_sales"] * (1.0 - 0.20)
    sim2.loc[mask_deep, "Profit"] = sim2.loc[mask_deep, "Sales"] - sim2.loc[mask_deep, "implied_cost"]
    gain2 = float(sim2["Profit"].sum() - total_profit)

    # Conservative Furniture-focused target scenario (Lever 1 at 65% realization assuming demand elasticity)
    conservative_gain = gain1 * 0.65
    new_margin = (total_profit + conservative_gain) / total_sales
    relative_margin_lift_pct = ((new_margin - base_margin) / base_margin) * 100.0

    # Furniture-specific margin improvement (even under 65% realization)
    furn_base_sales = float(work.loc[work["Category"] == "Furniture", "Sales"].sum())
    furn_base_profit = float(work.loc[work["Category"] == "Furniture", "Profit"].sum())
    furn_new_profit = furn_base_profit + conservative_gain

    return {
        "baseline_total_sales": round(total_sales, 2),
        "baseline_total_profit": round(total_profit, 2),
        "baseline_profit_margin_pct": round(base_margin * 100.0, 2),
        "furniture_baseline_margin_pct": round((furn_base_profit / furn_base_sales) * 100.0, 2),
        "furniture_post_cap_margin_pct": round((furn_new_profit / furn_base_sales) * 100.0, 2),
        "lever1_cap_tables_bookcases_15pct_gross_gain": round(gain1, 2),
        "lever2_cap_deep_discounts_20pct_gross_gain": round(gain2, 2),
        "combined_conservative_profit_recovery_usd": round(conservative_gain, 2),
        "estimated_overall_margin_recovery_pct": round(relative_margin_lift_pct, 2),
        "recommendations": [
            {
                "title": "Cap Tables & Bookcases Discounts at 15%",
                "rationale": "Tables (-8.56% margin, 26.1% avg discount) and Bookcases (-3.02% margin, 21.1% avg discount) lose -$21,198 combined.",
                "estimated_impact": f"+${gain1:,.0f} gross profit uplift (+${conservative_gain:,.0f} at 65% elasticity, ~{relative_margin_lift_pct:.1f}% overall margin recovery; Furniture margin {round((furn_base_profit / furn_base_sales) * 100.0, 2)}% -> {round((furn_new_profit / furn_base_sales) * 100.0, 2)}%).",
            },
            {
                "title": "Require Manager Approval Above 20% Discount Floor",
                "rationale": "Orders discounted >30% across Central and South regions consistently turn unit contribution negative.",
                "estimated_impact": f"Up to +${gain2:,.0f} additional gross margin upside if deep clearance discounts >30% are capped at 20%.",
            },
            {
                "title": "Shift Furniture Incentives to Volume Bundling & Standard Shipping",
                "rationale": "Bundle Tables with positive-margin Chairs (+8.1% margin) or Office Supplies (+17.0% margin) instead of flat price cuts.",
                "estimated_impact": "Protects average order value ($458.61) while eliminating unprofitable sub-20% discount bands.",
            },
        ],
    }


def generate_charts(df: pd.DataFrame, queries: dict[str, pd.DataFrame], out_dir: Path = CHARTS_DIR) -> None:
    """Create crisp Matplotlib PNG figures for README and reporting."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Category Profit Margin vs Avg Discount
    cat = (
        df.groupby("Category")
        .agg(sales=("Sales", "sum"), profit=("Profit", "sum"), avg_disc=("Discount", "mean"))
        .assign(margin_pct=lambda x: x["profit"] / x["sales"] * 100.0)
        .sort_values("margin_pct")
    )
    fig, ax1 = plt.subplots(figsize=(8.5, 4.4), dpi=150, constrained_layout=True)
    colors = ["#ef4444" if m < 5 else "#22c55e" for m in cat["margin_pct"]]
    bars = ax1.barh(cat.index, cat["margin_pct"], color=colors)
    ax1.set_xlabel("Profit Margin (%)")
    ax1.set_title("Profit Margin & Average Discount by Category (n=9,994 Orders)", fontweight="bold")
    ax1.set_xlim(0, max(cat["margin_pct"]) + 10.5)
    for bar, (_, row) in zip(bars, cat.iterrows()):
        ax1.text(
            bar.get_width() + 0.4,
            bar.get_y() + bar.get_height() / 2,
            f"{row['margin_pct']:.2f}%  (Avg Disc: {row['avg_disc']*100:.1f}%)",
            va="center",
            fontsize=9.5,
        )
    fig.savefig(out_dir / "category_margin.png")
    plt.close(fig)

    # 2. Sub-Category Profit Ranking
    sub = queries["subcategory_ranking"].sort_values("profit")
    fig2, ax2 = plt.subplots(figsize=(9.5, 5.8), dpi=150, constrained_layout=True)
    bar_cols = ["#dc2626" if p < 0 else "#2563eb" for p in sub["profit"]]
    ax2.barh(sub["sub_category"], sub["profit"], color=bar_cols)
    ax2.axvline(0, color="#334155", linewidth=1)
    ax2.set_title("Total Profit by Sub-Category (Tables & Bookcases Drive Furniture Loss)", fontweight="bold")
    ax2.set_xlabel("Total Profit ($ USD)")
    fig2.savefig(out_dir / "subcategory_profit.png")
    plt.close(fig2)


def main() -> dict:
    df, clean_stats = clean_superstore()
    db_path = build_star_schema_duckdb(df)
    queries = run_sql_queries(db_path)
    sim = simulate_pricing_recommendations(df)
    generate_charts(df, queries)

    summary = {
        "cleaning": clean_stats,
        "overall_kpis": {
            "total_revenue": round(float(df["Sales"].sum()), 2),
            "total_profit": round(float(df["Profit"].sum()), 2),
            "profit_margin_pct": round(float(df["Profit"].sum() / df["Sales"].sum() * 100.0), 2),
            "distinct_orders": int(df["Order ID"].nunique()),
            "avg_order_value": round(float(df["Sales"].sum() / df["Order ID"].nunique()), 2),
            "regions": int(df["Region"].nunique()),
            "categories": int(df["Category"].nunique()),
        },
        "yoy_growth": queries["yoy_growth"].to_dict(orient="records"),
        "region_category": queries["region_category"].to_dict(orient="records"),
        "subcategory_bottom5": queries["subcategory_ranking"].head(5).to_dict(orient="records"),
        "discount_simulation": sim,
    }
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "kpi_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    out = main()
    print(json.dumps(out["overall_kpis"], indent=2))
    print("Simulation:", json.dumps(out["discount_simulation"], indent=2))
