---
title: "F005 视觉坐标系统知识预检完成（只读 Wiki + 写 docs，未改业务代码）— 见 docs/wiki-prelude-vision.md"
type: concept
project: "自动系统"
source: journal.md
tags: ["dry_run", "安全", "黑名单"]
concept_id: journal-022
created: 2026-07-08
updated: 2026-07-08 11:29
---

# F005 视觉坐标系统知识预检完成（只读 Wiki + 写 docs，未改业务代码）— 见 docs/wiki-prelude-vision.md

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

📖 [兰萃英] F005 视觉坐标系统知识预检完成（只读 Wiki + 写 docs，未改业务代码）— 见 docs/wiki-prelude-vision.md
- 检索 AIproject-team/wiki/concepts（~90 条），命中 12 条高相关概念（AC4 信道隔离/R1 根治、AC5 脱敏、dry_run lazy import、deny-unconfirmed、破坏性黑名单、不可逆强提示、双 QA、状态虚高、对抗 fuzz、Python 沙箱、妙想≠成交）。
- 提出 3 对互引：AC4 信道隔离←→F005 R1 根治（视觉读屏=最大注入面）/ AC5 脱敏←→截图打码（须 remap 坐标）/ dry_run←→视觉模块 lazy import（mock 零依赖）。
- 输出 F005 专属 5 条避坑：①脱敏在识别前且坐标 remap ②屏上文字过 InjectionClassifier ③mock 零依赖 ④视觉派生动作不削弱 guardrails ⑤状态虚高（标 done 前真落盘+行为验证）。

---
*由 extract_concepts_from_journal.py 自动提炼*