import pytest

from app.sql_guard import UnsafeQuery, validate_sql


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "DROP TABLE orders",
    "SELECT * FROM orders; DELETE FROM orders",
    "SELECT * FROM read_csv_auto('C:/secret.csv')",
    "SELECT * FROM sqlite_scan('x', 'y')",
    "SELECT * FROM unknown_table",
    "SELECT 1",
])
def test_rejects_unsafe_or_ungrounded_queries(sql):
    with pytest.raises(UnsafeQuery):
        validate_sql(sql)


def test_approved_join_and_limit():
    sql = """SELECT o.customer_state, SUM(i.price) AS revenue
             FROM orders o JOIN order_items i USING (order_id)
             WHERE o.order_status = 'delivered'
             GROUP BY o.customer_state ORDER BY revenue DESC LIMIT 10000"""
    checked = validate_sql(sql, max_rows=200)
    assert "LIMIT 200" in checked
    assert "orders" in checked and "order_items" in checked


def test_cte_is_allowed():
    checked = validate_sql("WITH x AS (SELECT order_id FROM orders) SELECT COUNT(*) FROM x")
    assert "WITH x AS" in checked


def test_smaller_limit_is_preserved():
    checked = validate_sql("SELECT seller_id FROM order_items LIMIT 10", max_rows=200)
    assert checked.endswith("LIMIT 10")
