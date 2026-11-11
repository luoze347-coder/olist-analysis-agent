from pathlib import Path
import json

import duckdb
import pandas as pd

from app.database import run_query
from scripts.prepare_data import build_database


def test_build_database_preserves_order_grain(tmp_path: Path):
    source = tmp_path / "csv"
    source.mkdir()
    pd.DataFrame([{
        "order_id": "o1", "customer_id": "c1", "order_status": "delivered",
        "order_purchase_timestamp": "2018-01-01 10:00:00",
        "order_delivered_customer_date": "2018-01-10 10:00:00",
        "order_estimated_delivery_date": "2018-01-08 10:00:00",
    }]).to_csv(source / "olist_orders_dataset.csv", index=False)
    pd.DataFrame([{
        "customer_id": "c1", "customer_unique_id": "u1", "customer_state": "SP",
    }]).to_csv(source / "olist_customers_dataset.csv", index=False)
    pd.DataFrame([
        {"order_id": "o1", "order_item_id": 1, "product_id": "p1", "seller_id": "s1", "price": 10, "freight_value": 2},
        {"order_id": "o1", "order_item_id": 2, "product_id": "p1", "seller_id": "s1", "price": 20, "freight_value": 3},
    ]).to_csv(source / "olist_order_items_dataset.csv", index=False)
    pd.DataFrame([{"product_id": "p1", "product_category_name": "livros"}]).to_csv(
        source / "olist_products_dataset.csv", index=False
    )
    pd.DataFrame([{"order_id": "o1", "review_score": 4, "review_creation_date": "2018-01-11"}]).to_csv(
        source / "olist_order_reviews_dataset.csv", index=False
    )
    target = tmp_path / "test.duckdb"
    info = build_database(source, target)
    assert info["orders"] == 1 and info["order_items"] == 2
    with duckdb.connect(str(target), read_only=True) as con:
        order = con.execute("SELECT item_revenue, freight_total, item_count, late_delivery FROM orders").fetchone()
        assert order == (30.0, 5.0, 2, True)
        assert con.execute("SELECT SUM(price) FROM order_items").fetchone()[0] == 30.0
    result = run_query("SELECT SUM(item_revenue) AS revenue FROM orders WHERE order_status = 'delivered'", database_path=target)
    assert result["rows"] == [[30.0]]
    cases_path = Path(__file__).resolve().parents[1] / "eval" / "cases.json"
    for case in json.loads(cases_path.read_text(encoding="utf-8")):
        if "gold_sql" in case:
            run_query(case["gold_sql"], database_path=target)
