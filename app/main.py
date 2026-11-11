"""Web API and self-contained browser UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from plotly.offline import get_plotlyjs

from app.agent import AgentError, analyze
from app.database import DATABASE_PATH

app = FastAPI(title="电商经营分析 Agent", version="0.1.0")
WEB_PATH = Path(__file__).resolve().parents[1] / "web" / "index.html"


class HistoryTurn(BaseModel):
    role: str
    content: str = Field(max_length=1000)


class AnalyzeRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=4)


@app.get("/", response_class=HTMLResponse)
def index():
    return WEB_PATH.read_text(encoding="utf-8")


@app.get("/plotly.min.js")
def plotly_js():
    return Response(get_plotlyjs(), media_type="application/javascript")


@app.get("/health")
def health():
    return {"status": "ok", "database_ready": DATABASE_PATH.exists()}


@app.post("/analyze")
def analyze_endpoint(request: AnalyzeRequest):
    if not DATABASE_PATH.exists():
        raise HTTPException(status_code=503, detail="分析数据库尚未准备，请先运行数据准备脚本。")
    try:
        return analyze(request.question, [turn.model_dump() for turn in request.history])
    except (AgentError, ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Do not leak provider error bodies or secrets to a browser.
        raise HTTPException(status_code=502, detail="模型或数据库暂时不可用，请检查本地服务日志。") from exc
