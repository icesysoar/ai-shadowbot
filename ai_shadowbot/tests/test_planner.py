"""TDD 红阶段：规划层（F001）测试。

覆盖：
  - function-calling tools schema 含全部 9 个原子动作（AC2 schema 对齐）
  - 多步分解（≥3 步）映射到已注册原语（AC2）
  - 规划幻觉（无法规划）安全降级：不编造动作，返回原因（AC3）
  - 模型返回非法/未知动作：schema 强校验拦截，不崩溃（AC1）
  - mock 模式：无需真实 API key 即可产出计划（驱动 dry_run 演示）

迁移知识：
  - 「动作生成 ≠ 动作执行」：planner 只负责"生成"，执行校验交给 guardrails/executor。
  - 「原子动作词汇表」：planner 输出只能落在白名单原子动作上。
"""
import pytest

from ai_shadowbot.actions import build_tool_schema
from ai_shadowbot.config import Config
from ai_shadowbot.planner import Planner, MockLLMClient, PlanResult


ALL_ACTION_NAMES = {
    "click", "double_click", "right_click", "type_text", "key_press",
    "screenshot", "wait", "open_app", "scroll",
    # F016: Excel/CSV
    "excel_read", "excel_write",
    # F017: HTTP
    "http_request", "http_get", "http_post", "http_put", "http_delete",
    # F019: 文件系统
    "fs_read", "fs_write", "fs_append", "fs_copy", "fs_move",
    "fs_delete", "fs_list", "fs_mkdir", "fs_exists", "fs_info",
}


def test_tool_schema_contains_all_atomic_actions():
    tools = build_tool_schema()
    names = {t["function"]["name"] for t in tools}
    assert names == ALL_ACTION_NAMES
    # 每个 tool 都有合法 parameters.required
    for t in tools:
        assert "parameters" in t["function"]
        assert isinstance(t["function"]["parameters"]["required"], list)


def test_plan_two_steps_opens_notepad_and_types():
    mock = MockLLMClient([
        {"name": "open_app", "args": {"name": "notepad"}},
        {"name": "type_text", "args": {"text": "hello"}},
    ])
    p = Planner(Config(mock=True), llm_client=mock)
    r: PlanResult = p.plan("打开记事本并输入 hello")
    assert r.success is True
    assert len(r.actions) == 2
    assert r.actions[0].type == "open_app"
    assert r.actions[0].params["name"] == "notepad"
    assert r.actions[1].type == "type_text"
    assert r.actions[1].params["text"] == "hello"


def test_plan_three_steps():
    mock = MockLLMClient([
        {"name": "open_app", "args": {"name": "calc"}},
        {"name": "click", "args": {"x": 100, "y": 100}},
        {"name": "wait", "args": {"seconds": 1}},
    ])
    p = Planner(Config(mock=True), llm_client=mock)
    r = p.plan("打开计算器并点击然后等待")
    assert r.success is True
    assert len(r.actions) == 3
    assert {a.type for a in r.actions} == {"open_app", "click", "wait"}


def test_planning_hallucination_safe_degrade():
    # 模型未返回任何 tool_calls → 无法规划，安全降级
    mock = MockLLMClient([])
    p = Planner(Config(mock=True), llm_client=mock)
    r = p.plan("做一道量子料理并送到火星")
    assert r.success is False
    assert r.actions == []
    assert r.reason  # 必须给出非空原因，不得编造动作


def test_illegal_action_from_model_is_blocked_by_schema():
    # 模型幻觉出未知动作 → planner schema 强校验拦截，不崩溃
    mock = MockLLMClient([{"name": "launch_nukes", "args": {}}])
    p = Planner(Config(mock=True), llm_client=mock)
    r = p.plan("毁灭世界")
    assert r.success is False
    assert r.actions == []
    assert "未知" in r.reason or "白名单" in r.reason


def test_mock_mode_works_without_api_key():
    # 默认 mock 客户端带启发式：识别"打开X并输入Y"
    cfg = Config(mock=True)  # 无 api_key
    p = Planner(cfg)
    r = p.plan("打开记事本并输入 hello")
    assert r.success is True
    assert r.actions[0].type == "open_app"
    assert r.actions[1].type == "type_text"


def test_screenshot_context_accepted():
    # 截图上下文输入不报错（AC4 视觉闭环）
    mock = MockLLMClient([{"name": "screenshot", "args": {}}])
    p = Planner(Config(mock=True), llm_client=mock)
    r = p.plan("看一眼屏幕", screenshot_b64="iVBORw0KGgoAAAANSUhEUg==")
    assert r.success is True
    assert r.actions[0].type == "screenshot"
