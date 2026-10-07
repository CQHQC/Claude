#!/usr/bin/env python3
"""
ESP32-CAM 视频流上位机  (macOS / Windows / Linux)
----------------------------------------------------------
拉取 ESP32-CAM 的 MJPEG 视频流并显示, 可一键截图保存。

前提: ESP32-CAM 已烧录官方 CameraWebServer 例程并连上 WiFi,
      串口监视器里看到它的 IP (如 192.168.1.50)。

运行:
    uv run --with pillow --with requests python gui/esp32cam_viewer.py

视频流地址通常是:  http://<IP>:81/stream
单帧抓拍地址是:    http://<IP>/capture
"""

import io
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import requests
from PIL import Image, ImageTk


class CamViewer:
    def __init__(self, root):
        self.root = root
        self.running = False
        self.thread = None
        self.latest_jpeg = None          # 最近一帧的 JPEG 字节 (常驻, 供显示和截图)
        self.dirty = False               # 有新帧待显示
        self.lock = threading.Lock()
        self.frame_count = 0

        root.title("ESP32-CAM 视频上位机")
        root.resizable(True, True)
        self._build_ui()
        self._poll_display()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Label(top, text="视频流地址:").pack(side="left")
        self.url_var = tk.StringVar(value="http://192.168.1.50:81/stream")
        ttk.Entry(top, textvariable=self.url_var, width=36).pack(side="left", padx=6)
        self.btn = ttk.Button(top, text="连接", command=self.toggle)
        self.btn.pack(side="left", padx=4)
        ttk.Button(top, text="截图保存", command=self.snapshot).pack(side="left", padx=4)

        self.video = ttk.Label(self.root, text="(未连接)\n填入 ESP32-CAM 的流地址后点连接",
                               anchor="center", background="#101820", foreground="#9aa")
        self.video.pack(fill="both", expand=True, padx=8, pady=6)

        self.status = tk.StringVar(value="未连接")
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w").pack(fill="x", padx=8, pady=(0, 8))

    def toggle(self):
        self.stop() if self.running else self.start()

    def start(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("提示", "请填写视频流地址")
            return
        self.running = True
        self.thread = threading.Thread(target=self._reader, args=(url,), daemon=True)
        self.thread.start()
        self.btn.config(text="断开")
        self.status.set(f"连接中... {url}")

    def stop(self):
        self.running = False
        self.btn.config(text="连接")
        self.status.set("已断开")

    def _reader(self, url):
        """后台线程: 持续从 MJPEG 流中切出一帧帧 JPEG。"""
        try:
            r = requests.get(url, stream=True, timeout=5)
        except requests.RequestException as e:
            self.status.set(f"连接失败: {e}")
            self.running = False
            self.root.after(0, lambda: self.btn.config(text="连接"))
            return

        buf = b""
        for chunk in r.iter_content(chunk_size=4096):
            if not self.running:
                break
            buf += chunk
            # MJPEG: 每帧以 0xFFD8 开头, 0xFFD9 结尾
            start = buf.find(b"\xff\xd8")
            end = buf.find(b"\xff\xd9", start + 2)
            if start != -1 and end != -1:
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]
                with self.lock:
                    self.latest_jpeg = jpg
                    self.dirty = True
        try:
            r.close()
        except Exception:
            pass

    def _poll_display(self):
        """主线程: 定时把最新一帧解码显示。"""
        jpg = None
        with self.lock:
            if self.dirty and self.latest_jpeg is not None:
                jpg = self.latest_jpeg
                self.dirty = False
        if jpg is not None:
            try:
                img = Image.open(io.BytesIO(jpg))
                photo = ImageTk.PhotoImage(img)
                self.video.config(image=photo, text="")
                self.video.image = photo      # 防止被回收
                self.frame_count += 1
                self.status.set(f"播放中  {img.width}x{img.height}  已收 {self.frame_count} 帧")
            except Exception:
                pass
        self.root.after(30, self._poll_display)

    def snapshot(self):
        with self.lock:
            jpg = self.latest_jpeg
        if jpg is None:
            messagebox.showinfo("提示", "还没有画面，连接并出图后再截图")
            return
        name = f"snapshot_{int(time.time())}.jpg"
        try:
            with open(name, "wb") as f:
                f.write(jpg)
            self.status.set(f"已保存截图: {name}")
        except OSError as e:
            messagebox.showerror("保存失败", str(e))

    def on_close(self):
        self.running = False
        self.root.destroy()


def main():
    root = tk.Tk()
    root.geometry("700x560")
    CamViewer(root)
    root.mainloop()


if __name__ == "__main__":
    main()
