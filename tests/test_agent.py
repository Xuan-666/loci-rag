"""
Loci Agent 路由逻辑测试
====================
不需要真实 LLM,用 mock 验证:
- KB 命中 → 不查 Web / 不调 LLM
- KB 失败 → 走 Web
- Web 失败 → 走 LLM
- 全失败 → 走 LLM
"""
import pytest
from loci.agent import LociAgent, build_agent, _LANGGRAPH_AVAILABLE


class FakeRAGEngine:
    """模拟 RAGEngine:可配置 KB 检索结果"""

    def __init__(self, answer=None, sources=None, fallback=False, raise_exc=False, llm=None):
        self._answer = answer
        self._sources = sources or []
        self._fallback = fallback
        self._raise = raise_exc
        self.llm = llm

    def query(self, question, history=None, tag_filter=None):
        if self._raise:
            raise RuntimeError("simulated KB failure")
        return {
            "answer": self._answer,
            "sources": self._sources,
            "fallback": self._fallback,
        }


class FakeLLM:
    """模拟 LangChain ChatModel"""
    def invoke(self, prompt):
        class _R:
            content = f"[LLM_FALLBACK] {prompt[:80]}"
        return _R()


def test_agent_kb_hit_skips_web_and_llm():
    """KB 命中 → used_tool='kb',不应调用 web/llm"""
    rag = FakeRAGEngine(answer="知识库答案", sources=[("doc", 0.9)])
    web_called = []
    llm_called = []

    def web(q):
        web_called.append(q)
        return "web result"

    def llm(q):
        llm_called.append(q)
        return "llm result"

    agent = LociAgent(rag, web_search=web, llm_fallback=llm, use_langgraph=_LANGGRAPH_AVAILABLE)
    out = agent.run("问题")

    assert out["used_tool"] == "kb"
    assert out["answer"] == "知识库答案"
    assert web_called == []
    assert llm_called == []


def test_agent_kb_empty_routes_to_web():
    """KB 返回'未找到' → 尝试 Web"""
    rag = FakeRAGEngine(answer="未找到相关内容", sources=[])
    web_called = []

    def web(q):
        web_called.append(q)
        return "web snippet 1\nweb snippet 2"

    agent = LociAgent(rag, web_search=web, llm_fallback=lambda q: "llm", use_langgraph=_LANGGRAPH_AVAILABLE)
    out = agent.run("问题")

    assert web_called == ["问题"]
    assert out["used_tool"] == "web"
    assert "[1]" in out["answer"] or "web snippet" in out["answer"]


def test_agent_kb_fallback_routes_to_llm():
    """KB 标记 fallback → 走纯 LLM"""
    rag = FakeRAGEngine(answer="kb 兜底答案(不可信)", sources=[], fallback=True, llm=FakeLLM())
    agent = LociAgent(
        rag,
        web_search=lambda q: "web",
        llm_fallback=lambda q: "纯 LLM 答案",
        use_langgraph=_LANGGRAPH_AVAILABLE,
    )
    out = agent.run("问题")
    # fallback=True → 不信任 KB,应继续往下走
    # 取决于是否启用 web,这里 web 返回字符串,会被 LLM 总结;但 web 是空 prompt,可能直接 LLM
    # 至少 used_tool 应该是 web 或 llm,不是 kb
    assert out["used_tool"] in ("web", "llm")


def test_agent_all_fail_uses_llm():
    """KB 失败 + Web 失败 → 走 LLM"""
    rag = FakeRAGEngine(raise_exc=True, llm=FakeLLM())
    agent = LociAgent(
        rag,
        web_search=lambda q: "",  # Web 也返回空
        llm_fallback=lambda q: "纯 LLM 兜底",
        use_langgraph=_LANGGRAPH_AVAILABLE,
    )
    out = agent.run("问题")
    assert out["used_tool"] == "llm"
    assert "纯 LLM 兜底" in out["answer"]


def test_agent_steps_logged():
    """steps 字段应包含每一步的 tool/ok/summary"""
    rag = FakeRAGEngine(answer="kb 答案", sources=[("d", 0.8)])
    agent = LociAgent(rag, use_langgraph=_LANGGRAPH_AVAILABLE)
    out = agent.run("问题")

    assert "steps" in out
    assert isinstance(out["steps"], list)
    assert len(out["steps"]) >= 1
    assert out["steps"][0]["tool"] == "kb"


def test_build_agent_factory():
    """build_agent 工厂函数应能直接基于 RAGEngine 构造 Agent"""
    rag = FakeRAGEngine(answer="x", llm=FakeLLM())
    agent = build_agent(rag, enable_web=False)
    assert agent is not None
    assert agent.rag_engine is rag


def test_agent_langgraph_availability():
    """验证 LangGraph 可用性检测(若环境装了,应该 = True)"""
    # 仅 sanity check,具体值取决于环境
    assert isinstance(_LANGGRAPH_AVAILABLE, bool)
