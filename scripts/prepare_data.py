"""Build a repeatable, read-only analytical DuckDB from Olist CSVs."""

from __future__ import annotations

import argparse
import json
import os
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_SOURCE = (
    RAW_DIR / "olist-extracted"
    if (RAW_DIR / "olist-extracted" / "olist_orders_dataset.csv").exists()
    else RAW_DIR / "olist.zip"
)
DEFAULT_TARGET = ROOT / "data" / "olist.duckdb"

FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}


def _read_csv(source: Path, filename: str) -> pd.DataFrame:
    if source.is_dir():
        return pd.read_csv(source / filename)
    with zipfile.ZipFile(source) as archive:
        matches = [name for name in archive.namelist() if name.endswith(filename)]
        if len(matches) != 1:
            raise FileNotFoundError(f"Expected exactly one {filename} in {source}")
        with archive.open(matches[0]) as handle:
            return pd.read_csv(handle)


def build_database(source: Path = DEFAULT_SOURCE, target: Path = DEFAULT_TARGET) -> dict:
    if not source.exists():
        raise FileNotFoundError(
            f"Dataset missing: {source}. Download the Olist Brazilian E-Commerce dataset from Kaggle."
        )
    raw = {key: _read_csv(source, filename) for key, filename in FILES.items()}
    orders = raw["orders"][[
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_delivered_customer_date", "order_estimated_delivery_date",
    ]].copy()
    orders = orders.merge(
        raw["customers"][["customer_id", "customer_unique_id", "customer_state"]],
        on="customer_id", validate="many_to_one",
    )
    orders = orders.rename(columns={
        "order_purchase_timestamp": "purchased_at",
        "order_delivered_customer_date": "delivered_at",
        "order_estimated_delivery_date": "estimated_delivery_at",
    }).drop(columns="customer_id")
    for column in ("purchased_at", "delivered_at", "estimated_delivery_at"):
        orders[column] = pd.to_datetime(orders[column], errors="coerce")

    items = raw["items"][[
        "order_id", "order_item_id", "product_id", "seller_id", "price", "freight_value",
    ]].rename(columns={"order_item_id": "item_number"}).copy()
    totals = items.groupby("order_id", as_index=False).agg(
        item_revenue=("price", "sum"),
        freight_total=("freight_value", "sum"),
        item_count=("item_number", "count"),
    )
    orders = orders.merge(totals, on="order_id", how="left", validate="one_to_one")
    orders[["item_revenue", "freight_total", "item_count"]] = orders[
        ["item_revenue", "freight_total", "item_count"]
    ].fillna(0)
    orders["item_count"] = orders["item_count"].astype("int64")

    reviews = raw["reviews"][["order_id", "review_score", "review_creation_date"]].copy()
    reviews["review_creation_date"] = pd.to_datetime(reviews["review_creation_date"], errors="coerce")
    reviews = reviews.sort_values("review_creation_date").drop_duplicates("order_id", keep="last")
    orders = orders.merge(reviews[["order_id", "review_score"]], on="order_id", how="left", validate="one_to_one")
    valid_dates = orders["delivered_at"].notna() & orders["estimated_delivery_at"].notna()
    orders["late_delivery"] = (orders["delivered_at"] > orders["estimated_delivery_at"]).where(valid_dates)

    products = raw["products"][["product_id", "product_category_name"]].drop_duplicates("product_id")
    translation_name = "product_category_name_translation.csv"
    try:
        translations = _read_csv(source, translation_name)
        products = products.merge(translations, on="product_category_name", how="left", validate="many_to_one")
        products["product_category"] = products["product_category_name_english"].fillna(
            products["product_category_name"]
        )
    except FileNotFoundError:
        products["product_category"] = products["product_category_name"]
    products["product_category"] = products["product_category"].fillna("unknown")
    order_items = items.merge(
        products[["product_id", "product_category"]], on="product_id", how="left", validate="many_to_one"
    ).merge(
        orders[[
            "order_id", "purchased_at", "order_status", "customer_state",
            "late_delivery", "review_score",
        ]], on="order_id", how="left", validate="many_to_one"
    )
    order_items["product_category"] = order_items["product_category"].fillna("unknown")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.stem + ".building.duckdb")
    if temporary.exists():
        temporary.unlink()
    connection = duckdb.connect(str(temporary))
    try:
        connection.register("orders_frame", orders)
        connection.register("items_frame", order_items)
        connection.execute("CREATE TABLE orders AS SELECT * FROM orders_frame")
        connection.execute("CREATE TABLE order_items AS SELECT * FROM items_frame")
        connection.execute("CREATE INDEX orders_id_idx ON orders(order_id)")
        connection.execute("CREATE INDEX items_order_idx ON order_items(order_id)")
        order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        item_count = connection.execute("SELECT COUNT(*) FROM order_items").fetchone()[0]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    os.replace(temporary, target)
    return {"orders": order_count, "order_items": item_count, "database": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Olist zip or directory of CSVs")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Output DuckDB path")
    args = parser.parse_args()
    print(json.dumps(build_database(args.source, args.target), ensure_ascii=False))
