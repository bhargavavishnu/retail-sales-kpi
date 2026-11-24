"""Tests for Superstore cleaning, DuckDB Star Schema SQL window functions, and recovery simulation."""

from pathlib import Path

from retail_kpi.analyze import main as run_pipeline, run_sql_queries, simulate_pricing_recommendations
from retail_kpi.clean import build_star_schema_duckdb, clean_superstore


def test_clean_superstore_drops_incomplete_rows() -> None:
    df, stats = clean_superstore()
    assert stats["clean_rows"] == 9994
    assert stats["dropped_incomplete_rows"] == 806
    assert df["Region"].nunique() == 4
    assert df["Category"].nunique() == 3


def test_sql_window_functions_and_furniture_findings(tmp_path: Path) -> None:
    df, _ = clean_superstore()
    db_file = tmp_path / "test_superstore.duckdb"
    build_star_schema_duckdb(df, db_path=db_file, processed_csv=tmp_path / "clean.csv")
    queries = run_sql_queries(db_path=db_file)

    reg_cat = queries["region_category"]
    assert len(reg_cat) == 12  # 4 regions x 3 categories

    sub = queries["subcategory_ranking"]
    worst_two = set(sub.head(2)["sub_category"].tolist())
    assert worst_two == {"Tables", "Bookcases"}
    assert (sub.head(2)["profit"] < 0).all()

    sim = simulate_pricing_recommendations(df)
    assert sim["furniture_baseline_margin_pct"] < 3.0
    assert sim["combined_conservative_profit_recovery_usd"] > 10000
    assert 8.0 <= sim["estimated_overall_margin_recovery_pct"] <= 20.0
