#!/usr/bin/env python3
"""
六路舵机上位机  —  Arduino UNO + PCA9685
----------------------------------------------------------
通道 0/1/2 = 20kg 大扭力舵机, 通道 3/4/5 = MG90S 舵机。
配合 firmware/servo_control 使用。

运行:
    uv run --with pyserial python gui/servo_gui.py
"""

import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

BAUD = 115200

# (通道号, 显示名)
SERVO_GROUPS = [
    ("20kg 大扭力舵机 (通道 0-2)", [(0, "舵机 0"), (1, "舵机 1"), (2, "舵机 2")]),
    ("MG90S 舵机 (通道 3-5)",      [(3, "舵机 3"), (4, "舵机 4"), (5, "舵机 5")]),
]


class ServoPanel:
    """单个舵机的控制行（滑块 + 预设 + 松开 + 扫动）。"""

    def __init__(self, parent, app, channel, title):
        self.app = app
        self.ch = channel
        self.last_sent = None
        self.sweeping = False
        self.sweep_dir = 1

        self.frame = ttk.LabelFrame(parent, text=f"{title} (CH{channel})")

        self.angle_var = tk.IntVar(value=90)
        self.scale = ttk.Scale(self.frame, from_=0, to=180, orient="horizontal",
                               length=230)
        self.scale.set(90)
        self.scale.grid(row=0, column=0, columnspan=4, padx=6, pady=(6, 2), sticky="ew")

        self.angle_label = ttk.Label(self.frame, text="90°", width=5, anchor="e",
                                      font=("Menlo", 13))
        self.angle_label.grid(row=0, column=4, padx=(0, 6))

        for i, deg in enumerate((0, 90, 180)):
            ttk.Button(self.frame, text=f"{deg}°", width=4,
                       command=lambda d=deg: self.set_angle(d)).grid(row=1, column=i, padx=3, pady=5)
        ttk.Button(self.frame, text="松开", width=4,
                   command=self.relax).grid(row=1, column=3, padx=3, pady=5)
        self.sweep_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.frame, text="扫动", variable=self.sweep_var,
                        command=self._toggle_sweep).grid(row=1, column=4, padx=3)

        self.scale.configure(command=self._on_scale)  # 控件齐了再绑定回调

    def _on_scale(self, _v):
        ang = int(float(self.scale.get()))
        self.angle_var.set(ang)
        self.angle_label.config(text=f"{ang}°")
        self._send(ang)

    def set_angle(self, deg):
        self.sweep_var.set(False)
        self.sweeping = False
        self.scale.set(deg)

    def _send(self, ang):
        if ang == self.last_sent:
            return
        self.last_sent = ang
        self.app.send(f"SET,{self.ch},{ang}")

    def relax(self):
        self.sweep_var.set(False)
        self.sweeping = False
        self.last_sent = None
        self.app.send(f"OFF,{self.ch}")

    def _toggle_sweep(self):
        self.sweeping = self.sweep_var.get()
        if self.sweeping:
            self._sweep_step()

    def _sweep_step(self):
        if not self.sweeping or not self.app.connected():
            self.sweeping = False
            self.sweep_var.set(False)
            return
        ang = self.angle_var.get() + self.sweep_dir * 3
        if ang >= 180:
            ang, self.sweep_dir = 180, -1
        elif ang <= 0:
            ang, self.sweep_dir = 0, 1
        self.scale.set(ang)
        self.app.root.after(30, self._sweep_step)

    def set_state(self, state):
        for w in self.frame.winfo_children():
            try:
                w.configure(state=state)
            except tk.TclError:
                pass


class ServoGUI:
    def __init__(self, root):
        self.root = root
        self.ser = None
        self.reader_thread = None
        self.running = False
        self.rx_queue = queue.Queue()
        self.panels = []

        root.title("六路舵机控制器 (PCA9685)")
        root.resizable(False, False)

        self._build_ui()
        self.refresh_ports()
        self._poll_rx()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        conn = ttk.LabelFrame(self.root, text="连接")
        conn.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        ttk.Label(conn, text="串口:").grid(row=0, column=0, **pad)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var,
                                       width=30, state="readonly")
        self.port_combo.grid(row=0, column=1, **pad)
        ttk.Button(conn, text="刷新", command=self.refresh_ports).grid(row=0, column=2, **pad)
        self.connect_btn = ttk.Button(conn, text="连接", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=3, **pad)

        # 两组舵机, 左右两列
        for col, (group_title, members) in enumerate(SERVO_GROUPS):
            group = ttk.LabelFrame(self.root, text=group_title)
            group.grid(row=1, column=col, sticky="nsew", padx=8, pady=6)
            for r, (ch, title) in enumerate(members):
                panel = ServoPanel(group, self, ch, title)
                panel.frame.grid(row=r, column=0, sticky="ew", padx=6, pady=5)
                self.panels.append(panel)

        glob = ttk.Frame(self.root)
        glob.grid(row=2, column=0, columnspan=2, pady=4)
        ttk.Button(glob, text="全部居中 (90°)", command=self.center_all).grid(row=0, column=0, padx=6)
        ttk.Button(glob, text="全部松开", command=self.relax_all).grid(row=0, column=1, padx=6)

        logf = ttk.LabelFrame(self.root, text="日志")
        logf.grid(row=3, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        self.log = tk.Text(logf, width=72, height=6, state="disabled", font=("Menlo", 11))
        self.log.grid(row=0, column=0, padx=6, pady=6)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").grid(row=4, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 8))

        self._set_panels_state("disabled")

    def _set_panels_state(self, state):
        for p in self.panels:
            p.set_state(state)

    # --- 串口 ---
    def connected(self):
        return self.ser is not None and self.ser.is_open

    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        names = [p.device for p in ports]
        names.sort(key=lambda n: (("usbmodem" not in n and "usbserial" not in n), n))
        self.port_combo["values"] = names
        if names and not self.port_var.get():
            self.port_var.set(names[0])
        self._log(f"找到 {len(names)} 个串口")

    def toggle_connection(self):
        self.disconnect() if self.connected() else self.connect()

    def connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            time.sleep(2.0)
            self.running = True
            self.reader_thread = threading.Thread(target=self._reader, daemon=True)
            self.reader_thread.start()
            self.connect_btn.config(text="断开")
            self.status_var.set(f"已连接: {port} @ {BAUD}")
            self._set_panels_state("normal")
            self._log(f"已连接 {port}")
            self.send("PING")
        except serial.SerialException as e:
            messagebox.showerror("连接失败", str(e))
            self.ser = None

    def disconnect(self):
        self.running = False
        try:
            if self.connected():
                self.ser.close()
        except serial.SerialException:
            pass
        self.ser = None
        self.connect_btn.config(text="连接")
        self.status_var.set("未连接")
        self._set_panels_state("disabled")
        self._log("已断开")

    def _reader(self):
        while self.running and self.connected():
            try:
                line = self.ser.readline()
                if line:
                    self.rx_queue.put(line.decode(errors="replace").strip())
            except (serial.SerialException, OSError):
                break

    def send(self, cmd):
        if not self.connected():
            self._log("未连接，发送失败: " + cmd)
            return
        try:
            self.ser.write((cmd + "\n").encode())
            self._log("→ " + cmd)
        except serial.SerialException as e:
            self._log("发送错误: " + str(e))

    # --- 全局动作 ---
    def center_all(self):
        for p in self.panels:
            p.set_angle(90)

    def relax_all(self):
        for p in self.panels:
            p.relax()

    # --- 日志/轮询 ---
    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _poll_rx(self):
        try:
            while True:
                self._log("← " + self.rx_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(50, self._poll_rx)

    def on_close(self):
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    ServoGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
