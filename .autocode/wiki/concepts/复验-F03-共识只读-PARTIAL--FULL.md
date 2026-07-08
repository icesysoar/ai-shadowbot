---
title: "复验 F03 共识（只读）— PARTIAL → FULL"
type: concept
project: "自动系统"
source: journal.md
tags: ["安全", "测试", "黑名单"]
concept_id: journal-016
created: 2026-07-08
updated: 2026-07-08 11:29
---

# 复验 F03 共识（只读）— PARTIAL → FULL

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔍 [云见微] 复验 F03 共识（只读）— PARTIAL → FULL
- 默认闸门 deny-unconfirmed、ESC 接线、AC4 结构边界(INJECTION_PATTERNS+_scan_injection→CONFIRM)、AC5 脱敏(config 默认 True+observer 真实打码)、AC2 7 绕过变体均闭环。
- 残留风险（不阻断交付，M2/M3 跟进）：R1 AC4 仅参数命中兜底、关键词可改写绕过；R2 黑名单扩面缺口(kill/pkill/Stop-Process、runas/gsudo、schtasks/netsh/crontab、clipboard 隐私)；R3 AC6 不可逆动作强提示未实现(summarize 仍通用)；R4 本次未补对抗测试向量验证。

---
*由 extract_concepts_from_journal.py 自动提炼*