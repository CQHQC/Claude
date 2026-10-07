/*
 * 42 步进电机 (NEMA 17) 控制固件  —  Arduino UNO + A4988/DRV8825
 * ============================================================
 * 通过串口接收上位机指令，非阻塞驱动，并带线性加减速斜坡，
 * 避免 42 电机高速启动时丢步/堵转。
 *
 * 接线 (详见 docs/wiring.html 接线图):
 *   A4988 STEP   -> D3
 *   A4988 DIR    -> D2
 *   A4988 ENABLE -> D4         (低电平使能)
 *   A4988 VDD    -> UNO 5V     (逻辑电源)
 *   A4988 GND    -> UNO GND    (逻辑地, 必须与电源地共地)
 *   A4988 RESET  -- SLEEP      (用短线短接, 否则芯片不工作)
 *   A4988 VMOT   -> 12V 电源板 +12V   (VMOT-GND 间并 100uF 电容!)
 *   A4988 GND    -> 12V 电源板 GND
 *   A4988 1A/1B  -> 电机 A 相 (同一线圈的两根线)
 *   A4988 2A/2B  -> 电机 B 相 (另一线圈的两根线)
 *
 * 串口协议 (115200, 每条以换行结尾):
 *   EN              使能(锁轴)        DIS   失能(松轴)
 *   DIR,0 / DIR,1   方向
 *   SPD,<us>        目标每步间隔(微秒) 200~10000, 越小越快
 *   MOVE,<n>        转动 n 步后停止
 *   RUN             连续转动           STOP  停止
 *   PING            心跳 -> PONG
 * 回复: READY / OK / DONE / PONG / ERR
 */

const int DIR_PIN    = 2;
const int STEP_PIN   = 3;
const int ENABLE_PIN = 4;   // A4988/DRV8825 ENABLE 低电平有效

// ---- 运动状态 ----
long          stepsRemaining = 0;       // >0: 定量移动剩余步数
bool          continuous     = false;
bool          enabled        = false;
unsigned long lastStepMicros = 0;

// ---- 加减速斜坡 ----
const unsigned long START_INTERVAL = 2500; // 启动时的慢速间隔(us)
const unsigned long RAMP_STEP      = 12;   // 每步向目标速度靠拢的步长(us)
unsigned long targetInterval = 1000;       // 目标间隔(由 SPD 设置)
unsigned long curInterval    = START_INTERVAL; // 当前实际间隔(斜坡)

String inBuffer = "";

void setup() {
  pinMode(DIR_PIN, OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(ENABLE_PIN, OUTPUT);

  digitalWrite(STEP_PIN, LOW);
  digitalWrite(DIR_PIN, LOW);
  digitalWrite(ENABLE_PIN, HIGH); // 默认失能(松轴)

  Serial.begin(115200);
  Serial.println("READY");
}

void doStepPulse() {
  digitalWrite(STEP_PIN, HIGH);
  delayMicroseconds(3);           // A4988 最小脉宽~1us, 给 3us 余量
  digitalWrite(STEP_PIN, LOW);
}

void setEnabled(bool on) {
  enabled = on;
  digitalWrite(ENABLE_PIN, on ? LOW : HIGH);
  if (!on) { continuous = false; stepsRemaining = 0; }
}

// 开始一段新运动时调用: 从慢速起步以便斜坡加速
void beginMotion() {
  if (!enabled) setEnabled(true);
  curInterval = max(START_INTERVAL, targetInterval);
}

// 每走一步后, 让当前间隔朝目标间隔平滑靠拢(可加速也可减速)
void rampToward() {
  if (curInterval > targetInterval) {
    unsigned long d = curInterval - targetInterval;
    curInterval -= (d < RAMP_STEP) ? d : RAMP_STEP;
  } else if (curInterval < targetInterval) {
    unsigned long d = targetInterval - curInterval;
    curInterval += (d < RAMP_STEP) ? d : RAMP_STEP;
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  int comma = cmd.indexOf(',');
  String key = (comma >= 0) ? cmd.substring(0, comma) : cmd;
  String arg = (comma >= 0) ? cmd.substring(comma + 1) : "";
  key.toUpperCase();

  if (key == "EN") {
    setEnabled(true);                 Serial.println("OK");
  } else if (key == "DIS") {
    setEnabled(false);                Serial.println("OK");
  } else if (key == "DIR") {
    digitalWrite(DIR_PIN, arg.toInt() ? HIGH : LOW);
    Serial.println("OK");
  } else if (key == "SPD") {
    long v = arg.toInt();
    if (v < 200)   v = 200;
    if (v > 10000) v = 10000;
    targetInterval = v;               Serial.println("OK");
  } else if (key == "MOVE") {
    long n = arg.toInt();
    if (n <= 0) { Serial.println("ERR"); return; }
    continuous = false;
    stepsRemaining = n;
    beginMotion();                    Serial.println("OK");
  } else if (key == "RUN") {
    continuous = true;
    beginMotion();                    Serial.println("OK");
  } else if (key == "STOP") {
    continuous = false;
    stepsRemaining = 0;
    curInterval = START_INTERVAL;     // 下次重新斜坡起步
    Serial.println("OK");
  } else if (key == "PING") {
    Serial.println("PONG");
  } else {
    Serial.println("ERR");
  }
}

void readSerial() {
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

void loop() {
  readSerial();

  if (enabled && (continuous || stepsRemaining > 0)) {
    unsigned long now = micros();
    if (now - lastStepMicros >= curInterval) {
      lastStepMicros = now;
      doStepPulse();
      rampToward();
      if (!continuous && stepsRemaining > 0) {
        stepsRemaining--;
        if (stepsRemaining == 0) { curInterval = START_INTERVAL; Serial.println("DONE"); }
      }
    }
  }
}
