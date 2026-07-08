---
title: "ReqAnaly 落共识到权威 spec (ye-zhiqiu)"
type: concept
project: "自动系统"
source: journal.md
tags: ["安全", "规格"]
concept_id: journal-002
created: 2026-07-08
updated: 2026-07-08 11:29
---

# ReqAnaly 落共识到权威 spec (ye-zhiqiu)

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🚩 [2026-07-06] ReqAnaly 落共识到权威 spec (ye-zhiqiu)
- F002 AC2 改『元素锚定命中+重试』取代 ≤5px；新增 AC5 无障碍树+截图混合感知(M2)。
- F003 扩为 6 条 AC：默认未确认即拦截 / 语义化 gate(跨平台扩面) / 三档确认状态机(计划级批量+运行时高危单步) / 提示注入防护(极高) / 隐私脱敏+本地默认 / 不可逆动作强提示。
- F001 增 AC5：破坏性操作显式建模为语义化 action 类型供 gate。
- M2 承载无障碍树感知，M3 集安全增强；新增 env SCREEN_MASK_SENSITIVE。
- task.json 增 T002.6(无障碍树)、T003.5(提示注入)、T003.6(脱敏)；T003.1/2 标题对齐语义 gate 与计划级确认。
- consensus_review 块标记 incorporated_by=ye-zhiqiu。

---
*由 extract_concepts_from_journal.py 自动提炼*