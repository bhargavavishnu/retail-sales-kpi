# Power BI Star Schema & Drill-Through Setup Guide

Power BI Desktop runs natively on Windows. To assemble the `.pbix` report on Windows using this repository's cleaned dataset and DAX measures:

1. **Import Tables** (via `Get Data -> CSV` from `data/processed/superstore_clean.csv` or DuckDB ODBC):
   - `fact_orders` (`row_id`, `order_id`, `order_date`, `ship_date`, `customer_id`, `product_id`, `location_id`, `sales`, `quantity`, `discount`, `profit`)
   - `dim_products` (`product_id`, `category`, `sub_category`, `product_name`)
   - `dim_customers` (`customer_id`, `customer_name`, `segment`)
   - `dim_locations` (`location_id`, `postal_code`, `city`, `state`, `region`, `country`)
   - Create a `dim_date` calendar table (`CALENDARAUTO()`) marked as Date Table and linked `1:*` to `fact_orders[order_date]`.

2. **Add DAX Measures:** Copy all 12 measures from [measures.dax](measures.dax) into a dedicated `_Measures` table.

3. **Configure Drill-Through Hierarchy:**
   - Page 1 (**Executive KPI Overview**): KPI Cards (`Total Revenue`, `Total Profit`, `Profit Margin %`, `Order Volume`, `Average Order Value`, `YoY Revenue Growth %`), Region Matrix, Monthly Revenue Trend.
   - Page 2 (**Category & Discount Leakage Drill-Through**): Add `dim_locations[region]` and `dim_products[category]` as Drill-Through fields; display Sub-Category Profit waterfall + Discount vs. Margin scatter plot highlighting `Tables` and `Bookcases`.
