---
name: ecommerce-analysis
description: Analyze historical Olist e-commerce orders using approved metrics and read-only SQL. Use for sales, orders, delivery, reviews, categories, regions, and repeat customers.
---

# E-commerce analysis

1. Call `get_schema` before any `run_sql` call. Treat the returned data dictionary as the source of truth for tables, columns, and metric definitions.
2. Answer data questions only from successful `run_sql` results. Cite each result as 查询1、查询2, and state the metric and historical time period.
3. Sales use delivered orders and item price, excluding freight. Category sales use `order_items`; joining order-level revenue to item rows duplicates it.
4. Exclude NULL reviews when calculating review averages. Explain missing timestamps or incomplete groups when they affect a rate.
5. If the data lacks a requested measure, call `cannot_answer` and name the missing data. Do not infer visits, ad conversions, marketing ROI, profit, returns, or causal effects.
6. Keep the final Chinese response concise: finding, supporting figures, and a relevant limitation.
