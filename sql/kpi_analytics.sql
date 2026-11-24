-- Star Schema Analytical SQL Queries (DuckDB / ANSI SQL with JOINs, CTEs, and Window Functions)

-- 1. Region x Category Performance with Window-Function Share & Margin Rank
WITH region_cat AS (
    SELECT
        l.region,
        p.category,
        COUNT(DISTINCT f.order_id) AS order_volume,
        COUNT(*) AS line_items,
        ROUND(SUM(f.sales), 2) AS revenue,
        ROUND(SUM(f.profit), 2) AS profit,
        ROUND(SUM(f.profit) / NULLIF(SUM(f.sales), 0) * 100.0, 2) AS profit_margin_pct,
        ROUND(AVG(f.discount) * 100.0, 2) AS avg_discount_pct
    FROM fact_orders f
    JOIN dim_products p ON f.product_id = p.product_id
    JOIN dim_locations l ON f.location_id = l.location_id
    GROUP BY l.region, p.category
)
SELECT
    region,
    category,
    order_volume,
    line_items,
    revenue,
    profit,
    profit_margin_pct,
    avg_discount_pct,
    ROUND(revenue / SUM(revenue) OVER (PARTITION BY region) * 100.0, 2) AS regional_revenue_share_pct,
    RANK() OVER (PARTITION BY region ORDER BY profit_margin_pct DESC) AS regional_margin_rank
FROM region_cat
ORDER BY region, profit_margin_pct ASC;


-- 2. Year-over-Year (YoY) Revenue & Profit Growth via LAG() Window Function
WITH yearly AS (
    SELECT
        order_year,
        COUNT(DISTINCT order_id) AS order_volume,
        ROUND(SUM(sales), 2) AS revenue,
        ROUND(SUM(profit), 2) AS profit,
        ROUND(SUM(profit) / NULLIF(SUM(sales), 0) * 100.0, 2) AS profit_margin_pct,
        ROUND(SUM(sales) / NULLIF(COUNT(DISTINCT order_id), 0), 2) AS avg_order_value
    FROM fact_orders
    GROUP BY order_year
)
SELECT
    order_year,
    order_volume,
    revenue,
    profit,
    profit_margin_pct,
    avg_order_value,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY order_year))
        / NULLIF(LAG(revenue) OVER (ORDER BY order_year), 0) * 100.0,
        2
    ) AS yoy_revenue_growth_pct
FROM yearly
ORDER BY order_year;


-- 3. Sub-Category Margin & Discount Leakage Ranking (Identifies Tables & Bookcases Drag)
SELECT
    p.category,
    p.sub_category,
    COUNT(DISTINCT f.order_id) AS order_volume,
    ROUND(SUM(f.sales), 2) AS revenue,
    ROUND(SUM(f.profit), 2) AS profit,
    ROUND(SUM(f.profit) / NULLIF(SUM(f.sales), 0) * 100.0, 2) AS profit_margin_pct,
    ROUND(AVG(f.discount) * 100.0, 2) AS avg_discount_pct,
    RANK() OVER (ORDER BY SUM(f.profit) ASC) AS loss_severity_rank
FROM fact_orders f
JOIN dim_products p ON f.product_id = p.product_id
GROUP BY p.category, p.sub_category
ORDER BY profit ASC;


-- 4. Discount Band Impact Across Categories
SELECT
    p.category,
    f.discount_band,
    COUNT(*) AS line_items,
    ROUND(SUM(f.sales), 2) AS revenue,
    ROUND(SUM(f.profit), 2) AS profit,
    ROUND(SUM(f.profit) / NULLIF(SUM(f.sales), 0) * 100.0, 2) AS profit_margin_pct
FROM fact_orders f
JOIN dim_products p ON f.product_id = p.product_id
GROUP BY p.category, f.discount_band
ORDER BY p.category, profit_margin_pct DESC;
