/*
 * I2C 扫描器 — 用来确认 UNO 能否检测到 PCA9685
 * ------------------------------------------------------------
 * 烧录后, 打开 Arduino IDE 的串口监视器 (右上角放大镜),
 * 波特率选 115200。
 *
 * 期望看到:  Found device at 0x40
 *   -> 说明 I2C 接线正确, PCA9685 在线。可以换回 servo_control 固件。
 * 如果看到:  No I2C devices found
 *   -> SDA/SCL 接反, 或 VCC/GND 没接好, 或接触不良。
 */
#include <Wire.h>

void setup() {
  Wire.begin();
  Serial.begin(115200);
  while (!Serial) { }
  Serial.println("\nI2C Scanner 启动");
}

void loop() {
  byte count = 0;
  Serial.println("扫描中...");
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("  找到设备: 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
      count++;
    }
  }
  if (count == 0) Serial.println("  没找到任何 I2C 设备 (检查 SDA/SCL/VCC/GND)");
  else            Serial.print("  共找到 "), Serial.print(count), Serial.println(" 个设备");
  Serial.println();
  delay(2000);
}
