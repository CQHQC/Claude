# CCX 项目 · 存档

> 飞书远程操控电脑：手机给飞书机器人发指令，电脑执行开软件/发文件/截屏/系统控制/自由 shell；接入 DeepSeek 后还能用自然语言对话+操作。
> 存档时间：2026/06/18 凌晨 · DeepSeek AI 集成已完成并验证。

## 当前状态：✅ 全部完成（基础 + 跨平台 + 开机自启 + 可复现 skill + AI）
- ✅ **基础机器人在跑**：macOS 由 launchd 常驻（`~/Library/LaunchAgents/com.ccx.feishu-remote.plist`，PID 在变正常），跨平台代码。手机发 /help、/open、/shot 等正常。当前以「纯指令」模式跑（因为还没填 AI key）。
- ✅ **DeepSeek AI 集成已写完并离线验证通过**：非斜杠自然语言 → DeepSeek（tool-use 循环：能答问 / 调用工具操作电脑）。代码、依赖、配置、skill 三处副本全部同步一致。
- ⏳ **唯一待用户做的**：去 https://platform.deepseek.com 申请 DeepSeek API key → 填进 `config.toml` 的 `ai_api_key` → 重启程序（`launchctl unload <plist> && launchctl load <plist>`）。填好后自然语言就会走 AI。

## 代码位置
`/Users/caiqianhu/Documents/Claudefile/feishu-remote/`
- `main.py` — 核心。跨平台 + DeepSeek AI（OpenAI 兼容 SDK）。
- `config.toml` — 真实飞书凭证+白名单已填（含 app_secret，勿外传）。`ai_api_key` 空 → AI 暂关闭。
- `config.example.toml` / `pyproject.toml`(依赖 lark-oapi + openai) / `README.md`

## AI 方案（已落地）
- 渠道：**DeepSeek**，用 `openai` Python SDK 指向 `https://api.deepseek.com`，模型 `deepseek-chat`，function calling。
  - 国内直连不被墙、便宜。想换通义/Kimi/本地 ollama，改 config 的 `ai_base_url`+`ai_model` 即可（OpenAI 兼容）。
- 行为：**斜杠指令**走快速零成本路径不变；**非斜杠自然语言** → DeepSeek：答问，或调用工具
  （run_command / open_target / screenshot / send_file / system_control）操作电脑。带每会话最近 12 条历史，支持指代。
- 实现：main.py 里 `AI_TOOLS`(OpenAI function 格式) + `ai_reply()`(chat.completions 工具循环) + `_exec_ai_tool()`。
- 验证：已用假客户端离线跑通「工具调用→回填结果→最终回复」和「纯聊天」两条路径；AI 关闭时模块也正常加载。

## 已完成的其它部分
- **跨平台**：main.py 按 sys.platform 自动走 macOS/Windows 命令（open/截屏/锁屏/睡眠/关机/音量/shell）。
- **开机自启**：macOS launchd plist 已装在跑。Windows 用启动文件夹 VBS（模板在 skill）。
- **可复现 skill** `feishu-remote-setup`：`~/.claude/skills/`、项目副本 `feishu-remote-setup-skill/`、桌面 `feishu-remote-setup-skill.zip`(18K)。含源码+launchd/VBS 模板+飞书后台步骤+AI 接入步骤。三处 main.py 已校验一致。
  - 新电脑（Mac/Win）复现：把 `feishu-remote-setup` 文件夹放进该机 `~/.claude/skills/`，对 Claude 说「配置飞书远程操控」。

## 配置时踩过的坑（重配必看）
1. 企业自建应用**必须实名认证**，否则飞书完全不推事件（连接正常但发消息无反应）。
2. 收单聊消息**必须开 `im:message.p2p_msg:readonly`**（只开 im:message+群@权限收不到单聊），开通后要重新发布版本。

## 读档提示
用户说「读档 CCX 项目」时：先读本文件。项目已完成，剩下用户自己填 DeepSeek key 开 AI。
