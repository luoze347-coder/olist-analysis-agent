"""Offline gold-SQL validation, with optional live Agent evaluation."""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent import analyze  # noqa: E402
from app.database import run_query  # noqa: E402
from app.skills import load_analysis_skill  # noqa: E402
from app.sql_guard import UnsafeQuery  # noqa: E402


SAFETY_PROBES = [
    "DELETE FROM orders",
    "SELECT * FROM orders; DROP TABLE orders",
    "SELECT * FROM read_csv_auto('C:/private.csv')",
    "SELECT * FROM unknown_table",
]


def check_safety() -> dict:
    """Exercise the production query path without sending data to a model."""
    failures = []
    for sql in SAFETY_PROBES:
        try:
            run_query(sql)
        except UnsafeQuery:
            continue
        except Exception as exc:
            failures.append({"sql": sql, "error": f"unexpected {type(exc).__name__}"})
        else:
            failures.append({"sql": sql, "error": "unsafe SQL was accepted"})
    return {"passed": len(SAFETY_PROBES) - len(failures), "total": len(SAFETY_PROBES), "failures": failures}


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5)))
    return round(ordered[index], 2)


def normalized_rows(rows):
    def normalize(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(float(value), 2)
        return str(value)
    return sorted([tuple(normalize(value) for value in row) for row in rows], key=str)


def result_matches(actual: dict, gold: dict, mode: str = "exact") -> bool:
    """Compare gold values, permitting harmless extra result columns."""
    if mode == "grouped_mean":
        if len(gold["columns"]) != 2 or not gold["rows"]:
            return False
        for key_index, value_index in itertools.permutations(range(len(actual["columns"])), 2):
            groups = {row[key_index]: row[value_index] for row in actual["rows"]
                      if row[key_index] is not None}
            if len(groups) != len(gold["rows"]):
                continue
            if all(key in groups and isinstance(groups[key], (int, float))
                   and abs(float(groups[key]) - float(value)) <= 0.01
                   for key, value in gold["rows"]):
                return True
        return False
    if mode != "max_row" and len(actual["rows"]) != len(gold["rows"]):
        return False
    gold_width = len(gold["columns"])
    if len(actual["columns"]) < gold_width:
        return False
    expected = normalized_rows(gold["rows"])
    for indexes in itertools.combinations(range(len(actual["columns"])), gold_width):
        projected = [[row[index] for index in indexes] for row in actual["rows"]]
        if normalized_rows(projected) == expected:
            return True
        if mode == "max_row" and len(gold["rows"]) == 1 and gold_width == 2:
            winner = max(projected, key=lambda row: float(row[1]) if row[1] is not None else float("-inf"))
            if normalized_rows([winner]) == expected:
                return True
        # A ratio (0..1) and percentage (0..100) are equivalent presentations.
        scaled = [row.copy() for row in projected]
        for position, index in enumerate(indexes):
            if "pct" in gold["columns"][position].lower() and "rate" in actual["columns"][index].lower():
                for row in scaled:
                    if isinstance(row[position], (int, float)):
                        row[position] *= 100
        if normalized_rows(scaled) == expected:
            return True
    return False


def evaluate(cases: list[dict], live: bool = False, limit: int | None = None) -> dict:
    results = []
    for case in cases[:limit]:
        item = {"id": case["id"], "question": case["question"]}
        gold = None
        if not case.get("unsupported"):
            try:
                gold = run_query(case["gold_sql"])
                item["gold_rows"] = gold["row_count"]
            except Exception as exc:
                item["gold_error"] = str(exc)
        if live:
            started = time.perf_counter()
            try:
                actual = analyze(case["question"])
                item["status"] = actual["status"]
                item["sql_success"] = bool(actual["queries"])
                item["correct"] = (
                    actual["status"] == "unsupported" if case.get("unsupported") else
                    actual["status"] == "answered" and gold is not None and
                    any(result_matches(query, gold, case.get("match_mode", "exact"))
                        for query in actual["queries"])
                )
                item["answer"] = actual["answer"]
                item["queries"] = [query["sql"] for query in actual["queries"]]
                item["usage"] = actual.get("meta", {})
            except Exception as exc:
                item["correct"] = False
                item["error"] = str(exc)
            item["elapsed_s"] = round(time.perf_counter() - started, 2)
        results.append(item)
    scored = [item for item in results if "correct" in item]
    answerable = [item for item, case in zip(results, cases[:limit]) if "correct" in item and not case.get("unsupported")]
    unsupported = [item for item, case in zip(results, cases[:limit]) if "correct" in item and case.get("unsupported")]
    rate = lambda items, key: round(sum(bool(item.get(key)) for item in items) / len(items), 3) if items else None
    return {
        "mode": "live" if live else "gold-check",
        "cases": len(results),
        "gold_errors": sum("gold_error" in item for item in results),
        "safety": check_safety(),
        "skill_loaded": bool(load_analysis_skill()),
        "exact_result_accuracy": rate(scored, "correct"),
        "answerable_accuracy": rate(answerable, "correct"),
        "unsupported_refusal_rate": rate(unsupported, "correct"),
        "sql_success_rate": rate(answerable, "sql_success"),
        "mean_elapsed_s": round(sum(item["elapsed_s"] for item in scored) / len(scored), 2) if scored else None,
        "p95_elapsed_s": percentile([item["elapsed_s"] for item in scored], 0.95),
        "total_sql_errors": sum(item.get("usage", {}).get("sql_errors", 0) for item in scored),
        "total_tokens": sum(item.get("usage", {}).get("total_tokens", 0) for item in scored),
        "results": results,
    }


def rescore(cases: list[dict], report: dict) -> dict:
    """Recheck saved SQL against gold data without another model call."""
    case_by_id = {case["id"]: case for case in cases}
    results = report["results"]
    if len(results) != len({item["id"] for item in results}):
        raise ValueError("Duplicate case IDs in saved report")
    for item in results:
        case = case_by_id[item["id"]]
        if case.get("unsupported"):
            item["correct"] = item.get("status") == "unsupported"
            continue
        gold = run_query(case["gold_sql"])
        item["correct"] = item.get("status") == "answered" and any(
            result_matches(run_query(sql), gold, case.get("match_mode", "exact"))
            for sql in item.get("queries", [])
        )
    scored = [item for item in results if "correct" in item]
    answerable = [item for item in scored if not case_by_id[item["id"]].get("unsupported")]
    unsupported = [item for item in scored if case_by_id[item["id"]].get("unsupported")]
    rate = lambda items: round(sum(item["correct"] for item in items) / len(items), 3) if items else None
    report["exact_result_accuracy"] = rate(scored)
    report["answerable_accuracy"] = rate(answerable)
    report["unsupported_refusal_rate"] = rate(unsupported)
    report["safety"] = check_safety()
    report["skill_loaded"] = bool(load_analysis_skill())
    report["scoring_note"] = (
        "Saved model SQL rechecked locally; grouped means allow 0.01 "
        "rounding tolerance and exclude NULL group keys."
    )
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call DeepSeek for each question; incurs API charges")
    parser.add_argument("--limit", type=int, help="Only evaluate the first N cases")
    parser.add_argument("--output", type=Path, help="Write the report as JSON")
    parser.add_argument("--rescore", type=Path, help="Recheck saved report without model calls")
    args = parser.parse_args()
    cases = json.loads((ROOT / "eval" / "cases.json").read_text(encoding="utf-8"))
    report = (rescore(cases, json.loads(args.rescore.read_text(encoding="utf-8")))
              if args.rescore else evaluate(cases, live=args.live, limit=args.limit))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Saved {report['mode']} report: {args.output}")
    else:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        print(text)
