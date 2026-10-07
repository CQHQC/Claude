---
name: feishu-remote-setup
description: 在一台电脑(macOS 或 Windows)上搭建「飞书远程操控电脑」(CCX 项目)——用手机给飞书机器人发指令，电脑执行开软件/发文件/截屏/系统控制/自由 shell。当用户说「配置飞书远程操控」「搭 CCX 项目」「在这台电脑装飞书机器人控制」或在新电脑上要复现这套时使用。技术栈：飞书 lark-oapi 长连接(WebSocket)，无需公网 IP，电脑端无需登录飞书。代码 main.py 已跨平台，自动适配 macOS / Windows。
---

# 飞书远程操控电脑（CCX 项目）一键搭建 · 跨平台

帮用户在**当前这台电脑**(macOS 或 Windows)上把整套「手机→飞书机器人→操控电脑」跑起来。
代码已随本 skill 打包在 `assets/`，且 `main.py` **已跨平台**(运行时自动识别 Mac/Windows 走不同系统命令)。你只需复制出去、装依赖、引导用户做飞书后台配置、填凭证、跑起来、配开机自启。

**先判断当前系统**：用环境信息或 `uname`/`ver` 确认是 macOS 还是 Windows，后面「运行」「自启」两步按系统走。**飞书后台配置两边完全一样。**

## 架构（先跟用户对齐）
- 渠道：飞书 `lark-oapi` **长连接(WebSocket)模式** → 电脑主动外连飞书，**无需公网 IP / 端口转发 / 内网穿透**，**电脑端不用安装或登录飞书**（只靠 app_id/app_secret 连接）。
- 能力：`/open` 开软件或网址、`/get` 发文件回手机、`/shot` 截屏、`/lock /sleep /shutdown /vol` 系统控制、以及**自由 shell**（直接发文字当命令执行；Mac 走 zsh/bash，Windows 走 cmd）。
- 安全：**open_id 白名单**是唯一防线（因为开了自由 shell）。非白名单消息一律忽略。提醒用户给飞书账号本身设好锁屏/密码。

## ⚠️ 两个必栽的坑（务必提前告诉用户，这是首次部署卡 1 小时的根因）
1. **企业自建应用必须先实名认证**。没实名时：长连接能连上、心跳正常，但飞书**完全不推送任何消息事件**，表现为「发消息机器人无反应」。去飞书开放平台完成开发者/企业实名认证后才会推事件。
2. **必须开通 `im:message.p2p_msg:readonly`（读取用户发给机器人的单聊消息）**。只开 `im:message` + 群聊@权限的话，机器人**只能收到群里@它的消息，收不到单聊发的文字**。开通后**必须重新发布版本**才生效。

## 第 1 步：装好 uv（Python 包管理）
- **macOS**：通常已装。`which uv`，没有则 `curl -LsSf https://astral.sh/uv/install.sh | sh`。
- **Windows**：PowerShell 跑 `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`，重开终端后 `uv --version` 验证。

## 第 2 步：落地代码
1. 选工作目录（macOS 默认 `~/feishu-remote`；Windows 默认 `%USERPROFILE%\feishu-remote`，或问用户）。
2. 把本 skill `assets/` 下的 `main.py`、`pyproject.toml`、`config.example.toml`、`README.md` 复制过去。
3. 在工作目录跑 `uv sync` 建好虚拟环境。
4. 复制配置模板为 `config.toml`（白名单先留空 `[]`）。

## 第 3 步：引导用户做飞书后台配置（用户亲自操作，你无法代做，两平台相同）
按顺序，逐步引导、让用户每步回报或截图：
1. https://open.feishu.cn/app 登录 → 创建**企业自建应用**（无团队会让建个人团队，免费）。
2. **完成实名认证**（见坑 1）。
3. **添加应用能力 → 机器人**，启用。
4. **权限管理**开通这 4 个权限：
   - `im:message`（获取与发送单聊、群组消息）
   - `im:message:send_as_bot`（以应用身份发消息）
   - `im:message.p2p_msg:readonly`（读取用户发给机器人的单聊消息）← **关键，别漏**（坑 2）
   - `im:resource`（上传图片/文件，截屏和发文件要用）
5. **事件与回调 → 订阅方式**：选「**使用长连接接收事件**」并**保存**。
6. **添加事件**：`im.message.receive_v1`（接收消息）。
7. **创建版本并发布**（自用选仅自己可见，一般秒过）。每次改权限/事件都要重新发布。
8. 到「**凭证与基础信息**」拿 `App ID`(cli_ 开头) 和 `App Secret`。

## 第 4 步：填凭证并首次运行
1. 把 App ID / App Secret 填进 `config.toml`。
2. 后台运行 `uv run main.py`（建议用后台任务，便于读日志）。看到「✅ 已连接飞书」即成功。
3. 让用户用手机飞书搜到机器人、**单聊发任意一句**。机器人会回复其 `open_id`。
   - 若无反应：检查坑 1（实名）和坑 2（p2p 权限 + 已重新发布）。
   - 排查技巧：把 `main.py` 里 `log_level` 临时改 `lark.LogLevel.DEBUG`，能看到原始事件帧，分清「飞书没推」还是「代码没处理」。也可用 app 凭证调 `POST https://open.feishu.cn/open-apis/im/v1/messages` 主动发消息验证「发送」链路是否通。
4. 把拿到的 `open_id` 填进 `config.toml` 的 `allowed_open_ids`，重启程序。
5. 让用户发 `/help` 验证——回完整指令列表即全部跑通。

## 第 5 步：配开机自启

### macOS（launchd）
1. 取 `assets/com.ccx.feishu-remote.plist.template`，替换占位符：
   - `__UV_PATH__` → `which uv` 的绝对路径（如 `/Users/<用户>/.local/bin/uv`）
   - `__UV_DIR__`  → 上面 uv 所在目录
   - `__WORKDIR__` → 第 2 步的工作目录绝对路径
2. 写到 `~/Library/LaunchAgents/com.ccx.feishu-remote.plist`。
3. 先停掉手动/会话里跑的实例（避免两个连接重复执行命令），再 `launchctl load ~/Library/LaunchAgents/com.ccx.feishu-remote.plist`。
4. `launchctl list | grep feishu-remote` 确认在跑；看 `launchd.log` 确认已连接。
5. 管理：停 `launchctl unload <plist>`；改代码后重启 = 先 unload 再 load。

### Windows（启动文件夹 · 推荐，最简单）
1. 取 `assets/feishu-remote-win-autostart.vbs.template`，替换：
   - `__UV_PATH__` → uv.exe 绝对路径（`where uv`，常见 `C:\Users\<用户>\.local\bin\uv.exe`）
   - `__WORKDIR__` → 工作目录绝对路径（注意 Windows 路径反斜杠）
2. 存成 `feishu-remote.vbs`。
3. `Win+R` 输入 `shell:startup` 回车，把该 .vbs 放进打开的「启动」文件夹。VBS 用隐藏窗口启动，开机/登录即自动运行、无黑窗。
4. 立即测试：双击该 .vbs（或注销重登），看工作目录是否产生连接、手机发 `/help` 是否有响应。
   - 备选（更稳，开机即起不必登录）：用任务计划程序
     `schtasks /create /tn FeishuRemote /tr "\"<uv绝对路径>\" run python main.py" /sc onlogon /rl highest` （需在工作目录或脚本里 cd 过去）。
5. 管理：删启动文件夹里的 .vbs 即停自启；任务结束可在「任务管理器」结束 python 进程。

## 第 6 步：接入 AI（可选，让机器人能听懂人话）
默认接 **DeepSeek**（国内直连、便宜、支持 function calling；用 `openai` SDK 指向 DeepSeek 即可，已是依赖）。不接也能用——斜杠指令始终可用。
1. 让用户去 https://platform.deepseek.com 创建 API key。
2. 填进 `config.toml`：`ai_api_key = "sk-..."`（`ai_base_url` 默认 `https://api.deepseek.com`、`ai_model` 默认 `deepseek-chat`，一般不用改）。
3. 重启程序。之后**非斜杠的自然语言**会交给模型：它能答问，或调用工具（run_command/open_target/screenshot/send_file/system_control）操作电脑；带每会话最近 12 条历史，支持指代。
4. 想换其它 OpenAI 兼容模型（通义/Kimi/本地 ollama），改 `ai_base_url` + `ai_model`。
- 实现要点（已写好在 main.py，复现时无需重写）：OpenAI 格式 tools（`{"type":"function","function":{...}}`）+ `chat.completions.create` 工具循环（读 `choices[0].message.tool_calls`，回填 `role:"assistant"`(带 tool_calls) 和 `role:"tool"`(tool_call_id) 消息）。

## 平台差异提醒
- **/shot 截屏**：macOS 首次触发隐私授权（系统设置 → 隐私与安全性 → 屏幕录制）；Windows 用内置 PowerShell 截图，无需额外依赖，但要有桌面会话（锁屏状态截不到）。
- **/vol 音量**：macOS 原生支持；**Windows 无内置绝对音量命令**，需下载 `nircmd.exe` 放进 PATH 才能用 `/vol`，否则程序会提示。其余指令 Windows 全部内置可用。
- **自由 shell**：Windows 下发的是 cmd 命令（如 `dir`、`tasklist`），不是 bash。

## 收尾
- 提醒：`config.toml` 含 app_secret，别提交到公开仓库。
- 多台电脑可共用同一个飞书应用（同 app_id/secret，白名单各自加），也可各建一个。
- 跑通后建议更新记忆/存档，标记该机已部署。
