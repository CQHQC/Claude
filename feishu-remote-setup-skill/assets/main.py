#!/usr/bin/env python3
"""
飞书远程操控电脑 —— 长连接模式，无需公网 IP。跨平台：macOS / Windows 自动适配。

用手机给飞书机器人发消息：
- 斜杠指令（/open、/shot…）：快速、零成本，直接执行。
- 其它自然语言：交给 Claude 理解 —— 回答你的问题，或调用工具操作这台电脑。
"""
import io
import json
import os
import platform
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateFileRequest,
    CreateFileRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
    CreateMessageRequest,
    CreateMessageRequestBody,
    P2ImMessageReceiveV1,
)

# ---------- 平台 ----------
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
TMP = Path(tempfile.gettempdir())

# ---------- 配置 ----------
CONFIG_PATH = Path(__file__).parent / "config.toml"
if not CONFIG_PATH.exists():
    sys.exit("❌ 没找到 config.toml，请先 `cp config.example.toml config.toml` 并填写凭证。")

with open(CONFIG_PATH, "rb") as f:
    CFG = tomllib.load(f)

APP_ID = CFG["app_id"]
APP_SECRET = CFG["app_secret"]
ALLOWED = set(CFG.get("allowed_open_ids") or [])
WORK_DIR = os.path.expanduser(CFG.get("work_dir", "~"))
SHELL_TIMEOUT = int(CFG.get("shell_timeout", 60))

# AI（可选）：填了 ai_api_key 才启用，非斜杠消息交给大模型（默认 DeepSeek，OpenAI 兼容接口）。
AI_API_KEY = (CFG.get("ai_api_key") or "").strip()
AI_BASE_URL = CFG.get("ai_base_url", "https://api.deepseek.com")
AI_MODEL = CFG.get("ai_model", "deepseek-chat")
AI_ENABLED = bool(AI_API_KEY)

# 用于「主动发消息」的客户端（收消息走下面的 ws 客户端）
client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).build()

# 大模型客户端（OpenAI 兼容；DeepSeek 等国内模型直连，按需初始化）
_ai = None
if AI_ENABLED:
    try:
        from openai import OpenAI
        _ai = OpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ 初始化 AI 失败，将退回纯指令模式: {e}", file=sys.stderr)
        AI_ENABLED = False

# 每个会话保留最近若干轮对话（让「打开它」这类指代能work）
_history: dict[str, list] = {}
HISTORY_TURNS = 12  # 保留最近 N 条 user/assistant 消息

# 简单去重：飞书可能重发同一事件
_seen_msg_ids: set[str] = set()

HELP_BASE = """📱 可用指令（直接发文字即可）：

/help           查看本帮助
/whoami         回复你的 open_id 和 chat_id
/open <目标>    打开 App / 网址 / 文件，如：/open 微信、/open https://baidu.com
/get <路径>     把电脑上的文件发到手机，如：/get ~/Desktop/周报.xlsx
/shot           截屏并发回手机
/lock           锁屏
/sleep          电脑睡眠
/shutdown       关机
/vol <0-100>    设置音量，如：/vol 30
/sh <命令>      执行 shell 命令"""

HELP = HELP_BASE + (
    "\n\n💬 直接发其它文字 = 交给 AI 理解：可以问它问题，或用人话让它操作电脑"
    "（如「打开微信」「现在几点」「桌面有什么文件」）。"
    if AI_ENABLED else
    "\n\n直接发其它文字 = 当作 shell 命令执行（已开启自由 shell 模式）。"
)


# ---------- 发送辅助 ----------
def send_text(chat_id: str, text: str) -> None:
    # 飞书单条文本上限较大，这里截断超长输出
    if len(text) > 8000:
        text = text[:8000] + "\n…（输出过长已截断）"
    if not text.strip():
        text = "（无输出）"
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id).msg_type("text") \
        .content(json.dumps({"text": text})).build()
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id").request_body(body).build()
    resp = client.im.v1.message.create(req)
    if not resp.success():
        print(f"[send_text] 失败: {resp.code} {resp.msg}", file=sys.stderr)


def send_file(chat_id: str, path: Path) -> None:
    file_type = "stream"
    suffix = path.suffix.lower().lstrip(".")
    if suffix in ("opus", "mp4", "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx"):
        file_type = suffix if suffix != "docx" else "doc"
    with open(path, "rb") as fh:
        up = CreateFileRequest.builder().request_body(
            CreateFileRequestBody.builder()
            .file_type(file_type).file_name(path.name).file(fh).build()
        ).build()
        resp = client.im.v1.file.create(up)
    if not resp.success():
        send_text(chat_id, f"❌ 上传文件失败: {resp.code} {resp.msg}")
        return
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id).msg_type("file") \
        .content(json.dumps({"file_key": resp.data.file_key})).build()
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id").request_body(body).build()
    client.im.v1.message.create(req)


def send_image(chat_id: str, data: bytes) -> None:
    up = CreateImageRequest.builder().request_body(
        CreateImageRequestBody.builder()
        .image_type("message").image(io.BytesIO(data)).build()
    ).build()
    resp = client.im.v1.image.create(up)
    if not resp.success():
        send_text(chat_id, f"❌ 上传图片失败: {resp.code} {resp.msg}")
        return
    body = CreateMessageRequestBody.builder() \
        .receive_id(chat_id).msg_type("image") \
        .content(json.dumps({"image_key": resp.data.image_key})).build()
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id").request_body(body).build()
    client.im.v1.message.create(req)


# ---------- 命令执行 ----------
def run_shell(cmd: str) -> str:
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=WORK_DIR, timeout=SHELL_TIMEOUT,
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        out = (p.stdout or "") + (p.stderr or "")
        prefix = "" if p.returncode == 0 else f"[退出码 {p.returncode}]\n"
        return prefix + out
    except subprocess.TimeoutExpired:
        return f"⏱️ 命令超过 {SHELL_TIMEOUT}s 未结束，已终止。"
    except Exception as e:  # noqa: BLE001
        return f"❌ 执行出错: {e}"


# ---------- 平台相关的系统操作 ----------
def sys_open(target: str) -> str:
    """打开 App / 网址 / 文件。"""
    is_url = target.startswith(("http://", "https://"))
    expanded = os.path.expanduser(target)
    if IS_WIN:
        if is_url or os.path.exists(expanded):
            try:
                os.startfile(expanded if os.path.exists(expanded) else target)  # type: ignore[attr-defined]
                return "✅ 已打开"
            except Exception as e:  # noqa: BLE001
                return f"❌ 打开失败: {e}"
        return run_shell(f'start "" "{target}"') or f"✅ 已尝试打开 {target}"
    if is_url or os.path.exists(expanded):
        return run_shell(f'open "{expanded}"') or "✅ 已打开"
    return run_shell(f'open -a "{target}"') or f"✅ 已打开 {target}"


def sys_screenshot() -> bytes | None:
    """截屏，返回 PNG 字节；失败返回 None。"""
    out = TMP / "feishu_remote_shot.png"
    out.unlink(missing_ok=True)
    if IS_WIN:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap($b.Width,$b.Height);"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f"$bmp.Save('{out}');"
        )
        run_shell(f'powershell -NoProfile -Command "{ps}"')
    else:
        run_shell(f'screencapture -x "{out}"')
    return out.read_bytes() if out.is_file() else None


def sys_lock() -> str:
    if IS_WIN:
        run_shell("rundll32.exe user32.dll,LockWorkStation")
    else:
        run_shell('/System/Library/CoreServices/"Menu Extras"/User.menu/Contents/Resources/CGSession -suspend')
    return "🔒 已锁屏"


def sys_sleep() -> None:
    if IS_WIN:
        run_shell("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    else:
        run_shell("pmset sleepnow")


def sys_shutdown() -> None:
    if IS_WIN:
        run_shell("shutdown /s /t 0")
    else:
        run_shell("osascript -e 'tell app \"System Events\" to shut down'")


def sys_volume(level: int) -> str:
    if IS_WIN:
        from shutil import which
        if which("nircmd"):
            run_shell(f"nircmd setsysvolume {int(level / 100 * 65535)}")
            return f"🔊 音量已设为 {level}"
        return ("⚠️ Windows 端设置绝对音量需要 nircmd。"
                "可下载 nircmd.exe 放到 PATH，或用 shell 命令。")
    run_shell(f"osascript -e 'set volume output volume {level}'")
    return f"🔊 音量已设为 {level}"


# ---------- AI（DeepSeek / OpenAI 兼容 function calling）----------
AI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": ("在用户电脑上执行一条 shell 命令并返回输出。"
                            + ("Windows 用 cmd（如 dir、tasklist）。" if IS_WIN else "macOS 用 bash/zsh（如 ls、cat）。")
                            + "用于查询文件、运行程序、获取系统信息等。"),
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "要执行的命令"}},
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_target",
            "description": "打开一个 App、网址或文件。如「微信」「https://baidu.com」「~/Desktop/a.pdf」。",
            "parameters": {
                "type": "object",
                "properties": {"target": {"type": "string", "description": "App 名 / 网址 / 文件路径"}},
                "required": ["target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "screenshot",
            "description": "截取当前屏幕并直接发到用户手机。用户想看屏幕、确认画面时调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": "把电脑上的一个文件发到用户手机（用户可下载）。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "文件绝对/相对路径，支持 ~"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "system_control",
            "description": "系统控制：锁屏 / 睡眠 / 关机 / 设置音量。",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["lock", "sleep", "shutdown", "volume"]},
                    "level": {"type": "integer", "description": "action=volume 时的音量 0-100"},
                },
                "required": ["action"],
            },
        },
    },
]


def _ai_system_prompt() -> str:
    osname = "Windows" if IS_WIN else ("macOS" if IS_MAC else platform.system())
    return (
        f"你是运行在用户这台 {osname} 电脑上的私人助手，用户通过手机飞书和你对话。\n"
        "你有两种事可做：(1) 直接回答用户的任何问题；(2) 调用工具操作这台电脑。\n"
        "规则：\n"
        "- 用中文、简洁回答（用户在手机上看，别长篇大论）。\n"
        "- 需要操作电脑时调用对应工具；纯聊天或知识问答就直接回答，不要调用工具。\n"
        "- 截屏、发文件这类工具会把内容直接发到用户手机，你只需在调用后简短说明即可。\n"
        "- 只输出最终答复，不要输出思考过程或自言自语。"
    )


def _exec_ai_tool(chat_id: str, name: str, args: dict) -> str:
    """执行模型请求的工具，返回给模型的文字结果（媒体已直接发给用户）。"""
    try:
        if name == "run_command":
            return run_shell(args.get("command", "")) or "（无输出）"
        if name == "open_target":
            return sys_open(args.get("target", ""))
        if name == "screenshot":
            data = sys_screenshot()
            if data:
                send_image(chat_id, data)
                return "[已把当前屏幕截图发到用户手机]"
            return "截屏失败（可能无桌面会话或需授权屏幕录制）"
        if name == "send_file":
            p = Path(os.path.expanduser(args.get("path", "")))
            if not p.is_file():
                return f"文件不存在: {p}"
            send_file(chat_id, p)
            return f"[已把文件 {p.name} 发到用户手机]"
        if name == "system_control":
            action = args.get("action")
            if action == "lock":
                return sys_lock()
            if action == "sleep":
                sys_sleep()
                return "已让电脑睡眠"
            if action == "shutdown":
                sys_shutdown()
                return "正在关机"
            if action == "volume":
                return sys_volume(int(args.get("level", 50)))
            return f"未知系统操作: {action}"
        return f"未知工具: {name}"
    except Exception as e:  # noqa: BLE001
        return f"工具执行出错: {e}"


def ai_reply(chat_id: str, text: str) -> None:
    """把用户消息交给大模型（DeepSeek），跑 tool-use 循环，最终把回复发给用户。"""
    history = _history.setdefault(chat_id, [])
    # OpenAI 格式：system 放在 messages 首位
    messages = [{"role": "system", "content": _ai_system_prompt()}]
    messages += history
    messages.append({"role": "user", "content": text})
    final_text = ""
    try:
        for _ in range(6):  # 最多 6 轮工具调用，防止死循环
            resp = _ai.chat.completions.create(
                model=AI_MODEL,
                max_tokens=4096,
                tools=AI_TOOLS,
                messages=messages,
            )
            choice = resp.choices[0].message
            tool_calls = choice.tool_calls or []

            # 回填 assistant 这一轮（含可能的 tool_calls）
            assistant_msg = {"role": "assistant", "content": choice.content or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ]
            messages.append(assistant_msg)

            if tool_calls:
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    result = _exec_ai_tool(chat_id, tc.function.name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            final_text = (choice.content or "").strip()
            break
        else:
            final_text = "（工具调用过多，已停止）"
    except Exception as e:  # noqa: BLE001
        send_text(chat_id, f"❌ AI 处理出错: {e}")
        return

    if final_text:
        send_text(chat_id, final_text)

    # 只把纯文本对话存进历史（工具块不持久化，控制体积）
    history.append({"role": "user", "content": text})
    history.append({"role": "assistant", "content": final_text or "（已执行操作）"})
    if len(history) > HISTORY_TURNS:
        del history[: len(history) - HISTORY_TURNS]


def handle_command(chat_id: str, text: str) -> None:
    text = text.strip()
    if not text:
        return

    # 斜杠指令（快速、零成本路径）
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd == "/help":
            send_text(chat_id, HELP)
        elif cmd == "/whoami":
            send_text(chat_id, f"chat_id: {chat_id}")  # open_id 在 dispatch 里已回复
        elif cmd == "/open":
            if not arg:
                send_text(chat_id, "用法：/open 微信  或  /open https://...")
                return
            send_text(chat_id, sys_open(arg))
        elif cmd == "/get":
            if not arg:
                send_text(chat_id, "用法：/get ~/Desktop/文件.pdf")
                return
            path = Path(os.path.expanduser(arg))
            if not path.is_file():
                send_text(chat_id, f"❌ 文件不存在: {path}")
                return
            send_text(chat_id, f"📤 正在发送 {path.name} …")
            send_file(chat_id, path)
        elif cmd == "/shot":
            data = sys_screenshot()
            if data:
                send_image(chat_id, data)
            else:
                hint = ("（Windows：确认有桌面会话）" if IS_WIN
                        else "（可能需要在『系统设置→隐私与安全性→屏幕录制』里授权）")
                send_text(chat_id, f"❌ 截屏失败{hint}。")
        elif cmd == "/lock":
            send_text(chat_id, sys_lock())
        elif cmd == "/sleep":
            send_text(chat_id, "😴 即将睡眠")
            sys_sleep()
        elif cmd == "/shutdown":
            send_text(chat_id, "⏻ 正在关机…")
            sys_shutdown()
        elif cmd == "/vol":
            if not arg.isdigit():
                send_text(chat_id, "用法：/vol 30")
                return
            send_text(chat_id, sys_volume(int(arg)))
        elif cmd == "/sh":
            send_text(chat_id, run_shell(arg))
        else:
            send_text(chat_id, f"未知指令 {cmd}\n\n{HELP}")
        return

    # 非斜杠：有 AI 就交给 Claude，否则退回自由 shell
    if AI_ENABLED:
        ai_reply(chat_id, text)
    else:
        send_text(chat_id, run_shell(text))


# ---------- 事件回调 ----------
def on_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    sender = data.event.sender.sender_id
    open_id = sender.open_id
    chat_id = msg.chat_id

    # 去重
    if msg.message_id in _seen_msg_ids:
        return
    _seen_msg_ids.add(msg.message_id)
    if len(_seen_msg_ids) > 1000:
        _seen_msg_ids.clear()

    # 只处理文本消息
    if msg.message_type != "text":
        return
    try:
        text = json.loads(msg.content).get("text", "").strip()
    except (json.JSONDecodeError, AttributeError):
        return
    # 去掉群里 @机器人 的占位符
    text = text.replace("@_user_1", "").strip()

    # 白名单校验
    if not ALLOWED:
        print(f"⚠️  白名单为空。发消息者 open_id = {open_id}")
        send_text(
            chat_id,
            f"👋 你的 open_id 是：\n{open_id}\n\n请把它填入 config.toml 的 "
            f"allowed_open_ids，然后重启程序即可开始使用。",
        )
        return
    if open_id not in ALLOWED:
        print(f"⛔ 拒绝非白名单用户: {open_id}")
        return

    print(f"▶️  执行: {text!r}")
    handle_command(chat_id, text)


def main() -> None:
    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws = lark.ws.Client(
        APP_ID, APP_SECRET, event_handler=handler, log_level=lark.LogLevel.INFO
    )
    mode = "AI+指令" if AI_ENABLED else "纯指令"
    print(f"✅ 已连接飞书（{platform.system()} · {mode}），等待手机指令…（Ctrl+C 退出）")
    ws.start()


if __name__ == "__main__":
    main()
