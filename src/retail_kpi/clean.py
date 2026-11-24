"""Data cleaning, feature engineering, and DuckDB Star Schema loader for Superstore Sales."""

from __future__ import annotations

from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
import requests

ROOT_DIR = Path(__file__).resolve().parents[2]
RAW_CSV_PATH = ROOT_DIR / "data" / "raw" / "superstore.csv"
PROCESSED_CSV_PATH = ROOT_DIR / "data" / "processed" / "superstore_clean.csv"
DUCKDB_PATH = ROOT_DIR / "data" / "superstore.duckdb"
FALLBACK_URL = "https://raw.githubusercontent.com/leonism/sample-superstore/master/data/superstore.csv"


def ensure_raw_dataset(raw_path: Path = RAW_CSV_PATH) -> Path:
    """Ensure raw Superstore CSV exists locally (downloads public mirror if missing)."""
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and raw_path.stat().st_size > 0:
        return raw_path
    resp = requests.get(FALLBACK_URL, timeout=20)
    resp.raise_for_status()
    raw_path.write_bytes(resp.content)
    return raw_path


def clean_superstore(raw_path: Path = RAW_CSV_PATH) -> tuple[pd.DataFrame, dict[str, int]]:
    """Load, clean, and enrich the Superstore transactions dataset."""
    ensure_raw_dataset(raw_path)
    raw_df = pd.read_csv(raw_path, encoding="latin1")
    raw_rows = int(len(raw_df))

    # Drop incomplete rows missing core transaction/financial fields (806 stub rows in mirror).
    df = raw_df.dropna(
        subset=["Order ID", "Order Date", "Customer ID", "Product ID", "Region", "Category", "Sales", "Profit"]
    ).copy()
    df = df.drop_duplicates(subset=["Row ID"]).reset_index(drop=True)

    df["Order Date"] = pd.to_datetime(df["Order Date"], errors="coerce")
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], errors="coerce")
    df = df.dropna(subset=["Order Date", "Ship Date"]).reset_index(drop=True)

    df["Postal Code"] = df["Postal Code"].fillna(0).astype(int).astype(str).str.zfill(5)
    df["Sales"] = df["Sales"].astype(float)
    df["Profit"] = df["Profit"].astype(float)
    df["Discount"] = df["Discount"].astype(float)
    df["Quantity"] = df["Quantity"].astype(int)

    df["order_year"] = df["Order Date"].dt.year
    df["order_quarter"] = df["Order Date"].dt.to_period("Q").astype(str)
    df["order_month"] = df["Order Date"].dt.to_period("M").astype(str)
    df["ship_days"] = (df["Ship Date"] - df["Order Date"]).dt.days
    df["profit_margin"] = np.where(df["Sales"] != 0, df["Profit"] / df["Sales"], 0.0)
    df["discount_band"] = pd.cut(
        df["Discount"],
        bins=[-0.01, 0.0, 0.15, 0.30, 1.0],
        labels=["0% (Full Price)", "1-15% (Low)", "16-30% (Moderate)", ">30% (Heavy)"],
    ).astype(str)

    stats = {
        "raw_rows": raw_rows,
        "dropped_incomplete_rows": raw_rows - int(len(df)),
        "clean_rows": int(len(df)),
    }
    return df, stats


def build_star_schema_duckdb(
    df: pd.DataFrame,
    db_path: Path = DUCKDB_PATH,
    processed_csv: Path = PROCESSED_CSV_PATH,
) -> Path:
    """Persist cleaned CSV and normalized Star Schema tables into DuckDB."""
    processed_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(processed_csv, index=False)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    dim_customers = (
        df[["Customer ID", "Customer Name", "Segment"]]
        .drop_duplicates(subset=["Customer ID"])
        .rename(columns={"Customer ID": "customer_id", "Customer Name": "customer_name", "Segment": "segment"})
    )
    dim_products = (
        df[["Product ID", "Category", "Sub-Category", "Product Name"]]
        .drop_duplicates(subset=["Product ID"])
        .rename(
            columns={
                "Product ID": "product_id",
                "Category": "category",
                "Sub-Category": "sub_category",
                "Product Name": "product_name",
            }
        )
    )
    dim_locations = (
        df[["Postal Code", "City", "State", "Region", "Country"]]
        .drop_duplicates(subset=["Postal Code", "City", "State", "Region"])
        .reset_index(drop=True)
    )
    dim_locations.insert(0, "location_id", np.arange(1, len(dim_locations) + 1))
    dim_locations = dim_locations.rename(
        columns={
            "Postal Code": "postal_code",
            "City": "city",
            "State": "state",
            "Region": "region",
            "Country": "country",
        }
    )

    merged_loc = df.merge(
        dim_locations,
        left_on=["Postal Code", "City", "State", "Region"],
        right_on=["postal_code", "city", "state", "region"],
        how="left",
    )
    fact_orders = merged_loc[
        [
            "Row ID",
            "Order ID",
            "Order Date",
            "Ship Date",
            "Ship Mode",
            "Customer ID",
            "Product ID",
            "location_id",
            "Sales",
            "Quantity",
            "Discount",
            "Profit",
            "order_year",
            "ship_days",
            "profit_margin",
            "discount_band",
        ]
    ].rename(
        columns={
            "Row ID": "row_id",
            "Order ID": "order_id",
            "Order Date": "order_date",
            "Ship Date": "ship_date",
            "Ship Mode": "ship_mode",
            "Customer ID": "customer_id",
            "Product ID": "product_id",
            "Sales": "sales",
            "Quantity": "quantity",
            "Discount": "discount",
            "Profit": "profit",
        }
    )

    con = duckdb.connect(str(db_path))
    try:
        con.register("v_cust", dim_customers)
        con.register("v_prod", dim_products)
        con.register("v_loc", dim_locations)
        con.register("v_fact", fact_orders)
        con.execute("CREATE TABLE dim_customers AS SELECT * FROM v_cust")
        con.execute("CREATE TABLE dim_products AS SELECT * FROM v_prod")
        con.execute("CREATE TABLE dim_locations AS SELECT * FROM v_loc")
        con.execute("CREATE TABLE fact_orders AS SELECT * FROM v_fact")
    finally:
        con.close()
    return db_path
