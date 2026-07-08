"""AI 工作流编译器（F006 §2）—— 自然语言 → Workflow DAG。

设计：
  - 复用 Config.make_llm_client() / MockLLMClient
  - 注册 compile_workflow tool_choice（单一 tool，输出完整 Workflow DAG JSON）
  - Mock 模式：内置启发式匹配（关键词 → 预置模板流），不依赖真实 LLM
  - 编译时安全校验：validate_dag + atomic 节点参数过 _scan_injection 快筛
  - 异常 → CompileResult(success=False, reason=...)
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_shadowbot.config import Config
from ai_shadowbot.workflow import (
    ErrorStrategy,
    ErrorStrategyType,
    Node,
    NodeType,
    Trigger,
    TriggerType,
    Variable,
    VariableType,
    Workflow,
    WorkflowSchema,
    WorkflowValidationError,
)
from ai_shadowbot.guardrails import _scan_injection

# ---------------------------------------------------------------------------
# compile_workflow tool schema（§2.2.1）
# ---------------------------------------------------------------------------

COMPILE_WORKFLOW_TOOL = {
    "type": "function",
    "function": {
        "name": "compile_workflow",
        "description": "将自然语言需求编译为结构化工作流 DAG（节点图）",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "工作流名称",
                },
                "description": {
                    "type": "string",
                    "description": "工作流简短描述",
                },
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "atomic", "condition", "loop",
                                    "wait", "start", "end",
                                ],
                            },
                            "label": {"type": "string"},
                            "params": {"type": "object"},
                            "next": {"type": "string"},
                            "branches": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "children": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "continue_on": {"type": "string"},
                            "vision_query": {"type": "string"},
                            "output_variable": {"type": "string"},
                            "error_strategy": {"type": "object"},
                        },
                        "required": ["id", "type", "params"],
                    },
                },
                "triggers": {
                    "type": "array",
                    "items": {"type": "object"},
                },
                "variables": {
                    "type": "object",
                    "additionalProperties": {"type": "object"},
                },
                "error_strategy": {"type": "object"},
            },
            "required": ["name", "nodes"],
        },
    },
}

COMPILE_SYSTEM_PROMPT = (
    "你是一个 AI 工作流编译器。请将用户的自然语言需求编译为一个结构化工作流 DAG。\n"
    "工作流由节点组成，节点类型包括：start(开始), end(结束), atomic(原子动作: click/double_click/"
    "right_click/type_text/key_press/screenshot/wait/open_app/scroll/"
    "browser_navigate/browser_click/browser_type/browser_screenshot/browser_wait/browser_scroll/browser_extract_text), "
    "condition(条件判断, 包含 branches 分支), loop(循环), wait(等待)。\n"
    "必须包含 start 和 end 节点，节点 ID 格式 n1/n2/...，严格按顺序排列。\n"
    "atomic 节点的 params.atomic_action 必须指定具体动作类型。\n"
    "只调用 compile_workflow 工具返回 JSON，不调用任何其他函数。"
)


# ---------------------------------------------------------------------------
# 编译结果
# ---------------------------------------------------------------------------

@dataclass
class CompileResult:
    success: bool
    workflow: Optional[Workflow] = None
    reason: str = ""
    raw: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 模板流定义（Mock 编译器用）
# ---------------------------------------------------------------------------

_WORKFLOW_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "邮件": {
        "name": "邮件处理",
        "description": "打开 Outlook 检查新邮件并处理",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {"has_new_email": {"type": "bool", "default": False, "scope": "global"}},
    },
    "Excel": {
        "name": "Excel 数据处理",
        "description": "使用 Excel 处理数据",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {"data_ready": {"type": "bool", "default": False, "scope": "global"}},
    },
    "截图": {
        "name": "屏幕截图",
        "description": "对当前屏幕截图",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {},
    },
    "记事本": {
        "name": "记事本操作",
        "description": "打开记事本并输入文本",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {},
    },
    "浏览器": {
        "name": "浏览器操作",
        "description": "打开浏览器",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {},
    },
    "打印": {
        "name": "打印任务",
        "description": "打印操作",
        "triggers": [{"type": "manual", "config": {}}],
        "variables": {},
    },
}

# 默认工作流模板（无关键词匹配时）
_DEFAULT_WORKFLOW = {
    "name": "自动化工作流",
    "description": "AI 编译的自动化工作流",
    "triggers": [{"type": "manual", "config": {}}],
    "variables": {},
}


def _detect_actions_from_query(query: str) -> List[Dict[str, Any]]:
    """从自然语言查询中启发式检测动作序列。"""
    q = query.lower()
    actions: List[Dict[str, Any]] = []

    # ---- 浏览器关键词检测（F015.3） ----
    browser_detected = False
    if re.search(r"打开.*网页|浏览|访问.*网址|打开.*链接", q):
        url_match = re.search(
            r"(?:打开|浏览|访问).*?(?:网页|网址|链接)[：:]?\s*(https?://[^\s，,。]+)",
            q,
        )
        url = url_match.group(1) if url_match else "https://"
        actions.append({
            "id": "n2", "type": "atomic",
            "params": {"atomic_action": "browser_navigate", "url": url},
            "label": f"打开网页 {url}",
            "next": "n3",
        })
        browser_detected = True

    if re.search(r"点击.*按钮|点击.*链接|点击.*元素", q):
        actions.append({
            "id": "n3" if browser_detected else "n2",
            "type": "atomic",
            "params": {"atomic_action": "browser_click", "x": 0, "y": 0},
            "label": "点击元素",
            "next": "n4" if browser_detected else "n3",
        })
        browser_detected = True

    if re.search(r"输入.*搜索|在.*框.*输入|网页.*输入", q):
        tm = re.search(r"(?:输入|键入)(.+?)(?:然后|，|,|搜索|$)", q)
        text = tm.group(1).strip().strip("。.。") if tm else ""
        actions.append({
            "id": "n3" if not browser_detected else "n4",
            "type": "atomic",
            "params": {"atomic_action": "browser_type", "text": text},
            "label": f"输入 {text}",
            "next": "n4" if not browser_detected else "n5",
        })
        browser_detected = True

    if re.search(r"截.*网页|网页.*截图", q):
        actions.append({
            "id": "n3" if not browser_detected else "n4",
            "type": "atomic",
            "params": {"atomic_action": "browser_screenshot"},
            "label": "网页截图",
            "next": "n4" if not browser_detected else "n5",
        })
        browser_detected = True

    # 如果已检测到浏览器动作，不再走原有关键词匹配
    if browser_detected:
        return actions

    # 检测关键词并构建对应动作
    if re.search(r"打开.+?(?:并|，|,|然后)", q):
        m = re.search(r"打开(.+?)(?:并|，|,|然后)", q)
        if m:
            app = m.group(1).strip()
            actions.append({
                "id": "n2", "type": "atomic",
                "params": {"atomic_action": "open_app", "name": app},
                "label": f"打开 {app}",
                "next": "n3",
            })
            # 检测后续动作
            remaining = q[m.end():]
            if re.search(r"输入|键入|打字|写", remaining):
                tm = re.search(r"(?:输入|键入|打字|写)(.+?)(?:然后|，|,|$)", remaining)
                text = tm.group(1).strip().strip("。.。") if tm else "Hello"
                actions.append({
                    "id": "n3", "type": "atomic",
                    "params": {"atomic_action": "type_text", "text": text},
                    "label": f"输入 {text}",
                    "next": "n4",
                })
            elif "截图" in remaining:
                actions.append({
                    "id": "n3", "type": "atomic",
                    "params": {"atomic_action": "screenshot"},
                    "label": "截图",
                    "next": "n4",
                })
    elif "截图" in q:
        actions.append({
            "id": "n2", "type": "atomic",
            "params": {"atomic_action": "screenshot"},
            "label": "截图",
            "next": "n3",
        })
    elif "打开" in q:
        m = re.search(r"打开(.+)", q)
        app = m.group(1).strip() if m else "记事本"
        actions.append({
            "id": "n2", "type": "atomic",
            "params": {"atomic_action": "open_app", "name": app},
            "label": f"打开 {app}",
            "next": "n3",
        })
        # 检查是否有后续输入
        if re.search(r"输入|键入|打字|写", q):
            tm = re.search(r"(?:输入|键入|打字|写)(.+?)$", q)
            text = tm.group(1).strip().strip("。.。") if tm else "内容"
            actions.append({
                "id": "n3", "type": "atomic",
                "params": {"atomic_action": "type_text", "text": text},
                "label": f"输入 {text}",
                "next": "n4",
            })

    if not actions:
        # 默认单动作
        actions.append({
            "id": "n2", "type": "atomic",
            "params": {"atomic_action": "screenshot"},
            "label": "截图",
            "next": "n3",
        })

    return actions


def _build_mock_workflow(query: str) -> Workflow:
    """Mock 模式：启发式构建工作流 DAG。"""
    # 匹配模板
    matched_template = None
    for keyword, tmpl in _WORKFLOW_TEMPLATES.items():
        if keyword in query:
            matched_template = tmpl
            break
    if matched_template is None:
        matched_template = _DEFAULT_WORKFLOW

    wid = f"wf_{int(time.time()) % 10**8:08d}"
    nodes: List[Node] = [
        Node(id="n1", type=NodeType.start, label="开始", next="n2"),
    ]

    detected = _detect_actions_from_query(query)
    if detected:
        nodes.extend([Node.from_dict(d) for d in detected])
        # 找最后一个节点的 next
        last_next = None
        for act in reversed(detected):
            if "next" in act:
                last_next = act["next"]
                break
        end_id = last_next if last_next else "n3"
    else:
        end_id = "n2"

    # 确保 end_id 先存后建 end 节点
    end_id_actual = "n_end"
    # 把所有指向不存在的 next 改为 end_id_actual
    node_ids = {n.id for n in nodes}
    for n in nodes:
        if n.next and n.next not in node_ids:
            n.next = end_id_actual

    nodes.append(Node(id=end_id_actual, type=NodeType.end, label="结束"))

    # 构建变量
    variables: Dict[str, Variable] = {}
    for var_name, var_dict in matched_template.get("variables", {}).items():
        var_type_str = var_dict.get("type", "str")
        type_map = {
            "str": VariableType.str_type,
            "int": VariableType.int_type,
            "bool": VariableType.bool_type,
            "list": VariableType.list_type,
            "dict": VariableType.dict_type,
        }
        variables[var_name] = Variable(
            type=type_map.get(var_type_str, VariableType.str_type),
            default=var_dict.get("default"),
        )

    triggers = [
        Trigger.from_dict(t) for t in matched_template.get("triggers", [])
    ]

    description = f"AI 编译自：{query[:200]}"
    return Workflow(
        id=wid,
        name=matched_template["name"],
        nodes=nodes,
        description=description,
        triggers=triggers,
        variables=variables,
        error_strategy=ErrorStrategy(type=ErrorStrategyType.retry_type),
        metadata={
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "compiled_from": query,
            "total_steps": len([n for n in nodes if n.type == NodeType.atomic]),
        },
    )


# ---------------------------------------------------------------------------
# WorkflowCompiler
# ---------------------------------------------------------------------------

class WorkflowCompiler:
    """自然语言 → 工作流 DAG 编译器。

    核心 API: compile(natural_language_query, context?) → CompileResult
    """

    def __init__(
        self,
        config: Config,
        llm_client: Optional[Any] = None,
    ):
        self.config = config
        self._llm = llm_client if llm_client is not None else config.make_llm_client()

    def compile(
        self,
        natural_language_query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CompileResult:
        """编译自然语言需求为 Workflow DAG。

        Args:
            natural_language_query: 用户自然语言需求
            context: 可选上下文

        Returns:
            CompileResult: 编译结果
        """
        # Mock 模式直接走启发式
        llm_cls_name = self._llm.__class__.__name__
        if self.config.mock or "Mock" in llm_cls_name:
            return self._mock_compile(natural_language_query)

        return self._llm_compile(natural_language_query, context)

    def _mock_compile(self, query: str) -> CompileResult:
        """Mock 模式：启发式构建。"""
        try:
            workflow = _build_mock_workflow(query)
            # 编译时安全校验：DAG 校验
            try:
                WorkflowSchema.validate(workflow)
            except WorkflowValidationError as e:
                return CompileResult(False, reason=f"DAG 校验失败：{e}")

            # 安全编译时校验：atomic 节点参数快筛
            for node in workflow.nodes:
                if node.type == NodeType.atomic:
                    text = json.dumps(node.params, ensure_ascii=False)
                    if _scan_injection(text):
                        return CompileResult(
                            False,
                            reason=(
                                f"节点 '{node.id}' 参数含提示注入诱导短语，"
                                f"已拒绝编译"
                            ),
                        )

            return CompileResult(
                True,
                workflow=workflow,
                reason="Mock 编译成功（启发式模式）",
            )
        except Exception as e:
            return CompileResult(False, reason=f"编译异常：{e}")

    def _llm_compile(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CompileResult:
        """真实 LLM 编译（通过 tool_choice 获取 DAG JSON）。"""
        messages = [
            {"role": "system", "content": COMPILE_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]

        try:
            resp = self._llm.chat(
                messages,
                [COMPILE_WORKFLOW_TOOL],
            )
        except Exception as e:
            return CompileResult(False, reason=f"LLM 调用失败：{e}")

        tool_calls = resp.get("tool_calls", [])
        if not tool_calls:
            return CompileResult(False, reason="模型未返回编译结果")

        try:
            args = tool_calls[0].get("args", {})
            if not args:
                return CompileResult(False, reason="编译结果参数为空")

            # 构建 Workflow
            wid = f"wf_{int(time.time()) % 10**8:08d}"
            nodes_raw = args.get("nodes", [])
            nodes = [Node.from_dict(n) for n in nodes_raw]

            variables_raw = args.get("variables", {})
            variables: Dict[str, Variable] = {}
            if isinstance(variables_raw, dict):
                for k, v in variables_raw.items():
                    if isinstance(v, dict):
                        variables[k] = Variable.from_dict(v)

            triggers_raw = args.get("triggers", [])
            triggers = [Trigger.from_dict(t) for t in triggers_raw]

            es_raw = args.get("error_strategy")
            error_strategy = ErrorStrategy.from_dict(es_raw) if es_raw else None

            workflow = Workflow(
                id=wid,
                name=args.get("name", "未命名工作流"),
                nodes=nodes,
                description=args.get("description", ""),
                triggers=triggers,
                variables=variables,
                error_strategy=error_strategy,
                metadata={
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "compiled_from": query,
                    "total_steps": len([n for n in nodes
                                        if n.type == NodeType.atomic]),
                },
            )

            # DAG 校验
            WorkflowSchema.validate(workflow)

            # 安全校验
            for node in workflow.nodes:
                if node.type == NodeType.atomic:
                    text = json.dumps(node.params, ensure_ascii=False)
                    if _scan_injection(text):
                        return CompileResult(
                            False,
                            reason=(
                                f"节点 '{node.id}' 参数含提示注入诱导短语，"
                                f"已拒绝编译"
                            ),
                        )

            return CompileResult(
                True,
                workflow=workflow,
                reason="LLM 编译成功",
                raw={"tool_calls": tool_calls},
            )
        except WorkflowValidationError as e:
            return CompileResult(False, reason=f"DAG 校验失败：{e}")
        except Exception as e:
            return CompileResult(False, reason=f"编译结果解析异常：{e}")


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------

def save_workflow(workflow: Workflow, path: str) -> None:
    """序列化工作流为 JSON 文件。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(workflow.to_dict(), f, ensure_ascii=False, indent=2)


def load_workflow(path: str) -> Workflow:
    """从 JSON 文件加载工作流。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Workflow.from_dict(data)
