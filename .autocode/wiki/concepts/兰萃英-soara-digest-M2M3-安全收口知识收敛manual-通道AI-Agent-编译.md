---
title: "[兰萃英 / soara-digest] M2/M3 安全收口知识收敛（manual 通道，AI Agent 编译）"
type: concept
project: "自动系统"
source: journal.md
tags: ["LLM", "dry_run", "安全", "测试", "编码", "规格", "黑名单"]
concept_id: journal-021
created: 2026-07-08
updated: 2026-07-08 11:29
---

# [兰萃英 / soara-digest] M2/M3 安全收口知识收敛（manual 通道，AI Agent 编译）

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

📖 [2026-07-07] [兰萃英 / soara-digest] M2/M3 安全收口知识收敛（manual 通道，AI Agent 编译）
- 蒸馏数: 0（不重跑 quality_loop——本项目 journal 为「🚩 [date] [person] text」扁平格式，自动提取器产 0 条；按 soara-digest 既定「AI Agent 审核」manual 通道直接编译概念）。
- 提升数: 4 概念（新增 3 + 更新 1）｜淘汰数: 0
  - 新增① [[提示注入 LLM 语义分类器根治（R1/M4）：信道隔离+降级双通道]]（score 100，最高）——闭合「关键词改写绕过」根因；与 [[提示注入 AC4 指令/数据边界：短语命中即 CONFIRM]] 双向互引（mandated）。
  - 新增② [[不可逆动作强提示（R3/AC6）：GuardResult.confirm_prompt 后果+回滚点]]（score 96）——文本层+类型层；与 [[deny-unconfirmed 安全基线：确认策略绝不放行高危动作]] 互引。
  - 新增③ [[对抗测试 fuzz 向量（R4）：改写/编码/多语注入 + 扩面动词变体，闭合『测试数涨≠真闭环』]]（score 95）——与 [[双 QA 独立复验作为质量门禁：实现者自述≠真闭环]] / [[状态虚高陷阱：spec/task 标 done 但代码是 stub]] 互引，固化 MVP 状态虚高教训。
  - 更新④ [[破坏性黑名单：命令归一化+动词集合抗绕过]]（score 100 不变）——补 R2 扩面动词清单（kill/pkill/Stop-Process/runas/gsudo/schtasks/netsh/bitsadmin 无条件 BLOCK；crontab/certutil 危险子命令 BLOCK；clip→RISKY_COMMAND→CONFIRM），并互引 R1/R3/R4。
- 互引闭环：R1↔AC4（mandated 双向）；R3↔deny-unconfirmed；R4↔双QA/状态虚高陷阱；R2↔R1/R3/R4。ai-shadowbot 安全集群现 12 概念（R1/R2/R3/R4/AC4/AC5/dry_run/ESC/deny-unconfirmed/状态虚高/双QA/Python沙箱黑名单模式）。
- health 评分变化：evolver.py --report 真实重算（read-only，未伪造月报），概念 101→104，健康度 64→65（+1），stale 0 / retired 0；AI 领域均分升至 98（R1+R4 入列）。
- docs/qa-mvp.md 新增 §6「R1–R4 收敛状态（M2/M3 · 已收敛）」，标注原待关注项已收敛并指向对应 wiki 概念；凌澈明 #9 复验背书待最终确认。

---
*由 extract_concepts_from_journal.py 自动提炼*