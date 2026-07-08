# 开发日志

## 2025-07-08

### 🔧 F016: Excel/CSV Worker — status→done
- 新建 `ai_shadowbot/excel_worker.py`：ExcelWorker 类
  - read_csv/read_excel/write_csv/write_excel/merge_csv/filter_rows
  - openpyxl lazy import，csv 标准库
  - 统一返回 {success, data, error}
- 新建 `ai_shadowbot/tests/test_excel.py`：12 个测试（CSV 读写/合并/筛选/Engine 集成/Guardrails）
- engine.py：新增 `_execute_excel_action()` 路由（excel_read/excel_write）
- compiler.py：新增 Excel 关键词检测（读取.*excel|写入.*csv|合并.*csv|筛选.*行）
- canvas_api.py：PALETTE_NODES 新增"Excel"分类
- actions.py：新增 excel_read/excel_write 动作类型
- guardrails.py：summarize() 新增 Excel 动作摘要

### 🔧 F017: HTTP Worker — status→done
- 新建 `ai_shadowbot/http_worker.py`：HttpWorker 类
  - request/get/post/put/delete，requests lazy import
  - 统一返回 {success, data: {status_code, headers, body, elapsed_ms}, error}
- 新建 `ai_shadowbot/tests/test_http.py`：15 个测试（GET/POST/PUT/DELETE/超时/连接错误/Engine 集成/Guardrails）
- engine.py：新增 `_execute_http_action()` 路由
- compiler.py：新增 HTTP 关键词检测（发送.*请求|调用.*api|获取.*数据）
- canvas_api.py：PALETTE_NODES 新增"网络"分类
- actions.py：新增 http_request/http_get/http_post/http_put/http_delete
- guardrails.py：豁免 http_* 动作的 shell 破坏性命令扫描（HTTP DELETE 不应被误拦）

### 🔧 F019: Filesystem Worker — status→done
- 新建 `ai_shadowbot/filesystem_worker.py`：FilesystemWorker 类
  - read_file/write_file/append_file/copy_file/move_file/delete_file/list_dir/mkdir/exists/get_info
- 新建 `ai_shadowbot/tests/test_filesystem.py`：29 个测试（文件读写/复制/移动/删除/目录/查询/Engine 集成/Guardrails）
- engine.py：新增 `_execute_filesystem_action()` 路由
- compiler.py：新增文件系统关键词检测
- canvas_api.py：PALETTE_NODES 新增"文件"分类
- actions.py：新增 10 个 fs_* 动作类型（fs_delete 标记 dangerous=True）
- guardrails.py：fs_delete → CONFIRM（不可逆操作强提示）

### 全量测试
- 468 tests passed (0 regressions)
- 新增 63 tests: test_excel.py(12) + test_http.py(15) + test_filesystem.py(29) + test_planner.py(1-fix)
- dry_run 模式全部通过，不真操作文件/不发 HTTP 请求

🚩 [2026-07-08] [苏临渊] Phase D 全部完成 — 19/19 features done 🎉
- F023 画布撤销/重做: Ctrl+Z/Y + 快照栈MAX50 + 5处pushSnapshot + DPR恢复 (lin-zhiyu)
- F016 Excel: excel_worker.py (openpyxl+csv, 12tests)
- F017 HTTP: http_worker.py (requests, 15tests)
- F019 Filesystem: filesystem_worker.py (stdlib, 29tests)
- PALETTE_NODES: Excel(2) + 网络(5) + 文件(5) 三个新分类
- guardrails: fs_delete→CONFIRM不可逆提示, http_*豁免shell黑名单
- pytest: 468/468 passed 零回归
