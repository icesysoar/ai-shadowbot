---
title: "[叶知秋 / ReqAnaly] F005 视觉坐标系统需求分析完成（仅规格，未改任何 .py）"
type: concept
project: "自动系统"
source: journal.md
tags: ["API", "LLM", "dry_run", "pytest", "安全", "测试", "规格", "黑名单"]
concept_id: journal-025
created: 2026-07-08
updated: 2026-07-08 11:29
---

# [叶知秋 / ReqAnaly] F005 视觉坐标系统需求分析完成（仅规格，未改任何 .py）

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

📖 [2026-07-07] [叶知秋 / ReqAnaly] F005 视觉坐标系统需求分析完成（仅规格，未改任何 .py）
- wiki_hook.inject("reqanaly") 已注入历史经验（knowledge-base.md 反模式）：① 提示注入仅正则可被同义改写绕过→须 LLM 语义分类器(R1/M4 已落地，F005 复用 InjectionClassifier)；② R2 黑名单扩面须区分无条件 BLOCK 动词与危险子命令；③ R3↔R2 在 git reset --hard 张力保持 R2 BLOCK。
- 已与同学科产出对齐：docs/consensus-vision.md（云见微 方案 A 为主 + 强制时序 + L5 可选）、docs/wiki-prelude-vision.md（兰萃英 5 条避坑 + 互引指针）。三方无冲突，本 PRD 直接采纳其架构选型与 mask→remap 时序。
- 产出 docs/PRD-vision.md：F005 完整 PRD（背景/架构选型§1.1/强制时序§1.2/目标/场景S1-S5/功能边界§4.2 含 L5 可选/非功能约束§5/子任务 F005.1-4 含接口契约与 AC/关键风险 R1-R8）。
- project-spec.json 新增 F005（status=planned、claimed_by 留空、depends_on[F001,F002]、含子任务 F005.1-4 与 M5 里程碑、collaboration_log 追加记录；F005 AC1 已含 mask→remap 条款）；F001-F004 未改动，JSON 校验通过。
- 五维验证结论：可行性✅/完整性✅/一致性✅/可测性✅（均高），风险🟠中(可控)。核心设计原则：① 不新增动作类型，仅填充 click{x,y}/type_text 既有参数（actions.py 单一事实来源不变）；② 视觉派生动作原样过 guardrails.gate()，AC4/AC5/R1/R2/R3 全链路不变；③ AC5 脱敏前置且坐标 remap 回原图(consensus CV5)；④ AC4/R1 屏幕 OCR 文字只作数据、过 InjectionClassifier→CONFIRM 绝不 ALLOW（极高风 R2 缓解）；⑤ dry_run 下视觉模块 lazy import、不真截图/识别/点击（沿用 executor 铁律）；⑥ 缺 LLM_API_KEY→mock 确定性降级不编造坐标。
- 关键风险已落点：R1 敏感外发(高)→AC5 脱敏；R2 屏幕注入(极高)→AC4/R1；R3 多屏/DPI 坐标漂移(中高)→F002 AC2 重试+重截重定；R4 无 key(中高)→降级；R5 视觉幻觉(中高)→置信度+消歧+人工确认；R6 dry_run 误触(中)→lazy import；R7 脱敏致坐标偏移(中高)→mask→remap 显式建模；R8 L5 外部注入入口(中)→仅坐标服务+全闸门。
- 下一步：派 claimed_by（建议鲁千机）按 F005.1→F005.2→F005.3→F005.4 实现，沿用既有 pytest mock 范式补对抗测试（含屏上伪装注入/坐标偏移变体，防状态虚高）。
🔧 [鲁千机] F005 视觉坐标系统 TDD 实现完成。产出：ai_shadowbot/vision.py（VisionLocator.vision_resolve：截图→AC5脱敏→多模态LLM→坐标remap→返回{x,y,label,confidence}；无key/mock降级None；lazy import；信道隔离AC4）；planner.py OpenAIClient.vision_locate（additive，强制tool_choice）+ ground_to_action（INJECTION_PATTERNS快筛+InjectionClassifier）；cli.py --vision 演示开关；tests/test_vision.py 12项（mock脱敏remap/屏上注入拒驱动/无key降级/dry_run不加载）。pytest 189全绿（+12），verify 34 PASS无回归。F005已在project-spec.json标done(claimed_by=lu-qianji)。

---
*由 extract_concepts_from_journal.py 自动提炼*