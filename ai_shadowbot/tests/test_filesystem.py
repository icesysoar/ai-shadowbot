"""F019 测试 FilesystemWorker —— 全部 mock 模式 dry_run。

覆盖：
  - FilesystemWorker.read_file / write_file / append_file
  - FilesystemWorker.copy_file / move_file / delete_file
  - FilesystemWorker.list_dir / mkdir / exists / get_info
  - Engine._execute_filesystem_action 集成（dry_run 返回描述性结果）
  - guardrails.check() — fs_delete 走 CONFIRM（不可逆）
"""
from __future__ import annotations

import os
import tempfile
import time

import pytest

from ai_shadowbot.actions import Action
from ai_shadowbot.guardrails import ALLOW, BLOCK, CONFIRM, Guardrails


# ── 临时文件/目录 fixtures ─────────────────────────────────────────


@pytest.fixture
def tmp_file():
    """创建临时文本文件。"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8",
    ) as f:
        f.write("Hello World\n第二行内容")
        path = f.name
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def tmp_dir():
    """创建临时目录（含文件）。"""
    import tempfile
    d = tempfile.mkdtemp()
    # 创建一些文件和子目录
    with open(os.path.join(d, "a.txt"), "w") as f:
        f.write("file a")
    with open(os.path.join(d, "b.txt"), "w") as f:
        f.write("file b")
    os.makedirs(os.path.join(d, "subdir"), exist_ok=True)
    yield d
    try:
        import shutil
        shutil.rmtree(d, ignore_errors=True)
    except Exception:
        pass


# ── FilesystemWorker 单元测试 ──────────────────────────────────────


class TestFilesystemWorkerRead:
    """测试文件读取。"""

    def test_read_file_success(self, tmp_file):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.read_file(tmp_file)
        assert result["success"] is True
        assert "Hello World" in result["data"]["content"]
        assert result["data"]["encoding"] == "utf-8"

    def test_read_file_not_found(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.read_file("/nonexistent/file.txt")
        assert result["success"] is False
        assert "不存在" in result["error"]

    def test_read_file_gbk_fallback(self, tmp_path):
        """GBK 编码文件可以正确读取。"""
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "gbk.txt")
        with open(path, "w", encoding="gbk") as f:
            f.write("中文内容")
        result = worker.read_file(path, encoding="ascii")  # ascii 失败 → gbk fallback
        assert result["success"] is True
        assert "中文内容" in result["data"]["content"]


class TestFilesystemWorkerWrite:
    """测试文件写入。"""

    def test_write_file_success(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "output.txt")
        result = worker.write_file(path, "test content")
        assert result["success"] is True
        assert os.path.isfile(path)
        with open(path, "r") as f:
            assert f.read() == "test content"

    def test_write_file_creates_parent_dirs(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "deep" / "nested" / "output.txt")
        result = worker.write_file(path, "deep content")
        assert result["success"] is True
        assert os.path.isfile(path)

    def test_append_file_success(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "append.txt")
        worker.write_file(path, "line1\n")
        result = worker.append_file(path, "line2\n")
        assert result["success"] is True
        with open(path, "r") as f:
            content = f.read()
        assert "line1" in content
        assert "line2" in content


class TestFilesystemWorkerCopyMoveDelete:
    """测试文件复制/移动/删除。"""

    def test_copy_file_success(self, tmp_file, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        dst = str(tmp_path / "copied.txt")
        result = worker.copy_file(tmp_file, dst)
        assert result["success"] is True
        assert os.path.isfile(dst)

    def test_copy_file_src_not_found(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.copy_file("/nonexistent.txt", "/tmp/out.txt")
        assert result["success"] is False

    def test_move_file_success(self, tmp_file, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        dst = str(tmp_path / "moved.txt")
        result = worker.move_file(tmp_file, dst)
        assert result["success"] is True
        assert os.path.isfile(dst)
        assert not os.path.isfile(tmp_file)  # 源已消失

    def test_delete_file_success(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "to_delete.txt")
        with open(path, "w") as f:
            f.write("delete me")
        result = worker.delete_file(path)
        assert result["success"] is True
        assert not os.path.isfile(path)

    def test_delete_directory_success(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        d = str(tmp_path / "to_delete_dir")
        os.makedirs(d)
        with open(os.path.join(d, "file.txt"), "w") as f:
            f.write("x")
        result = worker.delete_file(d)
        assert result["success"] is True
        assert not os.path.isdir(d)

    def test_delete_not_found(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.delete_file("/nonexistent.txt")
        assert result["success"] is False
        assert "不存在" in result["error"]


class TestFilesystemWorkerDir:
    """测试目录操作。"""

    def test_list_dir_success(self, tmp_dir):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.list_dir(tmp_dir)
        assert result["success"] is True
        assert "a.txt" in result["data"]["files"]
        assert "b.txt" in result["data"]["files"]
        assert "subdir" in result["data"]["dirs"]

    def test_list_dir_not_found(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.list_dir("/nonexistent")
        assert result["success"] is False

    def test_mkdir_success(self, tmp_path):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        path = str(tmp_path / "new_dir")
        result = worker.mkdir(path)
        assert result["success"] is True
        assert os.path.isdir(path)

    def test_mkdir_already_exists(self, tmp_dir):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.mkdir(tmp_dir)
        assert result["success"] is True
        assert result["data"]["created"] is False


class TestFilesystemWorkerQuery:
    """测试查询操作。"""

    def test_exists_true(self, tmp_file):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.exists(tmp_file)
        assert result["success"] is True
        assert result["data"]["exists"] is True
        assert result["data"]["type"] == "file"

    def test_exists_false(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.exists("/nonexistent")
        assert result["success"] is True
        assert result["data"]["exists"] is False
        assert result["data"]["type"] is None

    def test_exists_directory(self, tmp_dir):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.exists(tmp_dir)
        assert result["success"] is True
        assert result["data"]["type"] == "directory"

    def test_get_info_file(self, tmp_file):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.get_info(tmp_file)
        assert result["success"] is True
        assert result["data"]["exists"] is True
        assert result["data"]["type"] == "file"
        assert result["data"]["size"] > 0
        assert result["data"]["mtime"] is not None

    def test_get_info_not_found(self):
        from ai_shadowbot.filesystem_worker import FilesystemWorker
        worker = FilesystemWorker()
        result = worker.get_info("/nonexistent")
        assert result["success"] is True
        assert result["data"]["exists"] is False


# ── Engine 集成测试（dry_run） ─────────────────────────────────────


class TestEngineFilesystemIntegration:
    """测试 Engine._execute_filesystem_action —— dry_run 模式。"""

    @pytest.fixture
    def engine(self):
        from ai_shadowbot.engine import Engine
        from ai_shadowbot.executor import Executor
        guardrails = Guardrails()
        executor = Executor(guardrails=guardrails, dry_run=True)
        return Engine(
            executor=executor,
            guardrails=guardrails,
            dry_run=True,
        )

    def test_fs_read_dry_run(self, engine):
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={"atomic_action": "fs_read", "path": "/tmp/test.txt"},
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert result.action_result is not None
        assert "dry_run" in result.action_result.summary.lower()

    def test_fs_write_dry_run(self, engine):
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={
                "atomic_action": "fs_write",
                "path": "/tmp/output.txt",
                "content": "test",
            },
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        assert result.status == "SUCCESS"
        assert "dry_run" in result.action_result.summary.lower()

    def test_fs_delete_dry_run_with_confirm(self, engine):
        """fs_delete 是 dangerous 动作，dry_run 模式下通过 guardrails CONFIRM
        但由于 auto_confirm=False（默认），会被拦截。dry_run 模式下
        Engine._execute_atomic 会在 guardrails 阶段返回 FAILED（需确认）。
        """
        from ai_shadowbot.workflow import Node, NodeType
        from ai_shadowbot.variables import VariableScope

        node = Node(
            id="n2", type=NodeType.atomic,
            params={"atomic_action": "fs_delete", "path": "/tmp/to_delete.txt"},
            next="n3",
        )
        scope = VariableScope()
        result = engine._execute_node(node, dry_run=True, scope=scope)
        # fs_delete 标记为 dangerous=True，guardrails 返回 CONFIRM。
        # dry_run 模式下 auto_confirm=False → 应返回 FAILED。
        # 但引擎的行为：guardrails.check() 返回 CONFIRM → auto_confirm=False
        # → 返回 FAILED（需确认）
        assert result.status == "FAILED"
        assert "确认" in (result.error or "")


# ── Guardrails 集成测试 ────────────────────────────────────────────


class TestFilesystemGuardrails:
    """测试 guardrails 对 fs_* 的检查。"""

    def test_fs_read_allowed(self):
        guardrails = Guardrails()
        action = Action(type="fs_read", params={"path": "/tmp/test.txt"})
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_fs_write_allowed(self):
        guardrails = Guardrails()
        action = Action(
            type="fs_write", params={"path": "/tmp/test.txt", "content": "x"},
        )
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_fs_delete_confirm(self):
        """fs_delete 标记为 dangerous=True，应走 CONFIRM。"""
        guardrails = Guardrails()
        action = Action(type="fs_delete", params={"path": "/tmp/test.txt"})
        result = guardrails.check(action)
        assert result.decision == CONFIRM
        assert result.risky is True

    def test_fs_list_allowed(self):
        guardrails = Guardrails()
        action = Action(type="fs_list", params={"path": "/tmp"})
        result = guardrails.check(action)
        assert result.decision == ALLOW

    def test_fs_exists_allowed(self):
        guardrails = Guardrails()
        action = Action(type="fs_exists", params={"path": "/tmp"})
        result = guardrails.check(action)
        assert result.decision == ALLOW
