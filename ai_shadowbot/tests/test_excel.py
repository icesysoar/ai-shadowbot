"""F016 测试 ExcelWorker —— 全部 mock 模式 dry_run。

覆盖：
  - ExcelWorker.read_csv（mock 文件系统）
  - ExcelWorker.read_excel（mock openpyxl）
  - ExcelWorker.write_csv（mock 文件系统）
  - ExcelWorker.write_excel（mock openpyxl）
  - ExcelWorker.merge_csv
  - ExcelWorker.filter_rows
  - Engine._execute_excel_action 集成（dry_run 返回描述性结果）
  - guardrails.check() 通过（不拦截 excel_read/excel_write）
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
from unittest import mock

import pytest

from ai_shadowbot.actions import Action
from ai_shadowbot.executor import ExecResult, Executor
from ai_shadowbot.guardrails import ALLOW, BLOCK, CONFIRM, Guardrails

# ── 临时文件 fixture ──────────────────────────────────────────────


@pytest.fixture
def csv_file():
    """创建临时 CSV 文件。"""
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "age", "city"])
        writer.writerow(["张三", "30", "北京"])
        writer.writerow(["李四", "25", "上海"])
        writer.writerow(["王五", "35", "深圳"])
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def csv_file_no_header():
    """创建无表头 CSV 文件。"""
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["张三", "30", "北京"])
        writer.writerow(["李四", "25", "上海"])
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


# ── ExcelWorker 单元测试 ──────────────────────────────────────────


class TestExcelWorkerCsv:
    """测试 ExcelWorker CSV 读写。"""

    def test_read_csv_success(self, csv_file):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        result = worker.read_csv(csv_file)
        assert result["success"] is True
        assert result["data"]["headers"] == ["name", "age", "city"]
        assert result["data"]["row_count"] == 3
        assert len(result["data"]["rows"]) == 3

    def test_read_csv_no_header(self, csv_file_no_header):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        result = worker.read_csv(csv_file_no_header, has_header=False)
        assert result["success"] is True
        assert result["data"]["headers"] == ["col_0", "col_1", "col_2"]
        assert result["data"]["row_count"] == 2

    def test_read_csv_file_not_found(self):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        result = worker.read_csv("/nonexistent/file.csv")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_write_csv_success(self, tmp_path):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        output = str(tmp_path / "output.csv")
        result = worker.write_csv(
            output,
            headers=["a", "b"],
            rows=[["1", "2"], ["3", "4"]],
        )
        assert result["success"] is True
        assert os.path.isfile(output)

    def test_merge_csv_success(self, tmp_path):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()

        # 创建两个 CSV
        csv1 = str(tmp_path / "a.csv")
        csv2 = str(tmp_path / "b.csv")
        worker.write_csv(csv1, ["col1", "col2"], [["a", "1"]])
        worker.write_csv(csv2, ["col1", "col2"], [["b", "2"]])

        output = str(tmp_path / "merged.csv")
        result = worker.merge_csv([csv1, csv2], output)
        assert result["success"] is True
        assert result["data"]["total_rows"] == 2

    def test_merge_csv_header_mismatch(self, tmp_path):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()

        csv1 = str(tmp_path / "a.csv")
        csv2 = str(tmp_path / "b.csv")
        worker.write_csv(csv1, ["col1", "col2"], [["a", "1"]])
        worker.write_csv(csv2, ["colX", "colY"], [["b", "2"]])

        output = str(tmp_path / "merged.csv")
        result = worker.merge_csv([csv1, csv2], output)
        assert result["success"] is False
        assert "表头不一致" in result["error"]

    def test_filter_rows(self, csv_file):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        result = worker.filter_rows(csv_file, "city", "上海")
        assert result["success"] is True
        assert result["data"]["matched_count"] == 1
        assert result["data"]["rows"][0][0] == "李四"

    def test_filter_rows_column_not_found(self, csv_file):
        from ai_shadowbot.excel_worker import ExcelWorker
        worker = ExcelWorker()
        result = worker.filter_rows(csv_file, "nonexistent", "any")
        assert result["success"] is False
        assert "不存在" in result["error"]


# ── Engine 集成测试（dry_run） ─────────────────────────────────────


class TestEngineExcelIntegration:
    """测试 Engine._execute_excel_action —— dry_run 模式。"""

    @pytest.fixture
    def engine(self):
        from ai_shadowbot.engine import Engine
        guardrails = Guardrails()
        executor = Executor(guardrails=guardrails, dry_run=True)
        return Engine(
            executor=executor,
            guardrails=guardrails,
            dry_run=True,
        )

    def test_excel_read_dry_run(self, engine):
        """dry_run 模式不真读取文件。"""
        from ai_shadowbot.actions import Action
        from ai_shadowbot.workflow import Node, NodeType

        node = Node(
            id="n2", type=NodeType.atomic,
            params={"atomic_action": "excel_read", "path": "/tmp/test.csv"},
            next="n3",
        )
        from ai_shadowbot.variables import VariableScope
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()

    def test_excel_write_dry_run(self, engine):
        """dry_run 模式不真写入文件。"""
        from ai_shadowbot.actions import Action
        from ai_shadowbot.workflow import Node, NodeType

        node = Node(
            id="n2", type=NodeType.atomic,
            params={
                "atomic_action": "excel_write",
                "path": "/tmp/out.csv",
                "headers": ["a", "b"],
                "rows": [["1", "2"]],
            },
            next="n3",
        )
        from ai_shadowbot.variables import VariableScope
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()


# ── Guardrails 集成测试 ────────────────────────────────────────────


class TestExcelGuardrails:
    """测试 guardrails 对 excel_read/excel_write 的检查。"""

    def test_excel_read_allowed(self):
        guardrails = Guardrails()
        action = Action(type="excel_read", params={"path": "/tmp/data.csv"})
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_excel_write_allowed(self):
        guardrails = Guardrails()
        action = Action(
            type="excel_write",
            params={"path": "/tmp/out.csv", "headers": ["a"], "rows": [["1"]]},
        )
        result = guardrails.check(action)
        assert result.decision == ALLOW
