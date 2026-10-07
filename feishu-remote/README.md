# 飞书远程操控电脑

人不在电脑旁时，用手机给飞书机器人发消息，让电脑自己执行：**开软件 / 发文件回手机 / 截屏 / 系统控制 / 自由 shell**。

采用飞书**长连接（WebSocket）模式**——电脑主动外连飞书，**无需公网 IP、无需路由器端口转发、无需内网穿透**，家里/公司网络都能用。

---

## 一、在飞书后台创建应用（约 5 分钟，一次性）

1. 打开飞书开放平台 https://open.feishu.cn/app ，用你的飞书账号登录
2. 点「创建企业自建应用」，填个名字（如「我的电脑管家」），创建
3. 进入应用后：
   - **凭证与基础信息**：记下 `App ID` 和 `App Secret`（填到 config.toml）
   - **添加应用能力 → 机器人**：点「添加」，启用机器人
   - **权限管理**：搜索并开通以下权限：
     - `im:message`（获取与发送单聊、群组消息）
     - `im:message:send_as_bot`（以应用的身份发消息）
     - `im:message.p2p_msg:readonly`（读取用户发给机器人的**单聊**消息）← **必须！** 缺它机器人收不到你单聊发的消息，只能收群里@
     - `im:resource`（上传图片/文件）
   - **事件与回调 → 订阅方式**：选择「**使用长连接接收事件**」
   - **事件与回调 → 添加事件**：添加 `接收消息 im.message.receive_v1`
4. 右上角「**版本管理与发布 → 创建版本**」，提交并发布（个人自用选「仅自己可见」即可，一般自动通过）

> 全程免费。企业自建应用如果你没有团队，飞书会让你创建一个个人团队，正常操作即可。

---

## 二、本地运行

本机用 uv 管理 Python：

```bash
cd /Users/caiqianhu/Documents/Claudefile/feishu-remote

# 填配置
cp config.example.toml config.toml
# 编辑 config.toml，填入 app_id 和 app_secret

# 启动
uv run main.py
```

第一次启动后，**用手机飞书搜到你的机器人，给它发任意一句话**，它会回复你的 `open_id`。
把这个 open_id 填进 `config.toml` 的 `allowed_open_ids`，重启程序——之后只有你能指挥它。

```toml
allowed_open_ids = ["ou_xxxxxxxxxxxxxxxxxxxx"]
```

---

## 三、手机端怎么用

直接给机器人发消息：

| 发送内容 | 效果 |
|---|---|
| `/help` | 查看所有指令 |
| `/open 微信` | 打开「微信」App |
| `/open https://baidu.com` | 用默认浏览器打开网址 |
| `/get ~/Desktop/周报.xlsx` | 把这个文件发到手机，可直接下载 |
| `/shot` | 截当前屏幕发回手机 |
| `/lock` | 锁屏 |
| `/sleep` | 睡眠 |
| `/vol 30` | 音量调到 30 |
| `ls ~/Downloads` | 直接当 shell 命令执行，返回结果 |

### 接入 AI 后（可选，见下）

填了 DeepSeek key 后，**非斜杠的自然语言**会交给大模型：它能回答问题，也能听懂人话去操作电脑。

| 发送内容 | 效果 |
|---|---|
| `你是谁` / `北京天气怎么查` | 当成提问，AI 直接回答 |
| `帮我打开微信` | AI 调用工具打开微信 |
| `桌面上有哪些文件` | AI 跑命令列出并总结 |
| `截个屏给我看看` | AI 截屏发到手机 |

斜杠指令始终走快速、零成本的直接路径（不消耗 AI 额度）。

---

## 三点五、接入 AI（可选）

默认用 **DeepSeek**（国内直连、便宜、支持工具调用）：

1. 去 https://platform.deepseek.com 注册，创建一个 API key。
2. 填进 `config.toml` 的 `ai_api_key`，重启程序。
3. 之后给机器人发「人话」即可，它会自己判断是回答还是操作电脑。

```toml
ai_api_key = "sk-xxxxxxxx"
ai_base_url = "https://api.deepseek.com"
ai_model = "deepseek-chat"
```

想换其它 OpenAI 兼容模型（通义千问 / Kimi / 本地 ollama 等），改 `ai_base_url` + `ai_model` 即可。留空 `ai_api_key` 则不启用 AI，自然语言按 shell 命令执行。

---

## 四、安全说明

- 已开启**自由 shell**：发什么命令电脑就执行什么，威力大也意味着风险大。
- 唯一防线是 **open_id 白名单**：非白名单账号发的消息一律忽略。请确保你的飞书账号本身有锁屏/指纹/密码保护。
- 截屏、控制系统首次会触发 macOS 隐私授权弹窗（屏幕录制、辅助功能），需在「系统设置 → 隐私与安全性」里给运行程序的终端授权。

---

## 五、让它开机自启 / 常驻后台（可选）

最简单：终端里 `nohup uv run main.py &`。
要更稳的开机自启（macOS launchd 方案），跟我说一声，我再给你配。
