---
title: "P0/P1/AC4/AC5 安全修复落地 — 确认默认 single + 黑名单扩面 + ESC 接线 + 脱敏默认开"
type: concept
project: "自动系统"
source: journal.md
tags: ["dry_run", "pytest", "安全", "测试", "黑名单"]
concept_id: journal-013
created: 2026-07-08
updated: 2026-07-08 11:29
---

# P0/P1/AC4/AC5 安全修复落地 — 确认默认 single + 黑名单扩面 + ESC 接线 + 脱敏默认开

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔧 [鲁千机] P0/P1/AC4/AC5 安全修复落地 — 确认默认 single + 黑名单扩面 + ESC 接线 + 脱敏默认开
🔧 [鲁千机-fix-3] 独立核验：cli --confirm 默认 single、auto_confirm=False（移除 skip 短路）、run_cli 内 emergency.arm_hotkey() 已接线、--real 禁止与 --confirm skip 共存；guardrails 归一化黑名单扩面（del /f /q、rm /rf、rd /s /q、format 裸、powershell -e/-enc 执行、curl|sh、reg delete、diskpart 等）+ gate() deny-unconfirmed（skip 不再自动放行高危）+ AC4 指令/数据边界（INJECTION_PATTERNS 命中即 CONFIRM）；config.screen_mask_sensitive 默认 True。pytest 全绿 137 passed；dry_run 演示无 pyautogui 触碰；新增对抗测试（powershell 变体/注入边界/默认脱敏/cli 安全）先红后绿。
🔧 [鲁千机] P0/P1/AC4/AC5 安全修复落地 — 确认默认 single + 黑名单扩面 + ESC 接线 + 脱敏默认开

---
*由 extract_concepts_from_journal.py 自动提炼*