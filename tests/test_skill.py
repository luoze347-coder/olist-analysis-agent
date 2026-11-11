from langchain_core.messages import AIMessage, SystemMessage

from app.agent import AgentError, analyze
from app.skills import load_analysis_skill


def test_bundled_skill_has_domain_rules():
    skill = load_analysis_skill()
    assert "get_schema" in skill
    assert "freight" in skill
    assert "cannot_answer" in skill


def test_agent_includes_skill_in_system_message():
    class InspectModel:
        def bind_tools(self, _tools):
            return self

        def invoke(self, messages):
            assert isinstance(messages[0], SystemMessage)
            assert "Approved analysis skill:" in messages[0].content
            assert "freight" in messages[0].content
            return AIMessage(content="No data")

    try:
        analyze("请分析销售额", model=InspectModel())
    except AgentError:
        pass
    else:
        raise AssertionError("Agent accepted an ungrounded response")
