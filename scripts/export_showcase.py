"""Export verified, non-LLM sample data for the static portfolio page."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import run_query  # noqa: E402


def export() -> dict:
    counts = run_query("SELECT COUNT(*) AS orders, SUM(item_count) AS order_lines FROM orders")
    monthly = run_query("""SELECT strftime(purchased_at, '%Y-%m') AS month,
        ROUND(SUM(item_revenue), 2) AS revenue
        FROM orders WHERE order_status = 'delivered'
        AND purchased_at >= '2018-01-01' AND purchased_at < '2019-01-01'
        GROUP BY 1 ORDER BY 1""")
    categories = run_query("""SELECT product_category,
        ROUND(SUM(price), 2) AS revenue FROM order_items
        WHERE order_status = 'delivered'
        AND purchased_at >= '2018-01-01' AND purchased_at < '2019-01-01'
        GROUP BY 1 ORDER BY revenue DESC LIMIT 5""")
    return {
        "dataset": "Brazilian E-Commerce Public Dataset by Olist",
        "orders": counts["rows"][0][0],
        "order_lines": counts["rows"][0][1],
        "currency": "BRL",
        "monthly_revenue_2018": [dict(zip(monthly["columns"], row)) for row in monthly["rows"]],
        "top_categories_2018": [dict(zip(categories["columns"], row)) for row in categories["rows"]],
        "metric_note": "已送达订单的商品价格合计，不含运费；按购买月份统计。2018 年仅覆盖数据集中实际有记录的月份。",
    }


if __name__ == "__main__":
    destination = ROOT / "docs" / "showcase-data.json"
    destination.write_text(json.dumps(export(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved verified sample data: {destination}")
