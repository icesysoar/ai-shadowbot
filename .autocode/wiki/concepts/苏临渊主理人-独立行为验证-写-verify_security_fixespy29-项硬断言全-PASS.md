---
title: "[苏临渊/主理人] 独立行为验证 — 写 verify_security_fixes.py（29 项硬断言，全 PASS）"
type: concept
project: "自动系统"
source: journal.md
tags: ["安全", "黑名单"]
concept_id: journal-014
created: 2026-07-08
updated: 2026-07-08 11:29
---

# [苏临渊/主理人] 独立行为验证 — 写 verify_security_fixes.py（29 项硬断言，全 PASS）

> 来源: `journal.md` | 项目: [[../projects/自动系统]]

🔍 [苏临渊/主理人] 独立行为验证 — 写 verify_security_fixes.py（29 项硬断言，全 PASS）
- SEC-1 deny-unconfirmed：gate(strategy=skip, 未确认)仍 CONFIRM；single 未确认仍 CONFIRM，确认后 ALLOW。
- SEC-2 破坏性黑名单：_scan_destructive 直接验证 13 变体全命中（rm -rf/-fr//rf、del /f /q、rd /f /s、format /fs:ntfs、dd if=、shutdown、sudo、powershell -e、curl|sh、git reset --hard、reg delete）；中文散文不误伤；type_text 承载破坏文本→BLOCK。
- SEC-3 AC4：含破坏动词的注入→先被黑名单 BLOCK（纵深）；纯注入诱导（无破坏动词）→CONFIRM 绝不 ALLOW。
- SEC-4 AC5：Config.screen_mask_sensitive 默认 True；Observer.mask_sensitive_regions 空 regions→整图像素化不崩。
- SEC-5 P1-2：EmergencyStop.arm_hotkey() 可调用不抛异常。结论：修复非假绿，真闭环。

---
*由 extract_concepts_from_journal.py 自动提炼*