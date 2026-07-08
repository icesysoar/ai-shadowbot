---
title: "F005 视觉坐标系统共识评审完成（只评审+写 docs，未改业务代码）— 见 docs/consensus-vision.md"
type: concept
project: "自动系统"
source: journal.md
tags: ["LLM", "dry_run", "安全", "黑名单"]
concept_id: journal-023
created: 2026-07-08
updated: 2026-07-08 11:29
---

# F005 视觉坐标系统共识评审完成（只评审+写 docs，未改业务代码）— 见 docs/consensus-vision.md

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔗 [云见微] F005 视觉坐标系统共识评审完成（只评审+写 docs，未改业务代码）— 见 docs/consensus-vision.md
- 知识注入 wiki_hook.inject("paritymind")：命中 dry_run 铁律（真实依赖 lazy import，零触碰鼠标）、HDA 增强≠重构、管线引擎避坑。
- 架构裁决：方案 A（多模态 LLM function-calling 返坐标）为主，D（LLM+OCR 补文本坐标）为渐进增强；B(OCR)/C(UI检测模型) 不作主干。理由：100% 复用 make_llm_client（OpenAIClient 已支持 image_url + tool_choice），零新客户端代码，准确率最高。
- 安全红线（不可协商，AC4 信道隔离硬要求）：视觉派生屏幕文本只作「数据/定位目标」，过 InjectionClassifier 后驱动动作，绝不信任为指令；AC5 脱敏(mask)必须在视觉识别之前且坐标 remap 回原图；信道隔离（固定 prompt + 强制 schema {x,y,label,confidence}）。
- 强制时序：截图→脱敏(AC5)→视觉识别(remap)→InjectionClassifier(AC4)→动作生成→guardrails→执行（注入检测先于动作生成）。
- L5 bridge：可选/非必须；若接仅暴露 vision_resolve(screenshot,query)->{x,y,label} 坐标服务，结果回主流水线仍过全闸门，L5 不得直接触发 executor。
- 兼容性零削弱：deny-unconfirmed（视觉 click 仍过 gate）/ dry_run（视觉依赖 lazy import，mock 假坐标）/ R2 破坏性黑名单（派生文本走归一化动词集合）/ R3 不可逆强提示（label 文本过分类器+文本签名）/ AC2（视觉坐标+无障碍树锚定互补）。
- 给鲁千机硬约束 5 条：①mask→remap 显式建模 ②label 进动作参数必过 InjectionClassifier+INJECTION_PATTERNS ③视觉依赖 lazy import+mock 假坐标 ④派生动作不削弱护栏 ⑤对抗验收（屏上伪装注入/坐标偏移可变体）+防状态虚高（回读屏幕真点中）。

---
*由 extract_concepts_from_journal.py 自动提炼*