/*
 * 六路舵机控制固件  —  Arduino UNO + PCA9685
 * ============================================================
 * 通道分配:
 *   通道 0/1/2 -> 20kg 大扭力舵机
 *   通道 3/4/5 -> MG90S 舵机
 * (只是约定; 固件对所有通道一视同仁, 你随意插也行)
 *
 * 需要库: Arduino IDE -> 管理库 -> "Adafruit PWM Servo Driver Library"
 *
 * 接线 (详见 docs/wiring.html):
 *   PCA9685 SCL -> UNO A5      SDA -> UNO A4
 *   PCA9685 VCC -> UNO 5V      GND -> UNO GND (共地)
 *   PCA9685 V+  -> 独立 5~6V 大电流电源(+)   ★ 不可用 12V, 不可用 UNO 供电
 *   电源(-)/GND -> 与 UNO 共地
 *   6 个舵机插通道 0~5 (棕=GND 红=V+ 橙=信号)
 *
 * 串口协议 (115200, 换行结尾):
 *   SET,<ch>,<angle>   ch:0~5  angle:0~180
 *   OFF,<ch>           松开该舵机
 *   PING               -> PONG
 * 回复: READY / OK / ERR / PONG
 */

#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);

const int NUM_CH = 6;

// 各通道脉宽范围(微秒)。多数 180° 舵机用 500~2500。
// 若某个舵机两端到不了位或越界抖动, 单独调它这一格即可。
// 索引 0~2 = 20kg, 3~5 = MG90S。
int servoMinUs[NUM_CH] = { 500, 500, 500, 500, 500, 500 };
int servoMaxUs[NUM_CH] = { 2500, 2500, 2500, 2500, 2500, 2500 };

String inBuffer = "";

void writeAngle(uint8_t ch, int angle) {
  if (ch >= NUM_CH) return;
  if (angle < 0)   angle = 0;
  if (angle > 180) angle = 180;
  long us = servoMinUs[ch] +
            (long)(servoMaxUs[ch] - servoMinUs[ch]) * angle / 180;
  int ticks = (int)(us * 4096L / 20000L);   // 50Hz, 20000us 周期
  pwm.setPWM(ch, 0, ticks);
}

void setup() {
  Serial.begin(115200);
  Wire.begin();
  pwm.begin();
  pwm.setPWMFreq(50);
  delay(10);
  for (int ch = 0; ch < NUM_CH; ch++) writeAngle(ch, 90); // 上电居中
  Serial.println("READY");
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  int c1 = cmd.indexOf(',');
  String key = (c1 >= 0) ? cmd.substring(0, c1) : cmd;
  key.toUpperCase();
  String rest = (c1 >= 0) ? cmd.substring(c1 + 1) : "";
  int c2 = rest.indexOf(',');
  String a1 = (c2 >= 0) ? rest.substring(0, c2) : rest;
  String a2 = (c2 >= 0) ? rest.substring(c2 + 1) : "";

  if (key == "SET") {
    int ch = a1.toInt();
    int angle = a2.toInt();
    if (ch < 0 || ch >= NUM_CH) { Serial.println("ERR"); return; }
    writeAngle(ch, angle);
    Serial.println("OK");
  } else if (key == "OFF") {
    int ch = a1.toInt();
    if (ch < 0 || ch >= NUM_CH) { Serial.println("ERR"); return; }
    pwm.setPWM(ch, 0, 0);          // 关闭输出, 舵机松开
    Serial.println("OK");
  } else if (key == "PING") {
    Serial.println("PONG");
  } else {
    Serial.println("ERR");
  }
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inBuffer.length() > 0) { handleCommand(inBuffer); inBuffer = ""; }
    } else {
      inBuffer += c;
      if (inBuffer.length() > 64) inBuffer = "";
    }
  }
}
