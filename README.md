# 六路舵机控制 — Arduino UNO + PCA9685

从这台 Mac 用图形界面控制 6 个舵机（3×20kg 大扭力 + 3×MG90S）。

## ⚠️ 供电（最关键，先看这条）

3 个 20kg 舵机非常耗电（每个堵转 2~3A），6 个一起峰值可达 **8~10A**：

- ✅ 必须单独配一个 **5~6V、大电流（≥10A）开关电源**，接 PCA9685 的 **V+ 螺丝端子**
- ❌ 不能用 UNO 的 5V（USB 顶多 0.5A，会拉垮重启）
- ❌ 不能用 12V 电源板的 5V 输出（电流不够）
- ❌ **绝不能给 V+ 接 12V**（瞬间烧舵机）
- 电压取 **6V** 最佳；大电源 GND 必须与 UNO **共地**，V+ 走粗线

## 通道分配
- 通道 **0 / 1 / 2** → 20kg 大扭力舵机
- 通道 **3 / 4 / 5** → MG90S 舵机
- （只是约定，固件对所有通道一视同仁）

## 目录
- `firmware/servo_control/servo_control.ino` — Arduino 固件
- `gui/servo_gui.py` — Mac 上位机 GUI
- `docs/wiring.html` — **彩色接线图（浏览器打开看）**
- `firmware/stepper_control/`、`gui/stepper_gui.py` — 旧的步进电机方案（备用，本次不用）

## 一、接线

**双击打开 `docs/wiring.html` 看彩色接线图**，关键连接：

| 从 | 到 |
|---|---|
| UNO A5/SCL | PCA9685 SCL |
| UNO A4/SDA | PCA9685 SDA |
| UNO 5V | PCA9685 VCC（芯片逻辑电源） |
| UNO GND | PCA9685 GND |
| **独立 5~6V 大电流电源 +** | PCA9685 **V+** 端子（舵机电源） |
| 电源 GND | PCA9685 GND 端子（并与 UNO 共地） |
| 6 个舵机（棕/红/橙） | PCA9685 通道 0~5 |

⚠️ **必看**
- V+ 用**独立大电流 5~6V 电源**，**绝不能接 12V**，也别用 UNO 供电（见顶部供电说明）。
- UNO / PCA9685 / 大电源 **三者共地**。
- 舵机三色线按颜色对齐插（棕 GND / 红 V+ / 橙信号），别插反。
- PCA9685 默认 I2C 地址 `0x40`（地址跳线全开）。

## 二、烧录固件

1. Arduino IDE → 工具 → **管理库**，搜索安装 **"Adafruit PWM Servo Driver Library"**
2. 打开 `firmware/servo_control/servo_control.ino`
3. 开发板选 **Arduino UNO**，端口选 `/dev/cu.usbmodem...`，上传

## 三、运行上位机

这台 Mac 用 `uv`，直接：

```bash
cd /Users/caiqianhu/Documents/Claudefile
uv run --with pyserial python gui/servo_gui.py
```

界面：选串口 → 连接。左列是 20kg 舵机（CH0-2），右列是 MG90S（CH3-5），每个舵机一行：
- **滑块** 实时调角度（0~180°）
- **0°/90°/180°** 预设按钮
- **松开** 停止输出（舵机可手动转，省电）
- **扫动** 自动往返摆动（演示用）
- 底部 **全部居中 / 全部松开**

## 四、串口协议（115200，换行结尾）

| 指令 | 含义 |
|---|---|
| `SET,<ch>,<angle>` | 设通道 ch(0~5) 到角度 angle(0~180) |
| `OFF,<ch>` | 松开该舵机（停输出） |
| `PING` | 心跳，返回 `PONG` |

回复：`READY` / `OK` / `ERR` / `PONG`。

> 提示：不同舵机行程略有差异，0°/180° 端可能偏差或抖动。
> 要单独微调某个舵机的行程，改固件里 `servoMinUs[]` / `servoMaxUs[]` 对应那一格（索引 0~5）。
