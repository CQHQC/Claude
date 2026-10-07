#!/bin/bash
# 双击即可启动「双路 9g 舵机上位机」
# (在 Finder 里双击本文件; 首次会弹出运行确认)

# 切到本脚本所在目录(项目根目录)
cd "$(dirname "$0")"

# 确保能找到 uv (Finder 双击时 PATH 较精简, 这里显式补上)
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "正在启动舵机上位机..."
uv run --with pyserial python gui/servo_gui.py

# 若出错, 停住窗口好让你看到报错信息
status=$?
if [ $status -ne 0 ]; then
  echo ""
  echo "启动失败 (退出码 $status)。按回车关闭此窗口。"
  read
fi
