---
title: "ReqAnaly 落成待完善清单为正式 spec（path B 第一输入，交叉 yun-jianwei 三道门禁 B4/B3/B1）"
type: concept
project: "自动系统"
source: journal.md
tags: ["规格"]
concept_id: journal-029
created: 2026-07-08
updated: 2026-07-08 11:29
---

# ReqAnaly 落成待完善清单为正式 spec（path B 第一输入，交叉 yun-jianwei 三道门禁 B4/B3/B1）

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🚩 [2026-07-08] ReqAnaly 落成待完善清单为正式 spec（path B 第一输入，交叉 yun-jianwei 三道门禁 B4/B3/B1）
- project-spec.json 新增 F012(画布增强/Vue3+LiteGraph MVP 收口/planned)、F013(工程卫生治理/planned)、F014(端口统一+mode both 修复/planned)；含子任务 F012.1-6 / F013.1-5 / F014.1-2。
- 校正 F008 规格漂移(React Flow→Vue3+LiteGraph，标注 B4 反例)；补 F007 acceptance_criteria(AC1-3)。
- 新增 M9(画布增强与网关收口)、M10(工程卫生与治理 L5 前置) 里程碑。
- task.json 刷新：根 task.json 补 T-F007..T-F014（F001-F011 done / F012-F014 planned）；.autocode/task.json 补 F012/F013/F014 特性块。
- 起草 docs/process1-canvas-hardening.md（7类门禁模板：目标与边界/验收/决策点与未知项/依赖与约束/风险与回滚点/里程碑拆解/知识挂钩），供 process1_gate.py 校验、后续升 A(Go 模式)。
- 未改任何 .py；JSON 校验通过(F001-F014)。下一步：yun-jianwei 共识复核 → 派 claimed_by 实现。

---
*由 extract_concepts_from_journal.py 自动提炼*