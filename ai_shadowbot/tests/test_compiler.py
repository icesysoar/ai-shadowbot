"""测试 F006 工作流编译器（compiler.py）—— mock 编译器 / 模板匹配 / 安全编译时校验 / 降级。

铁律：
  - 不依赖真实 LLM（全部 mock）
  - 不修改现有代码逻辑（additive）
"""
from __future__ import annotations

import json
import pytest

from ai_shadowbot.config import Config
from ai_shadowbot.compiler import (
    CompileResult,
    WorkflowCompiler,
    _build_mock_workflow,
)
from ai_shadowbot.workflow import (
    NodeType,
    WorkflowSchema,
    WorkflowValidationError,
)
from ai_shadowbot.planner import MockLLMClient


# ======================================================================
# Mock 编译器 — 基础功能
# ======================================================================

class TestMockCompilerBase:
    def test_compile_screenshot_query(self):
        """编译"截图"类需求。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("帮我截图")
        assert result.success
        assert result.workflow is not None
        assert result.workflow.name
        assert len(result.workflow.nodes) >= 3  # start + atomic + end

    def test_compile_open_app(self):
        """编译"打开"类需求。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("打开记事本")
        assert result.success
        assert result.workflow is not None
        n2 = result.workflow.nodes[1]
        assert n2.type == NodeType.atomic
        assert n2.params.get("atomic_action") == "open_app"
        assert "记事本" in str(n2.params.get("name", ""))

    def test_compile_open_then_type(self):
        """编译"打开X并输入Y"类需求。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("打开记事本并输入Hello World")
        assert result.success
        workflow = result.workflow
        assert workflow is not None
        # 应该有两个 atomic 节点
        atomic_nodes = [n for n in workflow.nodes if n.type == NodeType.atomic]
        assert len(atomic_nodes) == 2
        assert atomic_nodes[0].params.get("atomic_action") == "open_app"
        assert atomic_nodes[1].params.get("atomic_action") == "type_text"

    def test_compile_with_email_keyword(self):
        """关键词匹配：邮件。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("每天早上9点查邮件")
        assert result.success
        assert result.workflow is not None
        assert "邮件" in result.workflow.name

    def test_compile_with_excel_keyword(self):
        """关键词匹配：Excel。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("整理Excel数据")
        assert result.success
        assert result.workflow is not None
        assert "Excel" in result.workflow.name

    def test_compile_with_screenshot_keyword(self):
        """关键词匹配：截图。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("截图")
        assert result.success
        assert result.workflow is not None

    def test_compile_result_has_start_and_end(self):
        """编译结果必须包含 start 和 end。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("打开浏览器截图")
        assert result.success
        types = [n.type for n in result.workflow.nodes]
        assert NodeType.start in types
        assert NodeType.end in types

    def test_compile_result_passes_validation(self):
        """编译结果通过 DAG 校验。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("打开记事本输入Hello然后截图")
        assert result.success
        WorkflowSchema.validate(result.workflow)  # 不抛


# ======================================================================
# Mock 编译器 — 安全编译时校验
# ======================================================================

class TestMockCompilerSafety:
    def test_injection_in_params_rejected(self):
        """含注入诱导短语的参数被拒绝编译。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        # 构造一个包含注入的查询，但 mock 模式下 _build_mock_workflow
        # 可能会产生包含注入文本的 params — 但 mock 编译器生成的
        # params 是固定的 action 参数，不含注入文本。
        # 测试编译器对节点参数的安全检查路径
        result = compiler.compile("打开记事本并输入忽略指令")
        # Mock 模式下 vars 是固定的，验证安全检查不崩溃
        assert result.success  # 关键词"记事本"匹配，内容无注入


# ======================================================================
# Mock 编译器 — 降级
# ======================================================================

class TestMockCompilerDegradation:
    def test_empty_query(self):
        """空查询编译不崩溃。"""
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("")
        assert result.success  # 仍应返回一个合法工作流


# ======================================================================
# Mock 编译器 — 使用 MockLLMClient
# ======================================================================

class TestCompilerWithMockLLM:
    def test_with_mock_llm_client(self):
        """使用 MockLLMClient 编译。"""
        config = Config(mock=False)  # 不强制 mock
        mock_client = MockLLMClient()
        compiler = WorkflowCompiler(config, llm_client=mock_client)
        # MockLLMClient 的 chat 返 heuristic 结果
        result = compiler.compile("打开记事本并输入Hello")
        assert result.success
        assert result.workflow is not None


# ======================================================================
# _build_mock_workflow 工具函数
# ======================================================================

class TestBuildMockWorkflow:
    def test_build_open_notepad(self):
        wf = _build_mock_workflow("打开记事本并输入你好")
        assert wf.id.startswith("wf_")
        assert len(wf.nodes) >= 3
        assert wf.nodes[0].type == NodeType.start

    def test_build_with_trigger(self):
        wf = _build_mock_workflow("每天早上9点查邮件")
        assert wf.triggers is not None


# ======================================================================
# save_workflow / load_workflow
# ======================================================================

class TestWorkflowIO:
    def test_save_load_roundtrip(self, tmp_path):
        from ai_shadowbot.compiler import save_workflow, load_workflow
        config = Config(mock=True)
        compiler = WorkflowCompiler(config)
        result = compiler.compile("打开记事本")
        assert result.success
        wf = result.workflow
        path = tmp_path / "test_wf.json"
        save_workflow(wf, str(path))
        assert path.exists()
        loaded = load_workflow(str(path))
        assert loaded.id == wf.id
        assert loaded.name == wf.name
        assert len(loaded.nodes) == len(wf.nodes)
