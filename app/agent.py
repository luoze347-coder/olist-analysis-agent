"""A bounded LangChain tool loop for grounded e-commerce analysis."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

from app.database import run_query
from app.metrics import DATA_DICTIONARY
from app.skills import load_analysis_skill


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_schema",
            "description": "Read the approved database schema and metric definitions. Call before querying.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Execute one read-only DuckDB SELECT query against approved tables.",
            "parameters": {
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "A single DuckDB SELECT query"}},
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cannot_answer",
            "description": "Use if the requested metric is absent, or the question needs clarification.",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are a careful data analyst for a historical Brazilian e-commerce dataset.
Reply to the user in Chinese. Always call get_schema before run_sql.
Never invent figures, columns, business events, or causal explanations.
Use run_sql for every answer that states facts from the data. If the data
cannot answer the question, call cannot_answer and explain the missing data.
Use delivered orders for sales, and clearly state the time period and metric.
For review-score distributions, exclude rows with NULL review_score.
For multi-part questions, run more than one query if necessary, within the
available limit. Your final answer should be short: headline finding,
supporting numbers, and a caveat where needed. Cite the SQL result as 查询1,
查询2, etc. A relationship in observational data is not causation.
"""


class AgentError(RuntimeError):
    pass


def make_model():
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise AgentError("当前终端未读取到 DEEPSEEK_API_KEY，请在启动服务的终端检查用户环境变量。")
    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        base_url="https://api.deepseek.com",
        api_key=key,
        temperature=0,
        timeout=45,
        max_retries=1,
    )


def analyze(
    question: str,
    history: list[dict[str, str]] | None = None,
    *,
    model: Any = None,
    query_runner: Callable[[str], dict] = run_query,
) -> dict:
    if len(question.strip()) < 3:
        raise ValueError("问题至少需要 3 个字符")
    if len(question) > 1000:
        raise ValueError("问题不能超过 1000 个字符")

    tool_model = (model or make_model()).bind_tools(TOOL_SCHEMAS)
    started = time.perf_counter()
    usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    messages = [SystemMessage(content=f"{SYSTEM_PROMPT}\n\nApproved analysis skill:\n{load_analysis_skill()}")]
    for turn in (history or [])[-4:]:
        role, content = turn.get("role"), turn.get("content", "")[:1000]
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=question))

    saw_schema = False
    sql_attempts = 0
    sql_errors = 0
    tool_calls = 0
    queries: list[dict] = []

    def metadata() -> dict:
        return {
            "elapsed_s": round(time.perf_counter() - started, 2),
            **usage,
            "tool_calls": tool_calls,
            "sql_attempts": sql_attempts,
            "sql_errors": sql_errors,
            "skill": "ecommerce-analysis",
        }

    for _ in range(7):
        answer = tool_model.invoke(messages)
        for key in usage:
            usage[key] += int((getattr(answer, "usage_metadata", None) or {}).get(key, 0) or 0)
        messages.append(answer)
        calls = getattr(answer, "tool_calls", []) or []
        if not calls:
            if not queries:
                raise AgentError("模型未完成数据查询；为避免无依据的回答，本次分析已停止。")
            return {
                "status": "answered",
                "answer": str(answer.content),
                "queries": queries,
                "chart": _chart_spec(queries[-1]),
                "meta": metadata(),
            }
        for call in calls:
            tool_calls += 1
            name = call.get("name")
            args = call.get("args") or {}
            tool_result: dict[str, Any]
            if name == "get_schema":
                saw_schema = True
                tool_result = {"schema": DATA_DICTIONARY}
            elif name == "cannot_answer":
                return {
                    "status": "unsupported",
                    "answer": str(args.get("reason") or "现有数据不足以回答这个问题。"),
                    "queries": queries,
                    "chart": None,
                    "meta": metadata(),
                }
            elif name == "run_sql":
                if not saw_schema:
                    tool_result = {"error": "Call get_schema before run_sql."}
                elif sql_attempts >= 3:
                    tool_result = {"error": "SQL attempt limit reached. Explain the failure."}
                else:
                    sql_attempts += 1
                    try:
                        result = query_runner(str(args.get("sql", "")))
                        queries.append(result)
                        tool_result = {"query_id": f"查询{len(queries)}", **result}
                        # Limit model context, while preserving the full result for UI.
                        tool_result["rows"] = result["rows"][:30]
                    except Exception as exc:
                        sql_errors += 1
                        tool_result = {"error": str(exc)[:500]}
            else:
                tool_result = {"error": "Unknown tool"}
            messages.append(ToolMessage(content=json.dumps(tool_result, ensure_ascii=False, default=str), tool_call_id=call["id"]))
    raise AgentError("分析步骤超出上限，请将问题拆得更具体。")


def _chart_spec(query: dict) -> dict | None:
    columns, rows = query.get("columns", []), query.get("rows", [])
    if len(columns) < 2 or not rows or len(rows) > 30:
        return None
    numeric_idx = next((i for i in range(1, len(columns)) if all(
        row[i] is None or isinstance(row[i], (int, float)) for row in rows
    )), None)
    if numeric_idx is None:
        return None
    return {
        "type": "line" if any(token in columns[0].lower() for token in ("month", "date", "week", "day", "月份", "日期")) else "bar",
        "x": [str(row[0]) for row in rows],
        "y": [row[numeric_idx] for row in rows],
        "x_label": columns[0],
        "y_label": columns[numeric_idx],
    }
