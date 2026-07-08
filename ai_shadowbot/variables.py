"""变量系统（F006 §4）—— 工作流执行期间的数据流容器。

设计要点（§4.1）：
  - global 变量在工作流生命周期内存在，local 变量节点内临时
  - 变量值 JSON 可序列化（str, int, bool, list, dict）
  - 变量名规则：^[a-zA-Z_][a-zA-Z0-9_]*$
  - 声明时 type 检查，set 时验证类型匹配
  - 未声明变量引用 → 空值默认（不崩溃）
  - 内建变量：workflow.id, workflow.step, last_result, last_screenshot
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ai_shadowbot.workflow import (
    VARIABLE_PATTERN,
    Variable,
    VariableType,
    parse_variable_ref,
)

# Python 类型 ← VariableType 映射
TYPE_MAP: Dict[VariableType, type] = {
    VariableType.str_type: str,
    VariableType.int_type: int,
    VariableType.bool_type: bool,
    VariableType.list_type: list,
    VariableType.dict_type: dict,
}

# 类型默认值
DEFAULT_VALUES: Dict[VariableType, Any] = {
    VariableType.str_type: "",
    VariableType.int_type: 0,
    VariableType.bool_type: False,
    VariableType.list_type: [],
    VariableType.dict_type: {},
}


class VariableScope:
    """变量作用域 —— 支持 global 跨节点 / local 节点内临时。

    用法：
        scope = VariableScope(declarations={...})
        scope.set("count", 5)
        value = scope.get("count")
    """

    def __init__(
        self,
        declarations: Optional[Dict[str, Variable]] = None,
        workflow_id: str = "",
    ):
        self._vars: Dict[str, Any] = {}
        # 变量类型声明：name -> VariableType
        self._declarations: Dict[str, Variable] = {}
        if declarations:
            for name, var_def in declarations.items():
                self._declarations[name] = var_def
                if var_def.default is not None:
                    self._vars[name] = var_def.default
                else:
                    self._vars[name] = DEFAULT_VALUES.get(var_def.type, "")

        # 内建变量
        self._builtin: Dict[str, Any] = {
            "workflow.id": workflow_id,
            "workflow.step": 0,
            "last_result": {},
            "last_screenshot": "",
        }

    def get(self, name: str, default: Any = None) -> Any:
        """读取变量；未声明返回 default 或 None。"""
        if name in self._builtin:
            return self._builtin.get(name)
        if name in self._vars:
            return self._vars[name]
        return default

    def set(self, name: str, value: Any, type_check: bool = True) -> None:
        """设置变量值，可选类型检查。

        Raises:
            TypeError: 类型检查开启且值与声明类型不符时
        """
        if type_check and name in self._declarations:
            declared_type = self._declarations[name].type
            expected = TYPE_MAP.get(declared_type)
            if expected is not None:
                if not isinstance(value, expected):
                    # bool 是 int 的子类，特殊处理
                    if expected is int and isinstance(value, bool):
                        raise TypeError(
                            f"变量 '{name}' 声明类型 {declared_type.value}，"
                            f"但传入 bool 值"
                        )
                    if expected is bool and isinstance(value, bool):
                        pass
                    else:
                        raise TypeError(
                            f"变量 '{name}' 声明类型 {declared_type.value}，"
                            f"得到 {type(value).__name__}"
                        )
        self._vars[name] = value

    def has(self, name: str) -> bool:
        """变量是否已设置（含内建）。"""
        return name in self._vars or name in self._builtin

    def clear(self) -> None:
        """清空所有用户变量（保留内建）。"""
        self._vars.clear()

    def update_builtin(self, name: str, value: Any) -> None:
        """更新内建变量值（引擎内部使用）。"""
        if name in self._builtin:
            self._builtin[name] = value

    def snapshot(self) -> Dict[str, Any]:
        """返回所有变量副本（用于日志 / 调试）。"""
        result = dict(self._builtin)
        result.update(self._vars)
        return result

    def keys(self) -> List[str]:
        """返回所有可访问的变量名。"""
        return list(self._builtin.keys()) + list(self._vars.keys())

    def set_local(self, name: str, value: Any) -> None:
        """设置局部临时变量（不入持久声明）。"""
        self._vars[name] = value


# ---------------------------------------------------------------------------
# 模板解析器
# ---------------------------------------------------------------------------

def resolve_template(template: str, scope: VariableScope) -> str:
    """将模板字符串中的 {{variables.xxx}} 替换为实际值。

    规则（§3.4）：
        - str/int/float/bool 直接 str(value)
        - list/dict 用 json.dumps
        - 未声明变量 → {{undefined:xxx}}（不崩溃）
    """
    def _replace(m: re.Match) -> str:
        name = m.group(1)
        value = scope.get(name)
        if value is None:
            return f"{{{{undefined:{name}}}}}"
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        return json.dumps(value, ensure_ascii=False)
    return VARIABLE_PATTERN.sub(_replace, template)


def resolve_params(params: Dict[str, Any], scope: VariableScope) -> Dict[str, Any]:
    """递归解析参数字典中的所有字符串值，替换变量模板。"""
    result: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str):
            result[key] = resolve_template(value, scope)
        elif isinstance(value, dict):
            result[key] = resolve_params(value, scope)
        elif isinstance(value, list):
            result[key] = [
                resolve_template(v, scope) if isinstance(v, str)
                else resolve_params(v, scope) if isinstance(v, dict)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result
