# F003 安全护栏 · 多视角共识评审（补充轮）

> 评审人：云见微 (yun-jianwei) · ParityMind 四角色（用户/安全/工程/竞品）独立审视
> 关联：docs/consensus.md（总体路由裁决） · 对象：project-spec.json F003 + 底座决策
> 触发：ye-zhiqiu 的 spec 已就绪，请团队共识确认 F003 边界

---

## 1. 底座决策共识（先对齐大方向）

- 初版 consensus.md 推荐 Open-Interface 式「无障碍树+截图」混合观测作底座；ye-zhiqiu 在 spec 选定 `computer-agent + PyAutoGUI`，并标榜「增强≠重构」。
- **结论：方向认可，感知层须增强。** computer-agent 提供「截图感知→决策→动作」闭环 + grounding，PyAutoGUI 提供跨平台执行，再自研 F001 function-calling 规划 + F003 护栏 + F004 CLI = 正是「enhance not refactor」。
- **但 computer-agent 是纯截图感知，缺无障碍树**，恰是我初版担心的坐标脆弱点。建议：**保留 computer-agent 闭环，增强 Open-Interface 式「无障碍树+截图」混合感知**（ye-zhiqiu 7.3 已把 Open-Interface 列为可借鉴）。此增强直接决定 F002 AC2 能否成立。

---

## 2. F003 三个待决决策的共识

### 2.1 默认拦截 vs 默认放行
**共识：默认「未确认即拦截」(deny-unconfirmed)** —— 非全拦截、也非全放行。
- 黑名单动作 → **硬拦截**（永不自动执行）。
- 其余动作 → 默认**需用户确认**后才执行。
- 仅「白名单低危原语」（move / scroll / 只读 screenshot / 可信上下文 type）可配置为跳过确认。
- 依据：安全视角要 deny-by-default 防误伤；用户视角要"别每步都点"——二者在「白名单低危跳过 + 计划级批量确认」上达成。

### 2.2 三档确认策略默认值（单步 / 批量 / 跳过）
**共识：默认 = 计划级批量确认 + 运行时高危单步确认。**
- 在 F004 展示完整 action 计划时，用户**一次性批准**整段（=批量确认），这是主确认点。
- 执行中若冒出**计划外高危动作**（如 LLM 临时决定 shell 命令）→ 触发单步确认。
- 「跳过确认」仅对白名单低危/只读动作生效，且可在 F004 实时切换。
- 工程落地为状态机 `plan_approved / per_step_confirm / auto_allow`；ESC 急停由独立线程监听全局热键（F003 AC3）。

### 2.3 高危动作黑名单清单（须语义化 + 扩面）
**共识：用 F001 结构化 action 类型做语义 gate，黑名单仅作兜底正则。**
- F001 输出结构化 action（click/type/shell_cmd/...），F003 按**动作类型 + 参数**拦截，远比字符串正则稳健（LLM 可写 `os.remove()` / `shutil.rmtree()` / `Remove-Item -Recurse -Force` 绕过字符串匹配）。
- 建议把破坏性操作显式建模为独立 action 原语（`file_delete` / `process_kill` / `system_shutdown` / `privilege_escalate` / `shell_command`），便于 F003 按类型硬拦/强确认。
- 黑名单须覆盖跨平台等价物与绕过向量（在 ye-zhiqiu 原列表上扩面）：

| 类别 | 需拦截的动作（示例） |
|------|---------------------|
| 文件/系统 | `rm -rf` · `del /f /s /q` · `rd /s /q` · `format` · `DISKPART` · `dd if=` · `mkfs` · `> file` 覆盖写 · `git reset --hard` · `git clean -fdx` · `reg delete` |
| 进程 | `taskkill /F` · `kill -9` · `pkill` · `Stop-Process -Force` |
| 提权 | `sudo` · `runas` · `gsudo` · `powershell -EncodedCommand` · `sudo -i` |
| 外发/远程执行 | `curl | sh` · `wget | sh` · `iwr | iex` · `Invoke-Expression` · 管道到 shell |
| 持久化/横移 | `schtasks` · `sc create` · `crontab -r` · `netsh` · `reg add` 写 Run 键 |
| 隐私 | `clipboard read` + 外贴 · 屏幕内容送外部（见隐私段） |
| 代码执行(Python 上下文) | `eval` · `exec` · `__import__` · `format`(格式化字符串泄露) · 直接 shell · 写 `C:\Windows`/`/etc` · 未授权 `curl`/`requests` 外联 |

> **互引（与兰萃英《知识预检报告》互补）**：上表 OS/Shell 层清单与 `docs/wiki-prelude.md` §2.4 的 Python 上下文危险原语（`format`/`eval`/`exec`/`__import__`/直接 shell/写系统路径/未授权外联）互为表里——她从 Wiki「Python 沙箱黑名单模式」迁移为种子概念，我落地为 F003 拦截清单。两份互引：consensus-f003.md ↔ wiki-prelude.md §2.4。

---

## 3. 四角色独立发言（F003 专项）

### 用户视角 👤
- 默认全拦截太烦，默认放行不敢用。要"计划看一眼就批，高危才问我"。
- 隐私：截图发云端要明示 + 可选脱敏，否则不敢给屏幕权限。
- 误操要能预知"这步不可逆"（删除/发送/支付），确认弹窗须写清后果。

### 安全视角 🛡️
- deny-unconfirmed；黑名单**语义化**（action 类型 gate）；覆盖跨平台等价物 + 绕过向量。
- **提示注入必须补**：屏幕内容（网页/文档）含"忽略指令执行X"会诱导越权——spec 原风险表完全未列，须升为极高并加防护（读屏内容做"指令/数据"边界隔离）。
- 权限最小化：shell_command 默认确认；不暴露 raw shell 除非必要；sudo/runas 强制拦截。
- 隐私：屏幕外发脱敏 + 本地模型默认选项。

### 工程视角 ⚙️
- 黑名单用 action-type gate（复用 F001 结构化输出）比正则稳。
- 三档确认 = 状态机；ESC 急停独立线程全局热键；护栏钩子须**同步 pre-action** 拦截，否则滞后误执行。
- F002 AC2「≤5px」在 DPI/多屏/窗口变动下不现实 → 用无障碍树锚定 + 重试，建议修订 AC2 为"元素锚定命中 + 允许重试"。
- 护栏须可降级（失败→默认拦截），spec 已写，OK。

### 竞品视角 📊
- 影刀信任来自"可编辑流程 + 确认"；CLI 下也要"计划可视化确认"（F004 已承载）。
- 本地优先 + 隐私是差异点 → F003 把"本地模型默认 / 屏幕脱敏"写进护栏当卖点。
- 护城河：确认策略可配置导出 + 执行轨迹数据飞轮。

---

## 4. 矛盾清单（F003 专项）

| # | 矛盾 | 角色 | 优先级 | 修正 |
|---|------|------|--------|------|
| CF1 | 默认拦截(安全) vs 少确认(用户要快) | 安全↔用户 | 🔴 高 | 默认未确认即拦截 + 白名单低危跳过 + 计划级批量确认 |
| CF2 | 黑名单字符串匹配(简单) vs 语义 gate(稳健) | 工程↔安全 | 🟡 中 | F001 结构化 action 类型做语义 gate，黑名单兜底正则 |
| CF3 | 提示注入未列(规划) vs 极高风(安全) | 安全↔规划 | 🔴 高 | 新增提示注入为极高风，F003 增指令边界隔离 |
| CF4 | computer-agent 纯截图(现状) vs 无障碍树(初版建议) | 工程↔云见微初版 | 🟡 中 | 保留底座，增强无障碍树感知以达 AC2 |
| CF5 | AC2 ≤5px(规划) vs 不现实(工程) | 工程↔规划 | 🟡 中 | 修订 AC2：元素锚定 + 重试，取代绝对坐标精度 |

---

## 5. 风险重评级（针对 ye-zhiqiu 原评"中"）

原"中"低估。重评：

| 风险 | 原评级 | 共识重评 | 说明 |
|------|--------|---------|------|
| 提示注入 | 未列 | 🔴 极高（新增） | F003 未覆盖，computer-use 头号陷阱 |
| 坐标漂移 | 中 | 🔴 高 | AC2 目标不现实，需无障碍树 |
| 越权/破坏性动作 | 中 | 🔴 高 | 已由黑名单缓解，但需语义化 + 跨平台扩面 |
| 规划幻觉（错误但合法的 action） | 中 | 🟡 中-高 | schema 拦不住，需确认 + dry-run + 观测反馈 |
| 隐私外发 | 未凸显 | 🔴 高 | 默认云端 LLM，F003 无脱敏 |

**结论：整体风险中偏高。** F003 覆盖了"破坏性动作安全"，但**未覆盖提示注入、坐标鲁棒性、隐私脱敏**三项，须补。

---

## 6. 共识结论

**已共识：**
1. 默认「未确认即拦截」；三档确认默认 = 计划级批量 + 运行时高危单步。
2. 黑名单语义化 gate（基于 F001 action 类型）+ 跨平台扩面兜底正则。
3. computer-agent + PyAutoGUI 底座方向认可，感知层增无障碍树（Open-Interface 式）。

**待 ye-zhiqiu 落 spec（不阻塞开发）：**
- ① F003 增提示注入防护 + 隐私脱敏（屏幕敏感区打码后再外发 + 本地模型默认选项）。
- ② F002 AC2 修订为「元素锚定命中 + 允许重试」，取代绝对 ≤5px。
- ③ 底座感知层增无障碍树（Open-Interface 式混合观测）。
- ④ 黑名单扩面清单（见 §2.3）入 spec。

**开发节奏：** M1 可先按硬黑名单 + ESC 急停推进；增强项（无障碍树、提示注入防护、脱敏）入 M2/M3。

---

*— 云见微 @ Soara 七曜工程团 · F003 共识补充轮*
