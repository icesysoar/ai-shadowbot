# AI 版影刀（ai-shadowbot）— 全链闭环交付报告

> 自然语言驱动的桌面动作规划 RPA / Computer-Use agent。用户聊天说要干什么 → LLM 编译成原子动作（鼠标/键盘/截图/终端）→ 自动执行。
> 全链 7 环闭环：调研 → 需求 → 共识 → 开发(TDD) → Bug检测 → 双QA复验 → 知识提炼。

## 一、调研结论（开源"类影刀"工具图谱）
- **传统录制式 RPA**：Ui.Vision RPA、Taskt/sharpRPA、lingsuo_rpa(灵梭)、OpenRPA、TagUI、Robot Framework、RPALite、DrissionPage
- **AI 驱动（最贴近目标）**：computer-agent(suitedaces)、Open-Interface(AmberSahdev)、AutoGUI Agent、Cradle、NeuralAgent
- **架构裁决**：感知层(截图为主+目标混合无障碍树) / 执行层(PyAutoGUI+dry_run) / 规划·护栏·影刀流程自研 / 安全基线(白名单+危险确认+破坏性黑名单)

## 二、四特性实现（F001–F004，status=done）
| 特性 | 内容 | 关键文件 |
|------|------|---------|
| F001 自然语言规划 | LLM function-calling，OpenAI 兼容 + Mock 启发式 | `planner.py` |
| F002 执行引擎 | PyAutoGUI + dry_run；真实依赖 lazy import | `executor.py` `observer.py` |
| F003 安全护栏 | 三态闸门 + 黑名单 + 确认策略 + ESC + AC4 + AC5 | `guardrails.py` `cli.py` `config.py` |
| F004 CLI 聊天入口 | `--confirm single` 默认，`--real` 禁 skip | `cli.py` |

## 三、质量门禁：从缺陷到真闭环
**初轮 QA（凌澈明 + 云见微合并）发现**：P0×1（cli 默认 skip 关闸）/ P1×3（黑名单绕过 7 变体 / ESC 未接线 / 脱敏未接入）/ P2×3。F03 当时判定 **PARTIAL**（AC4/AC5 空壳）。

**返工修复**：
- P0：`--confirm` 默认 `skip→single`；`--real` 禁止与 `--confirm skip` 共存；删 `auto_confirm` 放行短路
- P1-1：废弃脆弱正则，改**命令归一化 + 动词集合**（覆盖跨平台等价物，不依赖参数顺序）
- P1-2：cli 启动处 `emergency.arm_hotkey()` 接线 ESC/Ctrl+C
- P1-3/AC5：`config.screen_mask_sensitive` 默认 `True`；`Observer.mask_sensitive_regions` 真实打码
- AC4：`_scan_injection` + `INJECTION_PATTERNS`，命中即 CONFIRM 绝不 ALLOW

**三轮独立核验（杜绝"假绿"）**：
1. 主理人写 `verify_security_fixes.py` —— **29 项行为断言全 PASS**
2. 凌澈明复验 —— 6/6 闭环，pytest **137 passed**
3. 云见微复验 —— F03 **PARTIAL → FULL**，含 R1–R4 残留风险

## 四、验证证据（可复现）
```bash
cd E:\WorkBuddy\自动系统
python verify_security_fixes.py     # 29 PASS
python -m pytest ai_shadowbot/tests -q   # 137 passed
```

## 五、知识提炼（Phase 5，兰萃英）
- 8 条高价值、可跨项目迁移概念入中央 wiki（`E:\WorkBuddy\AIproject-team\wiki\concepts\`），均 100 分
- 与既有「Python 沙箱黑名单模式」等形成双向 `[[双链]]`
- 健康度 **64/100**，0 淘汰
- 核心可迁移经验：**状态虚高陷阱→独立行为验证**、**deny-unconfirmed**、**黑名单归一化**、**dry_run 铁律**、**双 QA 独立复验**

## 六、残留风险（不阻断交付，M2/M3 跟进）
- **R1** AC4 仅参数命中兜底，诱导词可改写绕过
- **R2** 黑名单扩面缺口：`kill/pkill/Stop-Process`、`runas/gsudo`、`schtasks/netsh/crontab`、剪贴板隐私
- **R3** AC6 不可逆动作强提示未实现（`summarize` 仍通用）
- **R4** 本次未补对抗测试向量验证

## 七、交付物清单
- 代码包：`E:\WorkBuddy\自动系统\ai_shadowbot\`（actions/config/planner/executor/observer/guardrails/cli + tests）
- 独立验证：`E:\WorkBuddy\自动系统\verify_security_fixes.py`
- 文档：`docs/PRD.md` `docs/consensus.md` `docs/consensus-f003.md` `docs/qa-report.md` `docs/qa-mvp.md` `docs/wiki-prelude.md`
- 日志：`.autocode/journal.md`
- 知识：中央 wiki `E:\WorkBuddy\AIproject-team\wiki\concepts\`
