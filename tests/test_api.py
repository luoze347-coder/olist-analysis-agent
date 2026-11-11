from fastapi.testclient import TestClient

import app.main as main


def test_local_page_and_analyze_contract(monkeypatch, tmp_path):
    database = tmp_path / "ready.duckdb"
    database.touch()
    monkeypatch.setattr(main, "DATABASE_PATH", database)
    monkeypatch.setattr(main, "analyze", lambda question, history: {
        "status": "answered",
        "answer": "测试结论（查询1）。",
        "queries": [{"sql": "SELECT 1", "columns": ["value"], "rows": [[1]], "row_count": 1}],
        "chart": None,
        "meta": {"elapsed_s": 0.01, "total_tokens": 0},
    })
    client = TestClient(main.app)
    assert client.get("/health").json() == {"status": "ok", "database_ready": True}
    assert "电商经营分析 Agent" in client.get("/").text
    response = client.post("/analyze", json={"question": "2018年销售额是多少？", "history": []})
    assert response.status_code == 200
    assert response.json()["queries"][0]["rows"] == [[1]]
