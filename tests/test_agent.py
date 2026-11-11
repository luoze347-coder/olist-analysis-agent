from langchain_core.messages import AIMessage

from app.agent import AgentError, analyze


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)

    def bind_tools(self, _schemas):
        return self

    def invoke(self, _messages):
        return next(self.responses)


def call(name, args, identifier):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": identifier}])


def test_grounded_agent_returns_query_and_answer():
    model = FakeModel([
        call("get_schema", {}, "1"),
        call("run_sql", {"sql": "SELECT customer_state, COUNT(*) AS orders FROM orders GROUP BY 1"}, "2"),
        AIMessage(content="SP 有 2 笔订单（查询1）。"),
    ])
    def runner(sql):
        return {"sql": sql, "columns": ["customer_state", "orders"], "rows": [["SP", 2]], "row_count": 1}
    output = analyze("哪个州的订单多？", model=model, query_runner=runner)
    assert output["status"] == "answered"
    assert len(output["queries"]) == 1
    assert output["chart"]["y"] == [2]


def test_agent_can_decline_missing_metric():
    model = FakeModel([call("get_schema", {}, "1"), call("cannot_answer", {"reason": "没有曝光数据"}, "2")])
    output = analyze("广告点击转化率是多少？", model=model)
    assert output["status"] == "unsupported"
    assert "没有曝光数据" in output["answer"]


def test_agent_does_not_answer_without_data():
    model = FakeModel([AIMessage(content="销售额是 100。")])
    try:
        analyze("上月销售额是多少？", model=model)
    except AgentError as exc:
        assert "未完成数据查询" in str(exc)
    else:
        raise AssertionError("Ungrounded answer was accepted")
