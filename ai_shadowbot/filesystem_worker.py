"""文件系统操作 Worker（F019）—— 封装文件/目录操作。

设计要点：
  - 所有方法返回统一 dict: {success: bool, data: ..., error: "..."}
  - 全部使用标准库 os/shutil，无额外依赖
  - 不绕过 guardrails（fs_delete 标记为 dangerous，由 guardrails 确认）
  - dry_run 模式下不真操作文件（由 engine 层控制）
"""
from __future__ import annotations

import os
import shutil
import time
from typing import Any, Dict, Optional


class FilesystemWorker:
    """文件系统操作 Worker。

    提供文件读写、复制/移动/删除、目录操作等基础能力。
    """

    @staticmethod
    def _success(data: Any = None) -> dict:
        return {"success": True, "data": data, "error": None}

    @staticmethod
    def _error(msg: str) -> dict:
        return {"success": False, "data": None, "error": msg}

    # ------------------------------------------------------------------
    # 文件读写
    # ------------------------------------------------------------------

    def read_file(self, path: str, encoding: str = "utf-8") -> dict:
        """读取文本文件内容。

        Args:
            path: 文件路径
            encoding: 编码，默认 utf-8

        Returns:
            {success, data: {content: "...", size: N, encoding: "..."}, error}
        """
        if not os.path.isfile(path):
            return self._error(f"文件不存在: {path}")

        try:
            with open(path, "r", encoding=encoding) as f:
                content = f.read()
            size = os.path.getsize(path)
            return self._success({
                "content": content,
                "size": size,
                "encoding": encoding,
            })
        except UnicodeDecodeError:
            # 尝试 GBK 编码
            try:
                with open(path, "r", encoding="gbk") as f:
                    content = f.read()
                size = os.path.getsize(path)
                return self._success({
                    "content": content,
                    "size": size,
                    "encoding": "gbk",
                })
            except Exception as e:
                return self._error(f"读取文件编码错误: {e}")
        except Exception as e:
            return self._error(f"读取文件失败: {e}")

    def write_file(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
    ) -> dict:
        """写入文本内容到文件（覆盖模式）。

        Args:
            path: 文件路径
            content: 要写入的文本内容
            encoding: 编码，默认 utf-8

        Returns:
            {success, data: {path: "...", bytes_written: N}, error}
        """
        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(path, "w", encoding=encoding) as f:
                f.write(content)

            size = os.path.getsize(path)
            return self._success({
                "path": path,
                "bytes_written": size,
            })
        except Exception as e:
            return self._error(f"写入文件失败: {e}")

    def append_file(self, path: str, content: str) -> dict:
        """追加文本内容到文件末尾。

        Args:
            path: 文件路径
            content: 要追加的文本内容

        Returns:
            {success, data: {path: "...", appended_bytes: N}, error}
        """
        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)

            with open(path, "a", encoding="utf-8") as f:
                f.write(content)

            return self._success({
                "path": path,
                "appended_bytes": len(content.encode("utf-8")),
            })
        except Exception as e:
            return self._error(f"追加文件失败: {e}")

    # ------------------------------------------------------------------
    # 文件复制/移动/删除
    # ------------------------------------------------------------------

    def copy_file(self, src: str, dst: str) -> dict:
        """复制文件。

        Args:
            src: 源文件路径
            dst: 目标文件路径

        Returns:
            {success, data: {src, dst, size}, error}
        """
        if not os.path.isfile(src):
            return self._error(f"源文件不存在: {src}")

        try:
            dst_dir = os.path.dirname(dst)
            if dst_dir:
                os.makedirs(dst_dir, exist_ok=True)

            shutil.copy2(src, dst)
            size = os.path.getsize(dst)
            return self._success({
                "src": src,
                "dst": dst,
                "size": size,
            })
        except Exception as e:
            return self._error(f"复制文件失败: {e}")

    def move_file(self, src: str, dst: str) -> dict:
        """移动/重命名文件。

        Args:
            src: 源文件路径
            dst: 目标文件路径

        Returns:
            {success, data: {src, dst}, error}
        """
        if not os.path.exists(src):
            return self._error(f"源文件不存在: {src}")

        try:
            dst_dir = os.path.dirname(dst)
            if dst_dir:
                os.makedirs(dst_dir, exist_ok=True)

            shutil.move(src, dst)
            return self._success({
                "src": src,
                "dst": dst,
            })
        except Exception as e:
            return self._error(f"移动文件失败: {e}")

    def delete_file(self, path: str) -> dict:
        """删除文件或目录。

        注意：此动作为不可逆操作，已在 actions.py 标记为 dangerous=True，
        guardrails 会要求二次确认。

        Args:
            path: 文件/目录路径

        Returns:
            {success, data: {path, deleted_type: "file"|"directory"}, error}
        """
        if not os.path.exists(path):
            return self._error(f"路径不存在: {path}")

        try:
            if os.path.isfile(path):
                os.remove(path)
                deleted_type = "file"
            elif os.path.isdir(path):
                shutil.rmtree(path)
                deleted_type = "directory"
            else:
                return self._error(f"无法识别的路径类型: {path}")

            return self._success({
                "path": path,
                "deleted_type": deleted_type,
            })
        except PermissionError as e:
            return self._error(f"权限不足，无法删除: {e}")
        except Exception as e:
            return self._error(f"删除失败: {e}")

    # ------------------------------------------------------------------
    # 目录操作
    # ------------------------------------------------------------------

    def list_dir(self, path: str) -> dict:
        """列出目录中的文件和子目录。

        Args:
            path: 目录路径

        Returns:
            {success, data: {path, files: [...], dirs: [...], total: N}, error}
        """
        if not os.path.isdir(path):
            return self._error(f"目录不存在或不是目录: {path}")

        try:
            entries = os.listdir(path)
            files = []
            dirs = []
            for entry in entries:
                full = os.path.join(path, entry)
                if os.path.isfile(full):
                    files.append(entry)
                elif os.path.isdir(full):
                    dirs.append(entry)

            return self._success({
                "path": path,
                "files": sorted(files),
                "dirs": sorted(dirs),
                "total": len(entries),
            })
        except PermissionError:
            return self._error(f"权限不足，无法列出目录: {path}")
        except Exception as e:
            return self._error(f"列出目录失败: {e}")

    def mkdir(self, path: str) -> dict:
        """创建目录（含父目录）。

        Args:
            path: 目录路径

        Returns:
            {success, data: {path, created: bool}, error}
        """
        try:
            existed = os.path.isdir(path)
            os.makedirs(path, exist_ok=True)
            return self._success({
                "path": path,
                "created": not existed,
            })
        except Exception as e:
            return self._error(f"创建目录失败: {e}")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def exists(self, path: str) -> dict:
        """检查文件或目录是否存在。

        Args:
            path: 文件/目录路径

        Returns:
            {success, data: {path, exists: bool, type: "file"|"directory"|null}, error}
        """
        try:
            exists_flag = os.path.exists(path)
            ptype = None
            if exists_flag:
                if os.path.isfile(path):
                    ptype = "file"
                elif os.path.isdir(path):
                    ptype = "directory"

            return self._success({
                "path": path,
                "exists": exists_flag,
                "type": ptype,
            })
        except Exception as e:
            return self._error(f"检查路径失败: {e}")

    def get_info(self, path: str) -> dict:
        """获取文件/目录详细信息。

        Args:
            path: 文件/目录路径

        Returns:
            {success, data: {path, size, mtime, ctime, type, exists}, error}
        """
        if not os.path.exists(path):
            return self._success({
                "path": path,
                "exists": False,
                "size": None,
                "mtime": None,
                "ctime": None,
                "type": None,
            })

        try:
            stat = os.stat(path)
            if os.path.isfile(path):
                ptype = "file"
            elif os.path.isdir(path):
                ptype = "directory"
            else:
                ptype = "other"

            return self._success({
                "path": path,
                "exists": True,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
                "type": ptype,
            })
        except Exception as e:
            return self._error(f"获取文件信息失败: {e}")
