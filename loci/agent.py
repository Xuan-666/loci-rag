"""
Loci Agent · 工具调用型 RAG Agent (LangGraph)
============================================
基于 LangGraph StateGraph 实现"检索 → 决策 → 兜底"的智能体工作流。

工作流:
    用户问题
       │
       ▼
   [1] retrieve_kb ─────────────┐
       │ 命中且分数足够         │ KB 没答案 / 分数太低
       ▼                        ▼
   [generate_rag          [2] search_web  (可选,Tavily)
       │ 工具已启用          │ 命中
       │                    ▼
       │              [generate_web]
       │
       └────────► [3] generate_llm (纯 LLM 兜底)
                       │
                       ▼
                    END

特性:
- 工具按需调用,失败可降级
- 支持流式输出(每个节点都 yield 当前状态)
- 中间步骤全可观测(用于前端可视化)
- 兼容 Loci RAGEngine、LangChain 工具

注意:
- 这是 v5.2 路线图中的能力(README 路线图已声明)
- 依赖可选: `pip install langgraph langchain-tavily` (未装时优雅降级为单步 RAG)
- 本文件不强制修改 RAGEngine,作为独立模块被 web_api.py 通过 /api/agent/query 调用
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional, TypedDict

# LangChain / LangGraph 核心(轻量)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage


# ---------------------------------------------------------------------------
# State 定义
# ---------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    """Agent 工作流共享状态"""
    question: str          # 用户原始问题
    history: List[BaseMessage]  # 多轮对话历史(LangChain message 格式)
    kb_result: Optional[Dict[str, Any]]    # KB 检索结果
    web_result: Optional[str]   # Web 搜索结果
    answer: Optional[str]      # 最终答案
    steps: List[Dict[str, Any]]  # 中间步骤日志(给前端可视化)
    used_tool: Optional[str]   # 实际使用的工具:"kb" | "web" | "llm"
    error: Optional[str]       # 错误信息


# ---------------------------------------------------------------------------
# 工具封装:把 Loci RAGEngine / Web Search / LLM 包装成 LangGraph 节点
# ---------------------------------------------------------------------------
class LociAgent:
    """
    Loci Agent 主体。
    持有 RAGEngine 引用,对外暴露 run() / stream() 两个方法。
    """

    def __init__(
        self,
        rag_engine,                       # loci.rag_engine.RAGEngine
        web_search: Optional[Callable[[str], str]] = None,  # (query) -> str
        llm_fallback: Optional[Callable[[str], str]] = None,  # (question) -> str
        kb_threshold: float = 0.5,        # 复用 RAGEngine 内部阈值
        use_langgraph: bool = True,
    ):
        self.rag_engine = rag_engine
        self.web_search = web_search
        self.llm_fallback = llm_fallback
        self.kb_threshold = kb_threshold
        self.use_langgraph = use_langgraph and _LANGGRAPH_AVAILABLE

    # -----------------------------------------------------------------------
    # 三个工具节点
    # -----------------------------------------------------------------------
    def _node_retrieve_kb(self, state: AgentState) -> AgentState:
        """节点 1:用 RAGEngine 检索知识库"""
        q = state["question"]
        try:
            result = self.rag_engine.query(q)
            state["kb_result"] = result
            state["steps"].append({
                "tool": "kb",
                "ok": bool(result.get("answer")) and result.get("answer") != "未找到相关内容",
                "summary": f"KB 返回 {len(result.get('sources', []))} 条 sources",
                "fallback": result.get("fallback", False),
            })
            # KB 命中时直接写入最终答案,这样即使路由到 end,final state 也有
            ans = result.get("answer")
            if ans and ans != "未找到相关内容" and not result.get("fallback"):
                state["answer"] = ans
                state["used_tool"] = "kb"
        except Exception as e:
            state["kb_result"] = {"answer": None, "sources": []}
            state["steps"].append({"tool": "kb", "ok": False, "summary": f"KB 异常: {e}"})
        return state

    def _node_search_web(self, state: AgentState) -> AgentState:
        """节点 2:Web 搜索 + LLM 总结(若搜到结果)"""
        if not self.web_search:
            state["steps"].append({"tool": "web", "ok": False, "summary": "未启用 Web 搜索工具"})
            return state
        q = state["question"]
        try:
            web_text = self.web_search(q)
            state["web_result"] = web_text
            state["steps"].append({
                "tool": "web",
                "ok": bool(web_text),
                "summary": (web_text or "")[:120],
            })
            # 搜到结果 → 优先用 LLM 总结;若无 LLM 也直接用 web_text 作为答案
            if web_text:
                if self.rag_engine.llm:
                    try:
                        prompt = f"请基于以下 Web 检索结果回答用户问题。如果信息不足请明确说明。\n\n【Web 结果】\n{web_text}\n\n【问题】{q}"
                        resp = self.rag_engine.llm.invoke(prompt)
                        state["answer"] = resp.content if hasattr(resp, "content") else str(resp)
                        state["used_tool"] = "web"
                    except Exception as e:
                        state["steps"].append({"tool": "web", "ok": False, "summary": f"LLM 总结失败: {e}"})
                        state["answer"] = web_text
                        state["used_tool"] = "web"
                else:
                    state["answer"] = web_text
                    state["used_tool"] = "web"
        except Exception as e:
            state["steps"].append({"tool": "web", "ok": False, "summary": f"Web 异常: {e}"})
        return state

    def _node_generate_llm(self, state: AgentState) -> AgentState:
        """节点 3:纯 LLM 兜底"""
        if not self.llm_fallback or not self.rag_engine.llm:
            state["answer"] = "⚠️ LLM 未配置,无法回答。"
            state["used_tool"] = "llm"
            return state
        try:
            state["answer"] = self.llm_fallback(state["question"])
            state["used_tool"] = "llm"
            state["steps"].append({"tool": "llm", "ok": True, "summary": "纯 LLM 兜底成功"})
        except Exception as e:
            state["answer"] = f"⚠️ LLM 兜底失败: {e}"
            state["used_tool"] = "llm"
            state["steps"].append({"tool": "llm", "ok": False, "summary": str(e)})
        return state

    # -----------------------------------------------------------------------
    # 路由函数:决定下一步去哪
    # 重要:LangGraph 节点函数返回的 state 是新 dict(不可变更新),
    #      所以路由函数应返回 string 路由名,而不是修改 state。
    #      used_tool / answer 由节点函数(NODE)负责写入,而不是路由函数。
    # -----------------------------------------------------------------------
    def _route_after_kb(self, state: AgentState) -> str:
        """KB 检索后,根据命中情况返回下一步路由名"""
        kb = state.get("kb_result") or {}
        ans = kb.get("answer")
        # KB 给了像样的答案(没有 fallback 标记,且非"未找到")
        if ans and ans != "未找到相关内容" and not kb.get("fallback"):
            return "end"
        # 否则尝试 Web
        if self.web_search:
            return "search_web"
        # 没有 Web 就直接 LLM
        return "generate_llm"

    def _route_after_web(self, state: AgentState) -> str:
        """Web 搜索后,根据 _node_search_web 是否已写入 answer 决定路由"""
        # _node_search_web 已经在搜到结果时写入了 answer + used_tool="web"
        if state.get("answer"):
            return "end"
        return "generate_llm"

    # -----------------------------------------------------------------------
    # 主入口
    # -----------------------------------------------------------------------
    def run(
        self,
        question: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        同步执行 Agent。
        :param question: 用户问题
        :param history: 多轮历史,格式 [{"role": "user"|"assistant", "content": "..."}]
        :return: {
            "answer": str,
            "used_tool": "kb" | "web" | "llm",
            "steps": [{"tool": ..., "ok": ..., "summary": ...}, ...],
        }
        """
        if not self.use_langgraph:
            return self._run_simple(question, history)

        from langgraph.graph import END, StateGraph

        # 构造 state
        lc_history = []
        for h in (history or []):
            if h["role"] == "user":
                lc_history.append(HumanMessage(content=h["content"]))
            else:
                lc_history.append(AIMessage(content=h["content"]))

        initial_state: AgentState = {
            "question": question,
            "history": lc_history,
            "kb_result": None,
            "web_result": None,
            "answer": None,
            "steps": [],
            "used_tool": None,
            "error": None,
        }

        # 构图
        graph = StateGraph(AgentState)
        graph.add_node("retrieve_kb", self._node_retrieve_kb)
        graph.add_node("search_web", self._node_search_web)
        graph.add_node("generate_llm", self._node_generate_llm)

        graph.set_entry_point("retrieve_kb")
        graph.add_conditional_edges(
            "retrieve_kb",
            self._route_after_kb,
            {"search_web": "search_web", "generate_llm": "generate_llm", "end": END},
        )
        graph.add_conditional_edges(
            "search_web",
            self._route_after_web,
            {"generate_llm": "generate_llm", "end": END},
        )
        graph.add_edge("generate_llm", END)

        app = graph.compile()
        final = app.invoke(initial_state)
        return {
            "answer": final.get("answer") or "⚠️ Agent 未产出答案",
            "used_tool": final.get("used_tool"),
            "steps": final.get("steps", []),
        }

    def _run_simple(
        self, question: str, history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """LangGraph 不可用时的简化版(直接 RAG)"""
        steps = []
        try:
            result = self.rag_engine.query(question)
            steps.append({
                "tool": "kb",
                "ok": bool(result.get("answer")),
                "summary": f"KB 返回 {len(result.get('sources', []))} 条 sources",
            })
            return {
                "answer": result.get("answer", "未找到相关内容"),
                "used_tool": "kb",
                "steps": steps,
            }
        except Exception as e:
            return {
                "answer": f"⚠️ Agent 失败: {e}",
                "used_tool": "llm",
                "steps": steps,
            }


# ---------------------------------------------------------------------------
# 可选依赖检测
# ---------------------------------------------------------------------------
try:
    from langgraph.graph import END, StateGraph  # noqa: F401
    _LANGGRAPH_AVAILABLE = True
except ImportError:
    _LANGGRAPH_AVAILABLE = False


# ---------------------------------------------------------------------------
# 工厂:从 RAGEngine 一键构造 Agent
# ---------------------------------------------------------------------------
def build_agent(
    rag_engine,
    enable_web: bool = False,
    tavily_api_key: Optional[str] = None,
) -> LociAgent:
    """
    构造 LociAgent 实例。
    :param rag_engine: loci.rag_engine.RAGEngine 实例
    :param enable_web: 是否启用 Web 搜索(默认 False)
    :param tavily_api_key: Tavily API Key(enable_web=True 时使用)
    """
    web_search = None
    if enable_web:
        try:
            from langchain_community.tools.tavily_search import TavilySearchResults
            tavily = TavilySearchResults(
                max_results=3,
                tavily_api_key=tavily_api_key or os.getenv("TAVILY_API_KEY"),
            )
            def _web(q: str) -> str:
                results = tavily.invoke({"query": q})
                if isinstance(results, list):
                    return "\n\n".join(
                        f"[{i+1}] {r.get('title','')}\n{r.get('content','')}"
                        for i, r in enumerate(results)
                    )
                return str(results)
            web_search = _web
        except ImportError:
            print("[Agent] ⚠️ 未安装 langchain-tavily,Web 工具不可用")

    def _llm_fallback(q: str) -> str:
        if not rag_engine.llm:
            return "⚠️ LLM 未连接"
        resp = rag_engine.llm.invoke(
            f"请直接回答以下问题,不需要参考任何外部资料。如果不知道就明确说不知道。\n\n问题: {q}"
        )
        return resp.content if hasattr(resp, "content") else str(resp)

    return LociAgent(
        rag_engine=rag_engine,
        web_search=web_search,
        llm_fallback=_llm_fallback,
    )
