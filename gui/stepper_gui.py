#!/usr/bin/env python3
"""
A4988 步进电机上位机 (macOS / Windows / Linux)
------------------------------------------------
基于 tkinter + pyserial，与 firmware/stepper_control 配合使用。

运行 (推荐，无需手动建虚拟环境):
    uv run --with pyserial python gui/stepper_gui.py
"""

import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial
import serial.tools.list_ports

BAUD = 115200


class StepperGUI:
    def __init__(self, root):
        self.root = root
        self.ser = None
        self.reader_thread = None
        self.running = False
        self.rx_queue = queue.Queue()

        root.title("A4988 步进电机控制器")
        root.resizable(False, False)

        self._build_ui()
        self.refresh_ports()
        self._poll_rx()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # 连接区
        conn = ttk.LabelFrame(self.root, text="连接")
        conn.grid(row=0, column=0, sticky="ew", padx=8, pady=6)

        ttk.Label(conn, text="串口:").grid(row=0, column=0, **pad)
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var,
                                       width=28, state="readonly")
        self.port_combo.grid(row=0, column=1, **pad)
        ttk.Button(conn, text="刷新", command=self.refresh_ports).grid(row=0, column=2, **pad)
        self.connect_btn = ttk.Button(conn, text="连接", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=3, **pad)

        # 控制区
        ctrl = ttk.LabelFrame(self.root, text="控制")
        ctrl.grid(row=1, column=0, sticky="ew", padx=8, pady=6)

        # 方向
        ttk.Label(ctrl, text="方向:").grid(row=0, column=0, **pad)
        self.dir_var = tk.IntVar(value=0)
        ttk.Radiobutton(ctrl, text="正转 (CW)", variable=self.dir_var, value=0,
                        command=self.send_dir).grid(row=0, column=1, sticky="w", **pad)
        ttk.Radiobutton(ctrl, text="反转 (CCW)", variable=self.dir_var, value=1,
                        command=self.send_dir).grid(row=0, column=2, sticky="w", **pad)

        # 速度 (每步间隔, 越小越快)
        ttk.Label(ctrl, text="速度:").grid(row=1, column=0, **pad)
        self.speed_var = tk.IntVar(value=1000)
        self.speed_scale = ttk.Scale(ctrl, from_=10000, to=200, orient="horizontal",
                                     length=240, command=self.on_speed_change)
        self.speed_scale.set(1000)
        self.speed_scale.grid(row=1, column=1, columnspan=2, sticky="ew", **pad)
        self.speed_label = ttk.Label(ctrl, text="1000 µs/步")
        self.speed_label.grid(row=1, column=3, **pad)

        # 步数
        ttk.Label(ctrl, text="步数:").grid(row=2, column=0, **pad)
        self.steps_var = tk.StringVar(value="200")
        ttk.Entry(ctrl, textvariable=self.steps_var, width=12).grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(ctrl, text="(整步: 200步=1圈)").grid(row=2, column=2, columnspan=2, sticky="w", **pad)

        # 动作按钮
        btns = ttk.Frame(ctrl)
        btns.grid(row=3, column=0, columnspan=4, pady=6)
        ttk.Button(btns, text="转动指定步数", command=self.move_steps).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="连续转动", command=self.run_continuous).grid(row=0, column=1, padx=4)
        ttk.Button(btns, text="停止", command=self.stop).grid(row=0, column=2, padx=4)
        ttk.Button(btns, text="使能(锁轴)", command=lambda: self.send("EN")).grid(row=0, column=3, padx=4)
        ttk.Button(btns, text="失能(松轴)", command=lambda: self.send("DIS")).grid(row=0, column=4, padx=4)

        # 日志区
        logf = ttk.LabelFrame(self.root, text="日志")
        logf.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        self.log = tk.Text(logf, width=58, height=10, state="disabled", font=("Menlo", 11))
        self.log.grid(row=0, column=0, padx=6, pady=6)

        self.status_var = tk.StringVar(value="未连接")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))

        self._set_controls_state("disabled")

    def _set_controls_state(self, state):
        # 连接后才允许操作控制区
        for child in self.root.winfo_children():
            if isinstance(child, ttk.LabelFrame) and child.cget("text") == "控制":
                for w in child.winfo_children():
                    self._recursive_state(w, state)

    def _recursive_state(self, widget, state):
        try:
            widget.configure(state=state)
        except tk.TclError:
            pass
        for c in widget.winfo_children():
            self._recursive_state(c, state)

    # ---------------- 串口 ----------------
    def refresh_ports(self):
        ports = serial.tools.list_ports.comports()
        # macOS 下优先 cu.usbmodem / cu.usbserial
        names = [p.device for p in ports]
        names.sort(key=lambda n: (("usbmodem" not in n and "usbserial" not in n), n))
        self.port_combo["values"] = names
        if names and not self.port_var.get():
            self.port_var.set(names[0])
        self._log(f"找到 {len(names)} 个串口")

    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get()
        if not port:
            messagebox.showwarning("提示", "请先选择串口")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.1)
            time.sleep(2.0)  # 等待 Arduino 复位
            self.running = True
            self.reader_thread = threading.Thread(target=self._reader, daemon=True)
            self.reader_thread.start()
            self.connect_btn.config(text="断开")
            self.status_var.set(f"已连接: {port} @ {BAUD}")
            self._set_controls_state("normal")
            self._log(f"已连接 {port}")
            self.send("PING")
        except serial.SerialException as e:
            messagebox.showerror("连接失败", str(e))
            self.ser = None

    def disconnect(self):
        self.running = False
        try:
            if self.ser and self.ser.is_open:
                self.send("STOP")
                time.sleep(0.05)
                self.ser.close()
        except serial.SerialException:
            pass
        self.ser = None
        self.connect_btn.config(text="连接")
        self.status_var.set("未连接")
        self._set_controls_state("disabled")
        self._log("已断开")

    def _reader(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline()
                if line:
                    self.rx_queue.put(line.decode(errors="replace").strip())
            except (serial.SerialException, OSError):
                break

    def send(self, cmd):
        if not (self.ser and self.ser.is_open):
            self._log("未连接，发送失败: " + cmd)
            return
        try:
            self.ser.write((cmd + "\n").encode())
            self._log("→ " + cmd)
        except serial.SerialException as e:
            self._log("发送错误: " + str(e))

    # ---------------- 动作 ----------------
    def send_dir(self):
        self.send(f"DIR,{self.dir_var.get()}")

    def on_speed_change(self, _val):
        v = int(float(self.speed_scale.get()))
        self.speed_var.set(v)
        self.speed_label.config(text=f"{v} µs/步")

    def _push_speed(self):
        self.send(f"SPD,{self.speed_var.get()}")

    def move_steps(self):
        try:
            n = int(self.steps_var.get())
            if n <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "步数必须是正整数")
            return
        self.send_dir()
        self._push_speed()
        self.send(f"MOVE,{n}")

    def run_continuous(self):
        self.send_dir()
        self._push_speed()
        self.send("RUN")

    def stop(self):
        self.send("STOP")

    # ---------------- 日志/轮询 ----------------
    def _log(self, msg):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def _poll_rx(self):
        try:
            while True:
                line = self.rx_queue.get_nowait()
                self._log("← " + line)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_rx)

    def on_close(self):
        self.disconnect()
        self.root.destroy()


def main():
    root = tk.Tk()
    StepperGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
