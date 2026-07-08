"""测试 F006 工作流数据结构（workflow.py）—— DAG 校验 / 序列化 / 变量解析。

铁律：
  - 不依赖真实 LLM（全部 mock）
  - 不修改现有代码逻辑（additive）
"""
from __future__ import annotations

import json
import pytest

from ai_shadowbot.workflow import (
    ErrorStrategy,
    ErrorStrategyType,
    Node,
    NodeType,
    Trigger,
    TriggerType,
    Variable,
    VariableType,
    VariableScopeType,
    Workflow,
    WorkflowSchema,
    WorkflowValidationError,
    parse_variable_ref,
)


# ======================================================================
# Workflow 基本序列化/反序列化
# ======================================================================

class TestWorkflowSerialization:
    def test_workflow_to_dict(self):
        wf = Workflow(
            id="wf_test0001",
            name="测试工作流",
            nodes=[
                Node(id="n1", type=NodeType.start, next="n2"),
                Node(id="n2", type=NodeType.atomic,
                     params={"atomic_action": "screenshot"},
                     next="n3"),
                Node(id="n3", type=NodeType.end),
            ],
        )
        d = wf.to_dict()
        assert d["id"] == "wf_test0001"
        assert len(d["nodes"]) == 3
        assert d["nodes"][0]["type"] == "start"

    def test_workflow_from_dict(self):
        data = {
            "id": "wf_test0002",
            "name": "测试",
            "nodes": [
                {"id": "n1", "type": "start", "params": {}, "next": "n2"},
                {"id": "n2", "type": "atomic",
                 "params": {"atomic_action": "screenshot"},
                 "next": "n3"},
                {"id": "n3", "type": "end", "params": {}},
            ],
            "variables": {
                "count": {"type": "int", "default": 0, "scope": "global"},
            },
        }
        wf = Workflow.from_dict(data)
        assert wf.id == "wf_test0002"
        assert len(wf.nodes) == 3
        assert wf.nodes[0].type == NodeType.start
        assert wf.variables["count"].type == VariableType.int_type
        assert wf.variables["count"].default == 0

    def test_roundtrip_serialization(self):
        wf = Workflow(
            id="wf_abcd1234",
            name="循环测试",
            nodes=[
                Node(id="n1", type=NodeType.start, next="n2"),
                Node(id="n2", type=NodeType.loop,
                     params={"loop_type": "while", "condition": "true",
                             "max_iterations": 5},
                     children=["n3"],
                     continue_on="n4"),
                Node(id="n3", type=NodeType.atomic,
                     params={"atomic_action": "wait", "seconds": 1},
                     next="n2"),
                Node(id="n4", type=NodeType.end),
            ],
            triggers=[Trigger(type=TriggerType.manual)],
            error_strategy=ErrorStrategy(type=ErrorStrategyType.retry_type),
        )
        d = wf.to_dict()
        wf2 = Workflow.from_dict(d)
        assert wf2.id == wf.id
        assert wf2.nodes[1].type == NodeType.loop
        assert wf2.nodes[1].params["max_iterations"] == 5
        assert wf2.triggers[0].type == TriggerType.manual
        assert wf2.error_strategy.type == ErrorStrategyType.retry_type


# ======================================================================
# DAG 正确性校验
# ======================================================================

class TestWorkflowValidation:
    def test_valid_linear_workflow(self):
        """有效线性工作流。"""
        wf = Workflow(
            id="wf_valid001", name="有效",
            nodes=[
                Node(id="n1", type=NodeType.start, next="n2"),
                Node(id="n2", type=NodeType.atomic,
                     params={"atomic_action": "screenshot"},
                     next="n3"),
                Node(id="n3", type=NodeType.end),
            ],
        )
        WorkflowSchema.validate(wf)  # 不应抛出

    def test_missing_start(self):
        """缺 start 节点。"""
        wf = Workflow(id="wf_err001", name="错",
                      nodes=[
                          Node(id="n1", type=NodeType.atomic,
                               params={"atomic_action": "screenshot"}),
                          Node(id="n2", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="start"):
            WorkflowSchema.validate(wf)

    def test_duplicate_start(self):
        """多个 start 节点。"""
        wf = Workflow(id="wf_err002", name="错",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n3"),
                          Node(id="n2", type=NodeType.start, next="n3"),
                          Node(id="n3", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="start"):
            WorkflowSchema.validate(wf)

    def test_missing_end(self):
        """缺 end 节点。"""
        wf = Workflow(id="wf_err003", name="错",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.atomic,
                               params={"atomic_action": "screenshot"}),
                      ])
        with pytest.raises(WorkflowValidationError, match="end"):
            WorkflowSchema.validate(wf)

    def test_duplicate_node_id(self):
        """节点 ID 重复。"""
        wf = Workflow(id="wf_err004", name="错",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n1", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="重复"):
            WorkflowSchema.validate(wf)

    def test_invalid_ref(self):
        """next 指向不存在的节点。"""
        wf = Workflow(id="wf_err005", name="错",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n99"),
                          Node(id="n2", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="n99"):
            WorkflowSchema.validate(wf)

    def test_cycle_in_dag(self):
        """环路检测。"""
        wf = Workflow(id="wf_cycle001", name="环",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.atomic,
                               params={"atomic_action": "screenshot"},
                               next="n3"),
                          Node(id="n3", type=NodeType.atomic,
                               params={"atomic_action": "wait", "seconds": 1},
                               next="n2"),  # 回到 n2 -> 环路
                          Node(id="n4", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="环路|cycle|环"):
            WorkflowSchema.validate(wf)

    def test_condition_min_branches(self):
        """condition 节点至少 2 条分支。"""
        wf = Workflow(id="wf_cond001", name="分支不够",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.condition,
                               params={"expression": "true"},
                               branches=[{"condition": "true", "next": "n3"}]),
                          Node(id="n3", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="分支|branches"):
            WorkflowSchema.validate(wf)

    def test_loop_min_children(self):
        """loop 节点至少 1 个子节点。"""
        wf = Workflow(id="wf_loop001", name="loop 无子",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.loop,
                               params={"loop_type": "while", "condition": "true"},
                               children=[], continue_on="n3"),
                          Node(id="n3", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="children|子节点"):
            WorkflowSchema.validate(wf)

    def test_loop_max_iterations_limit(self):
        """loop.max_iterations 超过 1000。"""
        wf = Workflow(id="wf_loop002", name="超上限",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.loop,
                               params={"loop_type": "while", "condition": "true",
                                       "max_iterations": 2000},
                               children=["n3"], continue_on="n4"),
                          Node(id="n3", type=NodeType.atomic,
                               params={"atomic_action": "screenshot"},
                               next="n2"),
                          Node(id="n4", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="1000|iterations"):
            WorkflowSchema.validate(wf)

    def test_loop_valid_iterations(self):
        """loop.max_iterations 合法。"""
        wf = Workflow(id="wf_loop003", name="合法上限",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.loop,
                               params={"loop_type": "while", "condition": "true",
                                       "max_iterations": 100},
                               children=["n3"], continue_on="n4"),
                          Node(id="n3", type=NodeType.atomic,
                               params={"atomic_action": "screenshot"},
                               next="n2"),
                          Node(id="n4", type=NodeType.end),
                      ])
        WorkflowSchema.validate(wf)  # 不应抛出

    def test_branch_ref_not_exists(self):
        """分支 next 指向不存在的节点。"""
        wf = Workflow(id="wf_branch001", name="分支指向不存在",
                      nodes=[
                          Node(id="n1", type=NodeType.start, next="n2"),
                          Node(id="n2", type=NodeType.condition,
                               params={"expression": "true"},
                               branches=[
                                   {"condition": "true", "next": "n3"},
                                   {"condition": "false", "next": "n99"},
                               ]),
                          Node(id="n3", type=NodeType.end),
                      ])
        with pytest.raises(WorkflowValidationError, match="n99"):
            WorkflowSchema.validate(wf)

    def test_too_few_nodes(self):
        """节点数不足 2。"""
        wf = Workflow(id="wf_short001", name="太短",
                      nodes=[Node(id="n1", type=NodeType.start)])
        with pytest.raises(WorkflowValidationError, match="至少"):
            WorkflowSchema.validate(wf)


# ======================================================================
# 变量模板解析
# ======================================================================

class TestVariableParsing:
    def test_parse_simple(self):
        refs = parse_variable_ref("{{variables.count}}")
        assert refs == ["count"]

    def test_parse_multiple(self):
        refs = parse_variable_ref(
            "{{variables.name}} == {{variables.age}}"
        )
        assert refs == ["name", "age"]

    def test_parse_none(self):
        refs = parse_variable_ref("no variables here")
        assert refs == []

    def test_parse_empty(self):
        refs = parse_variable_ref("")
        assert refs == []

    def test_parse_in_params(self):
        text = json.dumps({
            "expression": "{{variables.has_new_email}} == true",
            "app": "{{variables.app_name}}",
        })
        refs = parse_variable_ref(text)
        assert "has_new_email" in refs
        assert "app_name" in refs


# ======================================================================
# 枚举与数据类
# ======================================================================

class TestEnumsAndDataclasses:
    def test_node_type_values(self):
        assert [e.value for e in NodeType] == [
            "atomic", "condition", "loop", "wait", "start", "end",
        ]

    def test_error_strategy_defaults(self):
        es = ErrorStrategy()
        assert es.type == ErrorStrategyType.abort_type
        assert es.max_retries == 3

    def test_variable_defaults(self):
        v = Variable()
        assert v.type == VariableType.str_type
        assert v.scope == VariableScopeType.global_type
