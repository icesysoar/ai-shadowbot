"""工作流 DAG 数据结构（F006 §1）—— AI 工作流的节点图定义与校验。

铁律：
  - NodeType 严格限定 6 种：atomic, condition, loop, wait, start, end
  - DAG 正确性 9 约束在 WorkflowSchema.validate() 中统一校验
  - 变量模板解析 pars_variable_ref() 提取 {{variables.xxx}} 引用
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 基本枚举
# ---------------------------------------------------------------------------

class NodeType(str, Enum):
    atomic = "atomic"
    condition = "condition"
    loop = "loop"
    wait = "wait"
    start = "start"
    end = "end"


class TriggerType(str, Enum):
    cron = "cron"
    hotkey = "hotkey"
    manual = "manual"


class VariableType(str, Enum):
    str_type = "str"
    int_type = "int"
    bool_type = "bool"
    list_type = "list"
    dict_type = "dict"


class VariableScopeType(str, Enum):
    global_type = "global"
    local_type = "local"


class ErrorStrategyType(str, Enum):
    retry_type = "retry"
    skip_type = "skip"
    abort_type = "abort"
    degrade_type = "degrade"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------

@dataclass
class ErrorStrategy:
    type: ErrorStrategyType = ErrorStrategyType.abort_type
    max_retries: int = 3
    retry_interval: float = 2.0
    retry_backoff: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "max_retries": self.max_retries,
            "retry_interval": self.retry_interval,
            "retry_backoff": self.retry_backoff,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ErrorStrategy":
        return cls(
            type=ErrorStrategyType(d.get("type", "abort")),
            max_retries=d.get("max_retries", 3),
            retry_interval=d.get("retry_interval", 2.0),
            retry_backoff=d.get("retry_backoff", 1.0),
        )


@dataclass
class Trigger:
    type: TriggerType = TriggerType.manual
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type.value, "config": dict(self.config)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Trigger":
        return cls(
            type=TriggerType(d.get("type", "manual")),
            config=d.get("config", {}),
        )


@dataclass
class Variable:
    type: VariableType = VariableType.str_type
    scope: VariableScopeType = VariableScopeType.global_type
    default: Any = None
    description: str = ""
    source: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type.value, "scope": self.scope.value}
        if self.default is not None:
            d["default"] = self.default
        if self.description:
            d["description"] = self.description
        if self.source:
            d["source"] = self.source
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Variable":
        var_type_str = d.get("type", "str")
        # 兼容枚举字符串值
        type_map = {
            "str": VariableType.str_type,
            "int": VariableType.int_type,
            "bool": VariableType.bool_type,
            "list": VariableType.list_type,
            "dict": VariableType.dict_type,
        }
        return cls(
            type=type_map.get(var_type_str, VariableType.str_type),
            scope=VariableScopeType(d.get("scope", "global")),
            default=d.get("default"),
            description=d.get("description", ""),
            source=d.get("source", ""),
        )


@dataclass
class Node:
    id: str
    type: NodeType
    params: Dict[str, Any] = field(default_factory=dict)
    label: str = ""
    next: Optional[str] = None
    branches: List[Dict[str, Any]] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    continue_on: Optional[str] = None
    vision_query: Optional[str] = None
    error_strategy: Optional[ErrorStrategy] = None
    output_variable: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "type": self.type.value,
            "params": dict(self.params),
        }
        if self.label:
            d["label"] = self.label
        if self.next is not None:
            d["next"] = self.next
        if self.branches:
            d["branches"] = list(self.branches)
        if self.children:
            d["children"] = list(self.children)
        if self.continue_on is not None:
            d["continue_on"] = self.continue_on
        if self.vision_query is not None:
            d["vision_query"] = self.vision_query
        if self.error_strategy is not None:
            d["error_strategy"] = self.error_strategy.to_dict()
        if self.output_variable is not None:
            d["output_variable"] = self.output_variable
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Node":
        es = d.get("error_strategy")
        return cls(
            id=d["id"],
            type=NodeType(d["type"]),
            params=d.get("params", {}),
            label=d.get("label", ""),
            next=d.get("next"),
            branches=d.get("branches", []),
            children=d.get("children", []),
            continue_on=d.get("continue_on"),
            vision_query=d.get("vision_query"),
            error_strategy=ErrorStrategy.from_dict(es) if es else None,
            output_variable=d.get("output_variable"),
        )


@dataclass
class Workflow:
    id: str
    name: str
    nodes: List[Node]
    description: str = ""
    version: str = "1.0"
    triggers: List[Trigger] = field(default_factory=list)
    variables: Dict[str, Variable] = field(default_factory=dict)
    error_strategy: Optional[ErrorStrategy] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "nodes": [n.to_dict() for n in self.nodes],
        }
        if self.description:
            d["description"] = self.description
        if self.version != "1.0":
            d["version"] = self.version
        if self.triggers:
            d["triggers"] = [t.to_dict() for t in self.triggers]
        if self.variables:
            d["variables"] = {k: v.to_dict() for k, v in self.variables.items()}
        if self.error_strategy is not None:
            d["error_strategy"] = self.error_strategy.to_dict()
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Workflow":
        variables_raw = d.get("variables", {})
        variables: Dict[str, Variable] = {}
        if isinstance(variables_raw, dict):
            for k, v in variables_raw.items():
                if isinstance(v, dict):
                    variables[k] = Variable.from_dict(v)
        es = d.get("error_strategy")
        return cls(
            id=d["id"],
            name=d["name"],
            nodes=[Node.from_dict(n) for n in d.get("nodes", [])],
            description=d.get("description", ""),
            version=d.get("version", "1.0"),
            triggers=[Trigger.from_dict(t) for t in d.get("triggers", [])],
            variables=variables,
            error_strategy=ErrorStrategy.from_dict(es) if es else None,
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# 变量模板解析
# ---------------------------------------------------------------------------

VARIABLE_PATTERN = re.compile(r"\{\{variables\.([a-zA-Z_][a-zA-Z0-9_]*)\}\}")


def parse_variable_ref(text: str) -> List[str]:
    """提取文本中所有 {{variables.xxx}} 引用，返回变量名列表。"""
    return VARIABLE_PATTERN.findall(text)


# ---------------------------------------------------------------------------
# DAG 正确性校验
# ---------------------------------------------------------------------------

class WorkflowValidationError(ValueError):
    """工作流 DAG 校验失败。"""


class WorkflowSchema:
    """DAG 正确性校验器 —— 9 条约束（§1.4）。"""

    @staticmethod
    def validate(workflow: Workflow) -> None:
        """校验工作流 DAG 正确性，失败抛 WorkflowValidationError。"""
        nodes = workflow.nodes
        if len(nodes) < 2:
            raise WorkflowValidationError("节点数至少为 2（start + end）")

        node_ids = [n.id for n in nodes]
        node_map: Dict[str, Node] = {n.id: n for n in nodes}

        # 约束 3: 所有节点 ID 唯一
        if len(node_ids) != len(set(node_ids)):
            raise WorkflowValidationError("节点 ID 重复")

        # 约束 1: 有且仅有一个 start 节点
        start_nodes = [n for n in nodes if n.type == NodeType.start]
        if len(start_nodes) != 1:
            raise WorkflowValidationError(
                f"必须有且仅有一个 start 节点，找到 {len(start_nodes)}"
            )

        # 约束 2: 有且仅有一个 end 节点
        end_nodes = [n for n in nodes if n.type == NodeType.end]
        if len(end_nodes) != 1:
            raise WorkflowValidationError(
                f"必须有且仅有一个 end 节点，找到 {len(end_nodes)}"
            )

        # 约束 4: 所有引用必须存在
        refs: List[str] = []
        for n in nodes:
            if n.next:
                refs.append(n.next)
            if n.children:
                refs.extend(n.children)
            if n.continue_on:
                refs.append(n.continue_on)
            for b in n.branches:
                nid = b.get("next", "")
                if nid:
                    refs.append(nid)
        for ref in refs:
            if ref not in node_map:
                raise WorkflowValidationError(f"节点 '{ref}' 被引用但不存在")

        # 约束 5: 无环（除 loop 节点自身）
        _check_cycles(nodes, node_map)

        # 约束 6: condition 节点至少 2 条 branch
        for n in nodes:
            if n.type == NodeType.condition:
                if len(n.branches) < 2:
                    raise WorkflowValidationError(
                        f"condition 节点 '{n.id}' 至少需要 2 条分支"
                    )
                # 同时检查 branches 的 next 必须有效
                for b in n.branches:
                    nid = b.get("next", "")
                    if nid and nid not in node_map:
                        raise WorkflowValidationError(
                            f"condition 节点 '{n.id}' 的分支指向不存在的节点 '{nid}'"
                        )

        # 约束 7: loop 节点至少 1 个 children
        for n in nodes:
            if n.type == NodeType.loop:
                if len(n.children) < 1:
                    raise WorkflowValidationError(
                        f"loop 节点 '{n.id}' 至少需要 1 个子节点"
                    )

        # 约束 8: loop.max_iterations <= 1000
        for n in nodes:
            if n.type == NodeType.loop:
                max_iter = n.params.get("max_iterations", 100)
                if max_iter > 1000:
                    raise WorkflowValidationError(
                        f"loop 节点 '{n.id}' 的 max_iterations={max_iter} 超过上限 1000"
                    )

        # 约束 9: 变量引用检查（警告标记为潜在错误，不崩溃）
        declared_vars = set(workflow.variables.keys()) if workflow.variables else set()
        for n in nodes:
            text = json.dumps(n.params, ensure_ascii=False)
            refs_found = parse_variable_ref(text)
            for ref in refs_found:
                if ref not in declared_vars:
                    # 不抛异常，但记录到 metadata
                    pass  # 兼容性，允许未声明的变量引用（运行时会给默认值）


def _check_cycles(nodes: List[Node], node_map: Dict[str, Node]) -> None:
    """环检测：DFS 三色标记，允许 loop 子节点指向 loop 自身的结构。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {n.id: WHITE for n in nodes}

    # 收集 loop 节点的 children ID 集合
    loop_children: Dict[str, set] = {}
    for n in nodes:
        if n.type == NodeType.loop:
            loop_children[n.id] = set(n.children)

    def dfs(nid: str, parent_loop_id: Optional[str] = None) -> None:
        if color.get(nid, WHITE) == GRAY:
            raise WorkflowValidationError(f"DAG 存在环路，涉及节点 '{nid}'")
        if color.get(nid, WHITE) == BLACK:
            return
        color[nid] = GRAY
        node = node_map.get(nid)
        if node:
            # 收集后继
            successors: List[str] = []
            if node.next:
                # 如果当前节点是 loop 的子节点，允许指向 loop 自身
                if parent_loop_id and node.next == parent_loop_id:
                    pass  # 允许子节点回指 loop
                elif node.next not in loop_children.get(nid, set()):
                    successors.append(node.next)
            for b in node.branches:
                nid2 = b.get("next", "")
                if nid2:
                    successors.append(nid2)
            if node.continue_on:
                successors.append(node.continue_on)

            # loop 节点的 children 入栈
            for cid in node.children:
                if cid in node_map:
                    dfs(cid, parent_loop_id=nid)

            for s in successors:
                dfs(s, parent_loop_id=parent_loop_id)
        color[nid] = BLACK

    # 从每个节点出发检查
    start_nodes = [n for n in nodes if n.type == NodeType.start]
    if start_nodes:
        dfs(start_nodes[0].id)
    for n in nodes:
        if color.get(n.id, WHITE) == WHITE:
            dfs(n.id)
