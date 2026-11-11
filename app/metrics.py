"""Trusted schema and business metric definitions supplied to the agent."""

ALLOWED_TABLES = frozenset({"orders", "order_items"})

DATA_DICTIONARY = """\
Database: Brazilian Olist e-commerce orders, historical data from 2016-2018.
All timestamps are stored as TIMESTAMP; prices are in Brazilian real (BRL).

orders: one row per order.
  order_id VARCHAR, customer_unique_id VARCHAR, customer_state VARCHAR,
  order_status VARCHAR, purchased_at TIMESTAMP, delivered_at TIMESTAMP,
  estimated_delivery_at TIMESTAMP, item_revenue DOUBLE,
  freight_total DOUBLE, item_count BIGINT, review_score DOUBLE,
  late_delivery BOOLEAN.

order_items: one row per order line (order_id + item_number).
  order_id VARCHAR, item_number BIGINT, product_id VARCHAR,
  product_category VARCHAR, seller_id VARCHAR, price DOUBLE,
  freight_value DOUBLE, purchased_at TIMESTAMP,
  order_status VARCHAR, customer_state VARCHAR,
  late_delivery BOOLEAN, review_score DOUBLE.

Metric rules:
  Sales revenue = SUM(item_revenue) from orders, or SUM(price) from order_items,
    where order_status = 'delivered'. Shipping/freight is excluded.
  Orders = COUNT(DISTINCT order_id) for delivered orders.
  Average order value = sales revenue / delivered orders.
  Late delivery rate = AVG(late_delivery::INTEGER) among delivered orders
    with both delivered_at and estimated_delivery_at present.
  Average review = AVG(review_score), excluding NULL.
  Repeat customer = a customer_unique_id with >= 2 delivered orders.
  Join orders to order_items only when needed; order_items has multiple rows/order.
  For category revenue use order_items, not orders joined to order_items.

Limitations:
  No impressions, visits, ad spend, returns or profit data. Do not claim
  conversion rate, marketing ROI, net revenue, or causal effects.
  Historical data only: do not interpret dates as current business activity.
"""
