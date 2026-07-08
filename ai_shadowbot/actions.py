"""动作原语 Schema —— AI 影刀的"原子动作词汇表"。

本模块是 planner（F001）、guardrails（F003）、executor（F002）三层的**唯一事实来源**。
所有动作类型、参数、危险标记在此集中定义，避免 schema 漂移。

迁移自知识库概念：
  - 「原子动作词汇表」：复杂操作拆为不可再分的原子单元，是组合基础。
  - 「LLM 动作黑名单安全校验」：动作类型本身是白名单，参数级危险由 guardrails 兜底。

动作类型（与主理人裁决一致）：
  click{x,y} / double_click{x,y} / right_click{x,y}
  type_text{text}
  key_press{key}            # 如 'enter'、'ctrl+c'
  screenshot{}             # 返回 base64 供 LLM 看
  wait{seconds}
  open_app{name}
  scroll{dx,dy}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 动作类型定义表（原子动作词汇表）
# ---------------------------------------------------------------------------
# dangerous=True 表示「高危动作」，guardrails 必须二次人工确认后才放行。
ACTION_TYPES: List[Dict[str, Any]] = [
    {"type": "click", "params": {"x": int, "y": int}, "required": ["x", "y"], "dangerous": False,
     "desc": "在屏幕绝对坐标 (x,y) 左键单击"},
    {"type": "double_click", "params": {"x": int, "y": int}, "required": ["x", "y"], "dangerous": False,
     "desc": "在屏幕绝对坐标 (x,y) 左键双击"},
    {"type": "right_click", "params": {"x": int, "y": int}, "required": ["x", "y"], "dangerous": False,
     "desc": "在屏幕绝对坐标 (x,y) 右键单击"},
    {"type": "type_text", "params": {"text": str}, "required": ["text"], "dangerous": False,
     "desc": "在当前焦点处输入文本"},
    {"type": "key_press", "params": {"key": str}, "required": ["key"], "dangerous": False,
     "desc": "按下键盘按键或组合键，如 'enter' 或 'ctrl+c'"},
    {"type": "screenshot", "params": {}, "required": [], "dangerous": False,
     "desc": "对当前屏幕截图，返回 base64 PNG（供 LLM 视觉观测）"},
    {"type": "wait", "params": {"seconds": (int, float)}, "required": ["seconds"], "dangerous": False,
     "desc": "等待指定秒数"},
    {"type": "open_app", "params": {"name": str}, "required": ["name"], "dangerous": False,
     "desc": "打开指定名称的应用程序"},
    {"type": "scroll", "params": {"dx": int, "dy": int}, "required": ["dx", "dy"], "dangerous": False,
     "desc": "滚动鼠标滚轮，dy 为正向下滚、为负向上滚，dx 为横向"},
    # ---- Excel/CSV (F016) ----
    {"type": "excel_read", "params": {"path": str, "sheet": str, "delimiter": str, "has_header": bool}, "required": ["path"], "dangerous": False,
     "desc": "读取 Excel/CSV 文件内容"},
    {"type": "excel_write", "params": {"path": str, "headers": list, "rows": list, "sheet": str}, "required": ["path", "headers", "rows"], "dangerous": False,
     "desc": "写入数据到 Excel/CSV 文件"},
    # ---- HTTP (F017) ----
    {"type": "http_request", "params": {"method": str, "url": str, "headers": dict, "body": str, "timeout": int}, "required": ["method", "url"], "dangerous": False,
     "desc": "发送 HTTP 请求"},
    {"type": "http_get", "params": {"url": str, "headers": dict}, "required": ["url"], "dangerous": False,
     "desc": "发送 HTTP GET 请求"},
    {"type": "http_post", "params": {"url": str, "body": str, "headers": dict}, "required": ["url"], "dangerous": False,
     "desc": "发送 HTTP POST 请求"},
    {"type": "http_put", "params": {"url": str, "body": str, "headers": dict}, "required": ["url"], "dangerous": False,
     "desc": "发送 HTTP PUT 请求"},
    {"type": "http_delete", "params": {"url": str, "headers": dict}, "required": ["url"], "dangerous": False,
     "desc": "发送 HTTP DELETE 请求"},
    # ---- 文件系统 (F019) ----
    {"type": "fs_read", "params": {"path": str, "encoding": str}, "required": ["path"], "dangerous": False,
     "desc": "读取文件内容"},
    {"type": "fs_write", "params": {"path": str, "content": str, "encoding": str}, "required": ["path", "content"], "dangerous": False,
     "desc": "写入内容到文件"},
    {"type": "fs_append", "params": {"path": str, "content": str}, "required": ["path", "content"], "dangerous": False,
     "desc": "追加内容到文件末尾"},
    {"type": "fs_copy", "params": {"src": str, "dst": str}, "required": ["src", "dst"], "dangerous": False,
     "desc": "复制文件"},
    {"type": "fs_move", "params": {"src": str, "dst": str}, "required": ["src", "dst"], "dangerous": False,
     "desc": "移动/重命名文件"},
    {"type": "fs_delete", "params": {"path": str}, "required": ["path"], "dangerous": True,
     "desc": "删除文件（高危：不可逆）"},
    {"type": "fs_list", "params": {"path": str}, "required": ["path"], "dangerous": False,
     "desc": "列出目录中的文件"},
    {"type": "fs_mkdir", "params": {"path": str}, "required": ["path"], "dangerous": False,
     "desc": "创建目录"},
    {"type": "fs_exists", "params": {"path": str}, "required": ["path"], "dangerous": False,
     "desc": "检查文件/目录是否存在"},
    {"type": "fs_info", "params": {"path": str}, "required": ["path"], "dangerous": False,
     "desc": "获取文件/目录详细信息（大小、修改时间、类型）"},
]

# 类型名 -> 定义 的索引
_ACTION_INDEX: Dict[str, Dict[str, Any]] = {a["type"]: a for a in ACTION_TYPES}

# 允许的动作类型白名单（guardrails 直接复用）
ALLOWED_ACTION_TYPES = frozenset(_ACTION_INDEX.keys())


@dataclass
class Action:
    """一个结构化动作实例。"""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)
    # 可选：来源快照（用于 dry_run 回显 / 重放）
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "params": self.params}


class ActionValidationError(ValueError):
    """动作不合法（类型不在白名单 / 缺参数 / 类型不匹配）。"""


def _coerce(value: Any, expected: Any) -> Any:
    """把 JSON 解析出的原始值向期望类型对齐。"""
    if expected is int:
        if isinstance(value, bool):
            raise ActionValidationError("布尔值不能当作 int")
        if isinstance(value, (int, float)):
            return int(value)
        raise ActionValidationError(f"期望 int，得到 {type(value).__name__}")
    if expected is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        raise ActionValidationError(f"期望 float，得到 {type(value).__name__}")
    if expected is str:
        if isinstance(value, str):
            return value
        raise ActionValidationError(f"期望 str，得到 {type(value).__name__}")
    if expected is bool:
        if isinstance(value, bool):
            return value
        raise ActionValidationError(f"期望 bool，得到 {type(value).__name__}")
    if expected is list:
        if isinstance(value, list):
            return value
        # 容错：str 变单元素列表
        if isinstance(value, str):
            return [value]
        raise ActionValidationError(f"期望 list，得到 {type(value).__name__}")
    if expected is dict:
        if isinstance(value, dict):
            return value
        raise ActionValidationError(f"期望 dict，得到 {type(value).__name__}")
    # 允许多类型（如 seconds: (int, float)）
    if isinstance(expected, tuple):
        for t in expected:
            try:
                return _coerce(value, t)
            except ActionValidationError:
                continue
        raise ActionValidationError(f"期望 {expected}，得到 {type(value).__name__}")
    return value


def validate_action(action: Dict[str, Any]) -> Action:
    """校验并归一化一个原始动作 dict，返回 Action 实例。

    这就是「动作 Schema 强校验」，对应共识报告风险项
    「模型幻觉产生非法动作序列 —— 动作 schema 强校验 + 执行前 dry-run 检查」。
    """
    if not isinstance(action, dict):
        raise ActionValidationError(f"动作必须是 dict，得到 {type(action).__name__}")
    atype = action.get("type")
    if not isinstance(atype, str):
        raise ActionValidationError("动作缺少字符串 type 字段")
    if atype not in ALLOWED_ACTION_TYPES:
        raise ActionValidationError(
            f"未知动作类型 '{atype}'，不在白名单 {sorted(ALLOWED_ACTION_TYPES)}"
        )
    spec = _ACTION_INDEX[atype]
    raw_params = action.get("params") or {}
    if not isinstance(raw_params, dict):
        raise ActionValidationError("params 必须是 dict")

    out: Dict[str, Any] = {}
    for req in spec["required"]:
        if req not in raw_params:
            raise ActionValidationError(f"动作 '{atype}' 缺少必填参数 '{req}'")
    for pname, pval in raw_params.items():
        if pname not in spec["params"]:
            raise ActionValidationError(f"动作 '{atype}' 存在未定义参数 '{pname}'")
        out[pname] = _coerce(pval, spec["params"][pname])
    return Action(type=atype, params=out, raw=action)


def is_dangerous_type(atype: str) -> bool:
    """该动作类型本身是否标记为高危。"""
    spec = _ACTION_INDEX.get(atype)
    return bool(spec and spec.get("dangerous"))


# ---------------------------------------------------------------------------
# 生成 LLM function-calling 用的 tools schema
# ---------------------------------------------------------------------------
def _json_type(py_type: Any) -> str:
    if py_type is int:
        return "integer"
    if py_type is float:
        return "number"
    if py_type is str:
        return "string"
    if py_type is bool:
        return "boolean"
    if py_type is list:
        return "array"
    if py_type is dict:
        return "object"
    if isinstance(py_type, tuple):
        # 多类型取第一个作为主类型（int/float 场景）
        return _json_type(py_type[0])
    return "string"


def build_tool_schema() -> List[Dict[str, Any]]:
    """把 ACTION_TYPES 编译成 OpenAI function-calling 的 tools 列表。

    每个动作一个 function，planner 调用 LLM 时一次性注册全部原子动作。
    """
    tools = []
    for a in ACTION_TYPES:
        props = {}
        for pname, ptype in a["params"].items():
            props[pname] = {
                "type": _json_type(ptype),
                "description": f"{a['type']} 的 {pname} 参数",
            }
        tools.append({
            "type": "function",
            "function": {
                "name": a["type"],
                "description": a["desc"],
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": list(a["required"]),
                },
            },
        })
    return tools


def normalize_plan(raw_actions: List[Dict[str, Any]]) -> List[Action]:
    """把 LLM 返回的原始动作列表归一化为 Action 列表，任一非法即抛错。"""
    return [validate_action(a) for a in raw_actions]
