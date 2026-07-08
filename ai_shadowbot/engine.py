"""执行引擎（F006 §3）—— 解释执行 DAG 节点图。

设计要点（§3.1-3.6）：
  - 核心 API：execute(workflow) / dry_run(workflow) → ExecutionResult
  - 状态机：PENDING → RUNNING → (SUCCESS|FAILED|SKIPPED|ABORTED|DEGRADED)
  - 迭代式栈遍历 DAG（防递归爆栈），不递归
  - 每个 atomic 节点执行前过 guardrails.check()（§6 硬要求）
  - Lazy import pyautogui（仅 executor._dispatch_real 内）
  - Guardrails 实例不可为 None（§6.2 铁律 5）
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ai_shadowbot.workflow import (
    ErrorStrategy,
    ErrorStrategyType,
    Node,
    NodeType,
    Workflow,
    WorkflowSchema,
    WorkflowValidationError,
)
from ai_shadowbot.actions import Action
from ai_shadowbot.executor import ExecResult, Executor
from ai_shadowbot.guardrails import ALLOW, BLOCK, CONFIRM, Guardrails, EmergencyStop
from ai_shadowbot.variables import VariableScope, resolve_params, resolve_template
from ai_shadowbot.errors import ErrorHandler, ErrorAction, HandleResult


# ---------------------------------------------------------------------------
# 节点执行结果
# ---------------------------------------------------------------------------

@dataclass
class NodeExecResult:
    node_id: str
    node_type: str
    status: str  # PENDING|RUNNING|SUCCESS|FAILED|SKIPPED|ABORTED|DEGRADED
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    action_result: Optional[ExecResult] = None
    variables_snapshot: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# 执行结果
# ---------------------------------------------------------------------------

@dataclass
class ExecutionResult:
    success: bool
    node_logs: List[NodeExecResult]
    final_state: str  # SUCCESS|FAILED|ABORTED|DEGRADED
    final_variables: Dict[str, Any]
    started_at: float
    finished_at: float
    total_duration: float


# ---------------------------------------------------------------------------
# 条件表达式解析
# ---------------------------------------------------------------------------

# 比较运算符
_COMP_OPS = [
    ("==", lambda a, b: a == b),
    ("!=", lambda a, b: a != b),
    (">=", lambda a, b: a >= b),
    ("<=", lambda a, b: a <= b),
    (">", lambda a, b: a > b),
    ("<", lambda a, b: a < b),
]


def _eval_expression(expression: str, scope: VariableScope) -> bool:
    """评估条件表达式，支持 == > < >= <= != 比较和 and/or/not 逻辑。

    例如：
        '{{variables.count}} > 5'
        '{{variables.status}} == "success"'
        'count > 5 and status == "success"'
    """
    # 替换变量引用
    resolved = resolve_template(expression, scope)

    # 处理 not X / X and Y / X or Y
    # 简化处理：按 and/or/not 分割
    expr = resolved.strip()

    # 检查 not 前缀
    if expr.startswith("not "):
        inner = _eval_simple(expr[4:].strip())
        return not inner

    # 检查 and/or
    if " and " in expr:
        parts = expr.split(" and ")
        return all(_eval_simple(p.strip()) for p in parts)
    if " or " in expr:
        parts = expr.split(" or ")
        return any(_eval_simple(p.strip()) for p in parts)

    return _eval_simple(expr)


def _eval_simple(expr: str) -> bool:
    """评估单一条件（无逻辑运算符）。"""
    expr = expr.strip()

    # 布尔字面量
    if expr == "true" or expr == "True":
        return True
    if expr == "false" or expr == "False":
        return False

    # 未定义变量标记
    if expr.startswith("{{undefined:"):
        return False

    # 比较运算
    for op_str, op_fn in _COMP_OPS:
        if op_str in expr:
            parts = expr.split(op_str, 1)
            if len(parts) == 2:
                left = _parse_value(parts[0].strip())
                right = _parse_value(parts[1].strip())
                try:
                    return op_fn(left, right)
                except (TypeError, ValueError):
                    return False

    # 单独的值（truthy 检查）
    val = _parse_value(expr)
    return bool(val)


def _parse_value(s: str) -> Any:
    """解析字面量值：数字、布尔、字符串、None。"""
    s = s.strip()
    if not s:
        return None
    # 布尔
    if s.lower() == "true":
        return True
    if s.lower() == "false":
        return False
    if s.lower() == "none" or s.lower() == "null":
        return None
    # 数字
    try:
        if "." in s:
            return float(s)
        return int(s)
    except ValueError:
        pass
    # 字符串（去引号）
    if (s.startswith('"') and s.endswith('"')) or \
       (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# 执行引擎
# ---------------------------------------------------------------------------

class Engine:
    """工作流执行引擎 —— 解释执行 DAG 节点图。

    Executor 和 Guardrails 不可为 None（§6.2 铁律 5）。
    """

    def __init__(
        self,
        executor: Executor,
        guardrails: Guardrails,
        dry_run: bool = True,
        emergency_stop: Optional[EmergencyStop] = None,
        browser_worker: Optional[Any] = None,
    ):
        if guardrails is None:
            raise ValueError("引擎必须接收 Guardrails 实例（不可为 None，§6.2 铁律 5）")
        self.executor = executor
        self.guardrails = guardrails
        self._dry_run = dry_run
        self.emergency_stop = emergency_stop
        self._browser_worker = browser_worker
        self._error_handler = ErrorHandler()
        self._node_map: Dict[str, Node] = {}
        self._workflow: Optional[Workflow] = None

    def execute(self, workflow: Workflow) -> ExecutionResult:
        """执行完整工作流（真实模式）。"""
        return self._run(workflow, dry_run=False)

    def dry_run(self, workflow: Workflow) -> ExecutionResult:
        """dry_run 模式执行工作流（安全演练）。"""
        return self._run(workflow, dry_run=True)

    # ------------------------------------------------------------------
    # 内部执行框架
    # ------------------------------------------------------------------

    def _run(self, workflow: Workflow, dry_run: bool) -> ExecutionResult:
        """统一的执行入口（dry_run / execute 共享同一套状态机代码）。"""
        started_at = time.time()
        self._workflow = workflow
        self._node_map = {n.id: n for n in workflow.nodes}
        self._error_handler.reset_all()

        # 1. DAG 校验
        try:
            WorkflowSchema.validate(workflow)
        except WorkflowValidationError as e:
            return ExecutionResult(
                success=False,
                node_logs=[],
                final_state="FAILED",
                final_variables={},
                started_at=started_at,
                finished_at=time.time(),
                total_duration=0.0,
            )

        # 2. 初始化变量系统
        declarations = workflow.variables or {}
        scope = VariableScope(
            declarations=declarations,
            workflow_id=workflow.id,
        )

        # 3. 查找 start 节点
        start_nodes = [n for n in workflow.nodes if n.type == NodeType.start]
        if not start_nodes:
            return ExecutionResult(
                success=False, node_logs=[], final_state="FAILED",
                final_variables={}, started_at=started_at,
                finished_at=time.time(), total_duration=0.0,
            )
        start_node = start_nodes[0]

        # 4. 遍历 DAG
        logs = self._traverse(start_node.id, dry_run, scope)

        finished_at = time.time()
        total_duration = finished_at - started_at

        # 确定最终状态
        final_state = self._determine_final_state(logs)

        return ExecutionResult(
            success=final_state == "SUCCESS",
            node_logs=logs,
            final_state=final_state,
            final_variables=scope.snapshot(),
            started_at=started_at,
            finished_at=finished_at,
            total_duration=total_duration,
        )

    # ------------------------------------------------------------------
    # DAG 遍历（迭代式栈，非递归）
    # ------------------------------------------------------------------

    def _traverse(
        self,
        start_node_id: str,
        dry_run: bool,
        scope: VariableScope,
    ) -> List[NodeExecResult]:
        """迭代式栈遍历 DAG（§3.5），防递归爆栈。"""
        stack: List[Tuple[str, int]] = [(start_node_id, 0)]
        visited: set = set()
        logs: List[NodeExecResult] = []
        abort_flag = False

        while stack:
            if self._check_emergency_stop():
                # 紧急停止
                current_id = stack[-1][0]
                logs.append(NodeExecResult(
                    node_id=current_id,
                    node_type="unknown",
                    status="ABORTED",
                    error="紧急停止",
                ))
                break

            node_id, depth = stack.pop()

            if node_id in visited:
                continue  # 防环路（兜底）
            visited.add(node_id)

            node = self._node_map.get(node_id)
            if node is None:
                logs.append(NodeExecResult(
                    node_id=node_id,
                    node_type="unknown",
                    status="FAILED",
                    error=f"节点 '{node_id}' 不存在",
                ))
                break

            # 更新工作流 step
            scope.update_builtin("workflow.step", len(logs) + 1)

            # 执行节点
            result = self._execute_node(node, dry_run, scope)
            logs.append(result)

            # 中止传播
            if result.status in ("FAILED", "ABORTED"):
                abort_flag = True
                break

            # 解析后继节点
            next_ids = self._resolve_next(node, result, scope)

            # 逆序入栈保持顺序（迭代式栈的正确入栈顺序）
            for nid in reversed(next_ids):
                # 环路检测：如果已经在 visited 中，不再入栈
                if nid not in visited:
                    # 重新加入栈
                    stack.append((nid, depth + 1))

        return logs

    def _resolve_next(
        self,
        node: Node,
        result: NodeExecResult,
        scope: VariableScope,
    ) -> List[str]:
        """解析节点的后继节点 ID。"""
        if result.status in ("FAILED", "ABORTED", "SKIPPED"):
            # 被跳过的节点看看有没有 next
            if node.next and result.status == "SKIPPED":
                return [node.next]
            return []

        if node.type == NodeType.condition:
            return self._resolve_condition_branch(node, scope)
        elif node.type == NodeType.loop:
            # loop 节点的后继由 continue_on 决定（循环结束后）
            if node.continue_on:
                return [node.continue_on]
            # 如果没有 continue_on，回环到自身（继续循环）
            return [node.id]
        elif node.type == NodeType.end:
            return []
        else:
            # atomic, wait, start：取 next
            if node.next:
                return [node.next]
            return []

    def _resolve_condition_branch(
        self,
        node: Node,
        scope: VariableScope,
    ) -> List[str]:
        """解析 condition 节点的分支选择。"""
        expression = node.params.get("expression", "")
        if not expression:
            # 无表达式时走第一个分支
            if node.branches:
                nid = node.branches[0].get("next", "")
                return [nid] if nid else []
            return []

        try:
            result = _eval_expression(expression, scope)
        except Exception:
            result = False

        # 匹配分支：真则匹配 true/yes 分支，假则匹配 false/no/else 分支
        for branch in node.branches:
            cond = branch.get("condition", "").lower()
            branch_result = _eval_expression(
                branch.get("condition", ""), scope
            ) if branch.get("condition") else False

            # 简化分支匹配：condition 为空或为 true/yes 当条件为真时走
            if not branch.get("condition"):
                # 默认分支（else）
                nid = branch.get("next", "")
                return [nid] if nid else []

        # 精确匹配：condition 是表达式本身
        best_next = None
        for branch in node.branches:
            bc = branch.get("condition", "").strip()
            if bc in ("true", "yes", "是"):
                if result:
                    best_next = branch.get("next", "")
            elif bc in ("false", "no", "否", "else"):
                if not result:
                    best_next = branch.get("next", "")

        if best_next:
            return [best_next]

        # 回退：走第一个分支
        if node.branches:
            nid = node.branches[0].get("next", "")
            return [nid] if nid else []
        return []

    # ------------------------------------------------------------------
    # 节点执行
    # ------------------------------------------------------------------

    def _execute_node(
        self,
        node: Node,
        dry_run: bool,
        scope: VariableScope,
    ) -> NodeExecResult:
        """执行单个节点，返回执行结果。"""
        started_at = time.time()

        if node.type == NodeType.start:
            result = NodeExecResult(
                node_id=node.id, node_type="start", status="SUCCESS",
                started_at=started_at, finished_at=time.time(),
                variables_snapshot=scope.snapshot(),
            )
            return result

        elif node.type == NodeType.end:
            result = NodeExecResult(
                node_id=node.id, node_type="end", status="SUCCESS",
                started_at=started_at, finished_at=time.time(),
                variables_snapshot=scope.snapshot(),
            )
            return result

        elif node.type == NodeType.atomic:
            return self._execute_atomic(node, dry_run, scope, started_at)

        elif node.type == NodeType.wait:
            return self._execute_wait(node, dry_run, scope, started_at)

        elif node.type == NodeType.condition:
            return self._execute_condition(node, scope, started_at)

        elif node.type == NodeType.loop:
            return self._execute_loop(node, dry_run, scope, started_at)

        else:
            return NodeExecResult(
                node_id=node.id, node_type=str(node.type.value),
                status="FAILED",
                error=f"未知节点类型：{node.type}",
                started_at=started_at, finished_at=time.time(),
            )

    def _execute_atomic(
        self,
        node: Node,
        dry_run: bool,
        scope: VariableScope,
        started_at: float,
    ) -> NodeExecResult:
        """执行 atomic 节点（§3.3 + §6 安全检查）。"""
        # 1. 解析变量引用
        resolved_params = resolve_params(node.params, scope)

        # 2. 构建 Action
        action_type = resolved_params.get("atomic_action", "")
        if not action_type:
            return NodeExecResult(
                node_id=node.id, node_type="atomic",
                status="FAILED",
                error="atomic 节点缺少 atomic_action 参数",
                started_at=started_at, finished_at=time.time(),
            )

        action_params = {
            k: v for k, v in resolved_params.items()
            if k != "atomic_action"
        }
        action = Action(type=action_type, params=action_params)

        # 3. 过 guardrails.check()（§6 硬要求：每个 atomic 节点必须检查）
        guard_result = self.guardrails.check(action)
        if guard_result.decision == BLOCK:
            return NodeExecResult(
                node_id=node.id, node_type="atomic",
                status="FAILED",
                error=f"护栏拦截：{guard_result.reason}",
                started_at=started_at, finished_at=time.time(),
            )
        if guard_result.decision == CONFIRM:
            # deny-unconfirmed 不削弱：CONFIRM 动作仍需用户确认
            if not self.executor.auto_confirm:
                return NodeExecResult(
                    node_id=node.id, node_type="atomic",
                    status="FAILED",
                    error=f"危险动作需确认：{guard_result.reason}",
                    started_at=started_at, finished_at=time.time(),
                )

        # 4. 浏览器动作走 browser_worker（F015.3 引擎集成）
        if action_type.startswith("browser_"):
            exec_result = self._execute_browser_action(
                action_type, resolved_params, dry_run,
            )
        else:
            # 委托 Executor 执行
            try:
                exec_result = self.executor.execute(action, dry_run=dry_run)
            except Exception as e:
                return self._handle_node_error(
                    node, scope, str(e), started_at
                )

        # 5. 处理输出变量
        if node.output_variable and exec_result.performed:
            try:
                scope.set(node.output_variable, {
                    "success": exec_result.performed,
                    "summary": exec_result.summary,
                    "error": exec_result.error,
                })
            except TypeError:
                pass

        # 6. 处理执行错误
        if exec_result.error:
            return self._handle_node_error(
                node, scope, exec_result.error, started_at,
                action_result=exec_result,
            )

        # dry_run 模式下 performed=False 是预期行为，不算失败
        is_error = exec_result.error is not None or exec_result.reason in ("执行出错",)
        status = "SUCCESS" if not is_error else "FAILED"
        return NodeExecResult(
            node_id=node.id, node_type="atomic",
            status=status,
            started_at=started_at, finished_at=time.time(),
            action_result=exec_result,
            variables_snapshot=scope.snapshot(),
        )

    def _execute_browser_action(
        self,
        action_type: str,
        resolved_params: dict,
        dry_run: bool,
    ) -> Any:
        """执行浏览器动作（F015.3）—— lazy import browser_worker。

        Args:
            action_type: 以 browser_ 开头的动作类型
            resolved_params: 解析后的参数字典
            dry_run: 是否为演练模式

        Returns:
            ExecResult 兼容对象
        """
        from ai_shadowbot.executor import ExecResult

        # dry_run 模式下不连 bridge，返回描述性结果
        if dry_run:
            return ExecResult(
                action=Action(type=action_type, params=resolved_params),
                performed=False,
                blocked=False,
                reason="dry_run 模式未真实执行浏览器动作",
                summary=f"[dry_run] 将执行浏览器动作 {action_type}",
            )

        # 真实模式：lazy import browser_worker 并执行
        try:
            from ai_shadowbot.browser_worker import BrowserWorker
        except ImportError as e:
            return ExecResult(
                action=Action(type=action_type, params=resolved_params),
                performed=False,
                blocked=True,
                reason=f"browser_worker 不可用：{e}",
                error=str(e),
                summary=f"[错误] browser_worker 导入失败 —— {e}",
            )

        # 使用 engine 已构造的 browser_worker 或临时创建
        bw = self._browser_worker
        if bw is None:
            bw = BrowserWorker(auto_start=False)

        # 动作映射
        _MAP = {
            "browser_navigate": lambda: bw.navigate(
                resolved_params.get("url", "https://example.com")
            ),
            "browser_click": lambda: bw.click(
                x=int(resolved_params.get("x", 0)),
                y=int(resolved_params.get("y", 0)),
            ),
            "browser_type": lambda: bw.type_text(
                text=str(resolved_params.get("text", "")),
            ),
            "browser_screenshot": lambda: bw.screenshot(),
            "browser_wait": lambda: bw.wait(
                seconds=float(resolved_params.get("seconds", 1)),
            ),
            "browser_scroll": lambda: bw.scroll(
                dx=int(resolved_params.get("dx", 0)),
                dy=int(resolved_params.get("dy", 0)),
            ),
            "browser_extract_text": lambda: bw.extract_text(
                selector=str(resolved_params.get("selector", "")),
            ),
        }

        handler = _MAP.get(action_type)
        if handler is None:
            return ExecResult(
                action=Action(type=action_type, params=resolved_params),
                performed=False,
                blocked=True,
                reason=f"未知浏览器动作：{action_type}",
                summary=f"[错误] 未知浏览器动作 {action_type}",
            )

        try:
            result = handler()
            if result.get("success"):
                return ExecResult(
                    action=Action(type=action_type, params=resolved_params),
                    performed=True,
                    blocked=False,
                    summary=f"[执行] 浏览器动作 {action_type} 完成",
                )
            else:
                return ExecResult(
                    action=Action(type=action_type, params=resolved_params),
                    performed=False,
                    blocked=False,
                    reason=f"浏览器动作执行失败",
                    error=result.get("error", "未知错误"),
                    summary=f"[错误] {action_type} —— {result.get('error', '未知错误')}",
                )
        except Exception as e:
            return ExecResult(
                action=Action(type=action_type, params=resolved_params),
                performed=False,
                blocked=False,
                reason=f"执行出错：{e}",
                error=str(e),
                summary=f"[错误] {action_type} —— {e}",
            )

    def _execute_wait(
        self,
        node: Node,
        dry_run: bool,
        scope: VariableScope,
        started_at: float,
    ) -> NodeExecResult:
        """执行 wait 节点。"""
        resolved = resolve_params(node.params, scope)
        seconds_str = resolved.get("seconds", "1")
        try:
            seconds = float(seconds_str)
        except (ValueError, TypeError):
            seconds = 1.0

        # 安全检查
        action = Action(type="wait", params={"seconds": seconds})
        guard_result = self.guardrails.check(action)
        if guard_result.decision == BLOCK:
            return NodeExecResult(
                node_id=node.id, node_type="wait",
                status="FAILED",
                error=f"护栏拦截：{guard_result.reason}",
                started_at=started_at, finished_at=time.time(),
            )

        if not dry_run:
            time.sleep(seconds)

        finished_at = time.time()
        return NodeExecResult(
            node_id=node.id, node_type="wait",
            status="SUCCESS",
            started_at=started_at, finished_at=finished_at,
            variables_snapshot=scope.snapshot(),
        )

    def _execute_condition(
        self,
        node: Node,
        scope: VariableScope,
        started_at: float,
    ) -> NodeExecResult:
        """执行 condition 节点 — 表达式评估由 _resolve_next 完成。"""
        # condition 节点的核心逻辑在 _resolve_next 中完成分支选择
        # 此处仅记录执行状态
        expression = node.params.get("expression", "")
        try:
            result = _eval_expression(expression, scope)
        except Exception:
            result = False

        return NodeExecResult(
            node_id=node.id, node_type="condition",
            status="SUCCESS",
            started_at=started_at, finished_at=time.time(),
            variables_snapshot=scope.snapshot(),
        )

    def _execute_loop(
        self,
        node: Node,
        dry_run: bool,
        scope: VariableScope,
        started_at: float,
    ) -> NodeExecResult:
        """执行 loop 节点（while/for/for_each），max_iterations 硬上限 1000。"""
        resolved = resolve_params(node.params, scope)
        loop_type = resolved.get("loop_type", "while")
        max_iterations = min(
            int(resolved.get("max_iterations", 100)),
            1000,
        )

        if not node.children:
            return NodeExecResult(
                node_id=node.id, node_type="loop",
                status="FAILED",
                error="loop 节点没有子节点",
                started_at=started_at, finished_at=time.time(),
            )

        iteration = 0

        if loop_type == "while":
            condition = resolved.get("condition", "")
            while iteration < max_iterations:
                if self._check_emergency_stop():
                    break
                try:
                    should_continue = _eval_expression(condition, scope)
                except Exception:
                    should_continue = False
                if not should_continue:
                    break

                for child_id in node.children:
                    child_result = self._execute_node(
                        self._node_map.get(child_id), dry_run, scope,
                    )
                    if child_result.status in ("FAILED", "ABORTED"):
                        # 传播给 loop 节点
                        return NodeExecResult(
                            node_id=node.id, node_type="loop",
                            status=child_result.status,
                            error=child_result.error,
                            started_at=started_at, finished_at=time.time(),
                        )
                iteration += 1

        elif loop_type == "for":
            count_str = resolved.get("count", "1")
            try:
                count = min(int(count_str), max_iterations)
            except (ValueError, TypeError):
                count = 1
            count = min(count, max_iterations)

            for _ in range(count):
                if self._check_emergency_stop():
                    break
                for child_id in node.children:
                    child_node = self._node_map.get(child_id)
                    if child_node:
                        child_result = self._execute_node(
                            child_node, dry_run, scope,
                        )
                        if child_result.status in ("FAILED", "ABORTED"):
                            return NodeExecResult(
                                node_id=node.id, node_type="loop",
                                status=child_result.status,
                                error=child_result.error,
                                started_at=started_at, finished_at=time.time(),
                            )

        elif loop_type == "for_each":
            iterable_ref = resolved.get("iterable", "")
            item_var = resolved.get("item_var", "item")
            items = scope.get(
                iterable_ref.replace("{{variables.", "").replace("}}", ""),
                [],
            )
            if not isinstance(items, list):
                items = []

            for item in items[:max_iterations]:
                if self._check_emergency_stop():
                    break
                scope.set_local(item_var, item)
                for child_id in node.children:
                    child_node = self._node_map.get(child_id)
                    if child_node:
                        child_result = self._execute_node(
                            child_node, dry_run, scope,
                        )
                        if child_result.status in ("FAILED", "ABORTED"):
                            return NodeExecResult(
                                node_id=node.id, node_type="loop",
                                status=child_result.status,
                                error=child_result.error,
                                started_at=started_at, finished_at=time.time(),
                            )

        return NodeExecResult(
            node_id=node.id, node_type="loop",
            status="SUCCESS",
            started_at=started_at, finished_at=time.time(),
            variables_snapshot=scope.snapshot(),
        )

    # ------------------------------------------------------------------
    # 错误处理
    # ------------------------------------------------------------------

    def _handle_node_error(
        self,
        node: Node,
        scope: VariableScope,
        error: str,
        started_at: float,
        action_result: Optional[ExecResult] = None,
    ) -> NodeExecResult:
        """处理节点执行错误，应用错误策略。"""
        # 确定错误策略
        strategy = node.error_strategy
        if strategy is None and self._workflow is not None:
            strategy = self._workflow.error_strategy
        if strategy is None:
            strategy = ErrorStrategy(type=ErrorStrategyType.abort_type)

        handle_result = self._error_handler.handle(
            node.id, error, strategy,
        )

        if handle_result.action == ErrorAction.retry:
            # 重试：等待退避时间
            if handle_result.delay > 0 and not self._dry_run:
                time.sleep(handle_result.delay)
            # 注意：重试由上层调用方（_traverse）再次入栈实现
            # 这里返回 RUNNING 状态让遍历器重新处理
            return NodeExecResult(
                node_id=node.id, node_type=str(node.type.value),
                status="RUNNING",
                error=handle_result.message,
                started_at=started_at, finished_at=time.time(),
                action_result=action_result,
            )

        return NodeExecResult(
            node_id=node.id, node_type=str(node.type.value),
            status=handle_result.node_status,
            error=handle_result.message,
            started_at=started_at, finished_at=time.time(),
            action_result=action_result,
            variables_snapshot=scope.snapshot(),
        )

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _check_emergency_stop(self) -> bool:
        """检查紧急停止标志。"""
        if self.emergency_stop is not None:
            return self.emergency_stop.is_stopped()
        return False

    @staticmethod
    def _determine_final_state(logs: List[NodeExecResult]) -> str:
        """根据节点日志确定最终执行状态。"""
        if not logs:
            return "FAILED"

        # 如果有 ABORTED 节点 → ABORTED
        if any(log.status == "ABORTED" for log in logs):
            return "ABORTED"
        # 如果有 FAILED → FAILED
        if any(log.status == "FAILED" for log in logs):
            return "FAILED"
        # 如果有 DEGRADED → DEGRADED（部分成功）
        if any(log.status == "DEGRADED" for log in logs):
            return "DEGRADED"
        # 所有节点成功
        return "SUCCESS"
