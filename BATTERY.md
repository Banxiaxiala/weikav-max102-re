# 电量上报 —— 完整链路与实现方案

> 本文回答一个具体问题：**MAX102 的电量是怎么来的，怎样才能把它上报给主机。**
>
> 所有结论均从 `max102_stock_trimmed.bin` 反编译得出（Ghidra + Capstone 交叉验证），
> 并与公开的 `WestberryTech/qmk_westberry`（tri-mode 分支）和
> `dot-agi/fr8003-re`（Akko 5075B 同方案逆向）逐字节比对过。
>
> 编写日期：2026-11-10

---

## 0. 一句话结论

**电量由无线模块 FR8003A 测量，通过 UART 的 `0x5C` 帧送给 WB32FQ95，
WB32 收到后只点亮键盘上 10 颗 LED 做电量柱，从不告诉电脑或手机。**

所以要"上报"，必须改 WB32 固件；改多少取决于走 USB 还是蓝牙。

---

## 1. 硬件链路

```
         ┌──────────────┐
电池 ────│ X14076       │ 充电管理 / 保护
10000mAh │ (见 §7)      │
         └──────┬───────┘
                │ VBAT
                ├──────────────────┐
                │                  │
                ▼                  ▼
         ┌──────────────┐   ┌──────────────┐
         │ FR8003A      │   │ WB32FQ95     │
         │ 富芮坤 BLE5.1│   │ 键盘主控      │
         │ + 2.4G SoC   │   │ Cortex-M3    │
         │ 内部 ADC 测电 │   │ 256KB Flash  │
         └──────┬───────┘   └──────┬───────┘
                │                  │
                │  UART3 @115200 8N1
                │  PC10(TX) / PC11(RX)
                ├──────────────────┤
                │                  │
                │              矩阵 / RGB
                ▼
          BLE / 2.4G 无线链路
                ▼
           手机 / 电脑
```

### 1.1 主控侧串口（已从固件确认）

| 项 | 值 | 证据 |
|---|---|---|
| 外设 | **UART3**（基址 `0x40008400`） | 固件中 UART 相关基址只有 `0x40008400` 被引用 |
| 中断 | **IRQ32**（`UART3_IRQn = 32`） | `IRQ32_Handler` @ `0x0800E6B8` 是最大 IRQ（含 RX/TX 环形缓冲） |
| 波特率 | **115200 8N1** | `FUN_080034d4` 首条指令 `mov.w r0, #0x1c200` = 115200 |
| GPIO base | **`0x40000800` = GPIOC** ✅ 已与官方 `wb32fq95xx.h` 核对一致 |
| 引脚 | **`0x400` = bit10、`0x800` = bit11** | `FUN_0800be84`：`movw r2,#0x382`（AF 模式 0x2 + 上下拉 0x380）配 bit10 与 bit11 → **PC10 / PC11** |

> `0x382` 的低 2 位 `0x2` 是 AF 模式，bit3–9 (`0x380`) 是上下拉配置。
> 两个引脚同配置，一收一发，符合 UART TX/RX 特征。这与 STM32F1 系列
> `UART3 = PC10/PC11` 的默认 AF 完全吻合。

---

## 2. 协议层：Westberry `md` 编解码

帧格式（双向一致）：

```
[opcode] [payload...] [checksum]
checksum = (Σ opcode + payload) & 0xFF
```

- 多字节字段小端
- 载荷长度按 opcode 隐式确定；可变长帧内含长度字节
- **同步 ACK = `61 0D 0A`**（3 字节，无校验和）。收到合法帧的一方回 ACK，
  发送方等待 ACK 后才继续。停止-等待式，一次一帧。

### 2.1 WB32 → FR8003A（主控发）

| opcode | 名称 | 载荷 | 帧长 | 本项目是否使用 |
|---|---|---|---|---|
| `0xA1` | SEND_KB | 8 字节 boot 键盘报告 | 10 | ✅ |
| `0xA2` | SEND_NKRO | 14 字节 NKRO 位图 | 16 | ✅ |
| `0xA3` | SEND_CONSUMER | u16 LE usage | 4 | ✅ |
| `0xA4` | SEND_SYSTEM | 1 字节位图 | 3 | ✅ |
| `0xA6` | **DEVCTRL** | 1 字节子命令 | 3 | ✅ |
| `0xA8` | SEND_MOUSE | 5 `[btn,x,y,wheel,pan]` | 7 | — |
| `0xA9` | SEND_DEVINFO | `[len][name…]` | var | ✅ |
| `0xAB` | MANUFACTURER | `[len][str…]` | var | — |
| `0xAC` | PRODUCT | `[len][str…]` | var | — |
| `0xAD` | VPID | 4 = `(pid<<16)\|vid` LE | 6 | ✅ |
| `0xAF` | RAW | `[0x61][32][32B]` | 36 | ✅ |

### 2.2 `0xA6` DEVCTRL 子命令（全表）

| 子命令 | 名称 | 本项目固件是否发 | 发出位置 |
|---|---|---|---|
| `0x11` | USB | ✅ | `FUN_0800264c`、`FUN_08002864`、`FUN_080039fc` |
| `0x30` | 2.4G | ✅ | `FUN_080039fc` |
| `0x31`/`0x32`/`0x33` | BT1/BT2/BT3 | ✅ | `FUN_080039fc` |
| `0x34`/`0x35` | BT4/BT5 | ✅ | `FUN_080039fc`（隐藏通道） |
| `0x51` | PAIR | ✅ | `FUN_080039fc` |
| `0x52` | CLEAN（解除配对） | ✅ | `FUN_080039fc` |
| **`0x53`** | **INQVOL（查询电量）** | ✅ | **`FUN_08003ac8`** |
| `0x55`/`0x56` | BT 休眠 使能/禁用 | ✅ | `FUN_080042fc` |
| `0x57`/`0x58` | 2.4G 休眠 使能/禁用 | ✅ | `FUN_080042fc` |
| `0x64` | **充电中** | ❌ **未使用** | — |
| `0x65` | **充电停止** | ❌ **未使用** | — |
| `0x66` | **充电完成** | ❌ **未使用** | — |
| `0x70` | 模块固件版本 | ✅ | `FUN_080042fc` |

> ⚠️ **`0x64/0x65/0x66` 原厂完全没发**。这就是为什么现在键盘没有任何
> "正在充电/已充满"的对外表现。要上报充电状态，需要自己补发这三条
> （它们的作用是**告诉模块**当前的充电状态，用于模块侧 LED/上报逻辑，
> 不是查询——所以仍需知道充电检测脚接在谁身上，见 §7）。

### 2.3 FR8003A → WB32（模块回）

| opcode | 名称 | 载荷 | 本项目固件是否处理 |
|---|---|---|---|
| `0x5A` | INDICATOR（主机 LED 状态） | 1 字节位图 | ✅ |
| `0x5B` | DEVCTRL（连接状态） | 1 字节子命令 | ✅ |
| **`0x5C`** | **BATVOL（电量百分比）** | **1 字节 `0x00`–`0x64`** | ✅ |
| `0x5D` | MD_FW_VERSION | 1 字节 | ✅ |
| `0x60` | HOST_STATE（`0x01` = resume） | 1 字节 | ✅ |
| `0xAF` | RAW（回传） | `[0x60][32][32B]` | ✅ |

`0x5B` 连接状态子命令：`0x31` PAIRING · `0x32` CONNECTED ·
`0x33` DISCONNECTED · `0x36` REJECT

---

## 3. 固件实现（全部函数已定位）

### 3.1 收发主循环

| 函数 | 地址 | 作用 | 对应上游 |
|---|---|---|---|
| `FUN_080034d4` | `0x080034D4` | 初始化：`uart_init(115200)` + 清队列 | `md_init()` |
| `FUN_08002bb8` | `0x08002BB8` | 每轮主循环：串口收发 + 电量轮询 | `wireless_task()` |
| `FUN_08003518` | `0x08003518` | **收帧状态机**（最核心） | `md_receive_msg_task()` |
| `FUN_08003218` | `0x08003218` | 发送队列 push | `smsg_push()` |
| `FUN_080032cc`/`0x32d8` | — | 发送状态机 get/set | `smsg_get/set_state()` |
| `FUN_080034b0` | `0x080034B0` | 计算校验和 | `md_calc_check_sum()` |
| `FUN_08003874` | `0x08003874` | **发 DEVCTRL**：`[0xA6, cmd, sum]` | `md_send_devctrl()` |
| `FUN_080039b4` | `0x080039B4` | 发 RAW：`[0xAF,0x61,0x20,...]` | `md_send_raw()` |
| `FUN_080039fc` | `0x080039FC` | **切设备**（USB/2.4G/BT1–5 + 配对） | `md_devs_change()` |
| `FUN_08003ac8` | `0x08003AC8` | **查询电量**：发 `0xA6 0x53` | `md_inquire_bat()` |

### 3.2 电量相关的 RAM 变量

设备状态结构体基址 **`0x20000C7D`**（由 `FUN_080034f4`/`0x034fc`/`0x03504`
三个 getter 的字面量反推）：

| 偏移 | 绝对地址 | 字段 | 说明 |
|---|---|---|---|
| +0 | `0x20000C7D` | `state` | 0=NONE 1=PAIRING 2=CONNECTED 3=DISCONNECTED 4=REJECT |
| +1 | `0x20000C7E` | `indicator` | 主机 LED 位图（Caps/Num/Scroll） |
| +2 | `0x20000C7F` | `version` | 模块固件版本 |
| **+3** | **`0x20000C80`** | **`bat`** | **电量百分比 0–100** |

对应上游 `md_info_t { state, indicator, version, bat }` —— 顺序完全一致。

### 3.3 收帧解析细节（`FUN_08003518`）

```
状态 0：等 opcode
        合法 opcode 白名单 = 0x5A..0x5D, 0x60, 0xAF
        （反编译为 `uVar7 < 0x62` 且 `3 < (uVar7-0x5a)` 的过滤）
状态 1：收第 2 字节（子命令）
        若 opcode==0x61 且 byte==0x0D 且 下一字节==0x0A → ACK，结束
        若 opcode==0xAF 且 byte==0x60 → 变长（下一字节为长度+1）
状态 2：按 opcode 隐式长度收完载荷 + 校验和
校验和正确 → 发 ACK `61 0D 0A` → 分发给业务
```

校验通过后的分发（反编译直接可读）：

```c
switch (frame[0]) {
  case 0x5A: md_info.indicator = frame[1];        // 指示灯
  case 0x5B:                                      // 连接状态
      switch (frame[1]) {
        case 0x31: md_info.state = PAIRING;
        case 0x32: md_info.state = CONNECTED;
        case 0x33: md_info.state = DISCONNECTED;
        case 0x36: md_info.state = REJECT;
      }
  case 0x5C: md_info.bat = frame[1];              // ★ 电量
  case 0x5D: md_info.version = frame[1];          // 模块版本
  case 0x60: host_state_cb(frame[1] == 1);        // 主机 suspend/resume
  case 0xAF: if (frame[2] == 0x20) raw_receive_cb(frame+3, 32);
}
```

### 3.4 轮询节奏：每 3 秒一次，且只在无线模式

`FUN_08002bb8` 的完整逻辑（反编译可直接读懂）：

```c
void FUN_08002bb8(void) {            // = wireless_task()
    FUN_08002bb4();                  // 前置钩子
    FUN_08003164();                  // 发送状态机
    FUN_08003518();                  // ★ 收帧
    FUN_080042fc();                  // 设备切换后的初始化脉冲

    if (FUN_08002ea8() == 1) {       // == 1 表示"非 USB"
        if (state == 5 /* 无线已连接 */) {
            if (FUN_0800bc70(last_inq) > 0xbb7 /* 2999ms */) {
                last_inq = 0;
                FUN_08002fc4(1);
            }
        }
        return;
    }

    // USB 模式分支
    if (FUN_08002f5c() == 0) {                       // 非充电中
        if (FUN_0800bc70(last) > 0xbb7 /* 2999ms */) {   // 每 3 秒
            if (FUN_08003ac8() != 0) {                   // ★ 发 0xA6 0x53
                last = FUN_0800bbe8();
            }
        }
    }
}
```

> 注意：**电量查询在 USB 模式下也会做**（`FUN_08003ac8` 在 USB 分支里），
> 只是在正常连接模式下 3 秒一次。这比上游 `wireless_task()` 里"仅非 USB"更宽松
> —— 对我们是好事，意味着**插着线也能拿到电量**。

`0xbb7` = **2999** ms，与上游 `WLS_INQUIRY_BAT_TIME 3000` 完全对应。

### 3.5 电量唯一的消费点：10 段 LED 柱

**`FUN_08002570` @ `0x08002570`**（`FUN_0800571c` 每轮调用）：

```c
if (*DAT_080025f4) {                 // 0x20003D64：电量显示使能
    thunk_FUN_0800a320(0,0);         // 清空键盘
    for (i = 0; i < 10; i++) {
        led = DAT_080025f8[i];       // 0x0800F474：{35,36,...,44} = 10 颗灯
        if (i < bat / 10 || i == 0) {
            if (bat < 0x32 /* 50 */ && bat < 0x1e /* 30 */) {
                color = 红;
            } else {
                color = 绿;
            }
        } else {
            color = 灭;
        }
        FUN_08008828(led, color);
    }
}
```

- LED 索引表在 `0x0800F474`，实测字节为 `23 24 25 26 27 28 29 2A 2B 2C`
  （十六进制）= **35–44**，连续 10 颗
- `bat/10` 决定亮几段；`bat < 30` 用红（`R=0,G=0x96`），否则绿（`R=0x96,G=0`）
- 触发键码 **`0x7E06` = `HS_BATQ`**（VIA 里的 `BATQ`）

**这是 `md_info.bat` 在整个固件里的唯一读取点。**
VIA 的 45 条命令（含 22–45 号私有命令）**没有任何一条返回电量**。

---

## 4. QK_KB 自定义键码全表（已用跳转表精确还原）

固件里有两处 `0x7E00` 减法比较 + 跳转表，分别对应
**按下时处理**（`FUN_08004020`，`tbb @0x0800403C`）和
**松开/keymap 处理**（`FUN_080042fc` 附近，`tbh @0x0800436E`）。

| 键码 | 索引 | VIA 声明 | 实际功能（反编译） |
|---|---|---|---|
| `0x7E00` | 0 | `DEV BT1` | 切蓝牙 1（→ `0x80025fc`/`0x80029dc`） |
| `0x7E01` | 1 | `DEV BT2` | 切蓝牙 2 |
| `0x7E02` | 2 | `DEV BT3` | 切蓝牙 3 |
| `0x7E03` | 3 | `DEV 2.4G` | 切 2.4G |
| `0x7E04` | 4 | `DEV USB` | 切 USB |
| `0x7E05` | 5 | `display test white` | 全白测试 |
| **`0x7E06`** | 6 | **`HS_BATQ`** | **显示电量柱**（`FUN_08002570` 的使能开关） |
| `0x7E07` | 7 | `Bluetooth no secret pairing` | 免密钥配对 |
| `0x7E08` | 8 | `Recording lighting effects` | 灯效录制 |
| `0x7E09` | 9 | ❌ 未声明 | **切换主机通道**（`FUN_0800417e`，会发 `0x5C`/`0x5A` 相关） |
| `0x7E0A` | 10 | ❌ 未声明 | 未细查 |
| `0x7E0B` | 11 | ❌ 未声明 | 置位标志（`0x8004998`） |
| `0x7E0C` | 12 | ❌ 未声明 | `FUN_0800491d` |
| `0x7E0D` | 13 | ❌ 未声明 | `FUN_0800497d` |
| `0x7E0E` | 14 | ❌ 未声明 | `FUN_08004d39` |
| `0x7E0F` | 15 | ❌ | `FUN_08004cb5` |
| `0x7E10` | 16 | ❌ | `FUN_08004ced` |
| `0x7E11` | 17 | ❌ | `FUN_08004d0d` |
| `0x7E12` | 18 | ❌ | 空操作 |
| `0x7E13` | 19 | ❌ | `FUN_08004a73` |
| `0x7E14` | 20 | ❌ | `FUN_08004a99` |
| `0x7E15` | 21 | ❌ | `FUN_08004ab7` |
| `0x7E16` | 22 | ❌ | `FUN_0800491d` |
| `0x7E17` | 23 | ❌ | — |

> 修正：原 `HANDOVER.md` 说 `0x7E09/0A/0C/0D/0E` 是"未知功能"。
> 其中 `0x7E09` 已确认是**切换主机通道**（调 `FUN_08005c06` 判断当前通道，
> 再 `FUN_08005abe` 切换），`0x7E0B` 是置位标志。

---

## 5. 现在为什么电脑看不到电量

三处都缺：

| 检查项 | 结果 | 证据 |
|---|---|---|
| HID 描述符里有 Battery Strength（`0x05 0x06` / `0x09 0x20`）？ | ❌ 没有 | 全片只有 2 个键盘描述符 + Consumer + SysCtrl + VIA(FF60) |
| VIA 命令里有返回电量的？ | ❌ 没有 | 45 条命令全表已还原，`GET_KEYBOARD_VALUE` 的 5 个 value id 无电量 |
| 原始 HID（`0xAF` RAW）回传电量？ | ❌ 没有 | `md_receive_raw_cb` 只转发给 VIA raw HID |
| 蓝牙 GATT 有 Battery Service（`0x180F`）？ | ❓ **未验证** | 由 FR8003A 固件决定，需 dump 模块或扫 BLE |

**结论：USB 模式下 100% 看不到，因为主控根本没往外发。**
蓝牙模式下要看 FR8003A 的脸色（§6 路线 C）。

---

## 6. 三条上报路线

### 路线 A（推荐先做）：只改主控，覆盖 USB 模式

**改动量：小。`md_info.bat`（`0x20000C80`）现成就有 0–100 的百分比。**

两个可选出口，建议都做：

**A-1. VIA 私有命令**（最容易调，改完立刻能用现有 `hidapi` 脚本验证）

固件里 22–45 号命令全是厂家私有，随便挑一个空的（比如 `0x2D`/45 已被占用，
用 `0x2E` 更安全）。协议沿用现有 `REPORT_SIZE=33` 格式：

```
请求: [0, cmd=0x2E, 0, 0, ...]
响应: [0, cmd, 0, 0, bat, state, version, 0, ...]
                              ↑    ↑       ↑
                              │    │       └ 模块固件版本 (md_info.version)
                              │    └ 连接状态 (md_info.state)
                              └ 电量百分比 0-100
```

实现只需在 `FUN_08009868` 的 switch 里加一个 case，几行 C：

```c
case 0x2E: {                       // VIA_GET_BATTERY_INFO
    uint8_t *resp = DAT_08009aac;  // 响应缓冲区 0x20000F60
    resp[4] = *md_getp_bat();      // 0x20000C80
    resp[5] = md_state;            // 0x20000C7D
    resp[6] = md_version;          // 0x20000C7F
    break;
}
```

**A-2. HID 电池报告**（让系统原生显示）

在 HID 描述符里加一个 Battery Strength 集合，然后在键盘报告后追加/单独发送：

```
05 06        Usage Page (Generic Device Controls)
09 20        Usage (Battery Strength)
15 00 26 64  Logical Min/Max (0..100)
75 08 95 01  Report Size/Count
81 02        Input (Data,Var,Abs)
```

> ⚠️ 改 HID 描述符会**改变接口布局**，可能影响 VIA 通道识别。
> 建议放在第 3 个接口（现有多媒体/系统控制那个）里，或新建第 4 个接口。

**难度**：需要能编译出可刷的固件 → 仍然要过「矩阵引脚 / RGB 类型」这两关
（见 `HANDOVER.md` P2）。**但电量这部分零风险，逻辑可以完全照抄。**

### 路线 B：让手机系统原生显示（BLE Battery Service）

**取决于 FR8003A 的 GATT 表里有没有 `0x180F`。**

- 有 → 你现在配对蓝牙后，手机/Windows 蓝牙设置里就应该已经能看到电量百分比。
  （你说没接设备所以没扫，插上就能验证，一分钟的事）
- 没有 → 需要改 FR8003A 固件加 GATT service。
  好消息：**它有 BLE OTA，CRC32 校验但无签名**，可以不拆机刷。

### 路线 C：充电状态上报

需要知道 **X14076 的 CHRG/STDBY/DONE 脚接到谁**：

- 若接 FR8003A → 模块能自己知道，会在 `0x5C` 之外另有上报（需 dump 模块确认）
- 若接 WB32 → 主控可以自己读 GPIO，然后**主动发 `0xA6 0x64/0x65/0x66`**
  告诉模块当前充电状态

原厂两者都没做，所以现在完全没有充电指示。

---

## 7. X14076 充电 IC

| 项 | 值 |
|---|---|
| 丝印 | `X14076` / `B01A`（B01A 疑为批次码） |
| 封装 | 推测 SOT-23-6（需照片确认） |
| 公开资料 | **未找到 datasheet**。`X` 前缀 + 国产品牌体系，疑似赛芯（Xysemi）或同类 |
| 作用 | 锂电池线性充电管理（配合 10000mAh 单节） |

**要确定的**：`CHRG`（充电中）/ `STDBY` 或 `DONE`（充满）两个开漏输出脚
分别接到 WB32 的哪个 GPIO、还是接到 FR8003A。

> 已知旁证：`0xA6 0x64/0x65/0x66` 这三个 "battery power control" 子命令
> 是**主控发给模块**的，语义是"我这边检测到充电中/停止/完成"。
> 既然原厂定义了这三条命令却一次都没发，说明原厂自己也没做充电检测上报。
> 大概率 X14076 的状态脚是悬空或只接 LED。

---

## 8. 待核实项（本文件的不确定处）

| # | 待核实 | 影响 | 怎么核 |
|---|---|---|---|
| 1 | ~~GPIO 基址疑点~~ | ✅ **已解决**：`0x40000800` 就是官方 GPIOC | 对照 `wb32fq95xx.h` |
| 2 | ~~UART 引脚~~ | ✅ **已解决**：PC10/PC11 | 固件 `FUN_0800be84` |
| 3 | X14076 的 CHRG/STDBY 接谁 | 能否上报充电态 | 照片 + 万用表 |
| 4 | FR8003A GATT 里有无 `0x180F` | 路线 B 是否白送 | 手机连一次看蓝牙设置 |
| 5 | FR8003A 的 ADC 分压电阻比例 | 若要把 `0x5C` 的百分比换算成电压 | dump 模块固件 |
| 6 | LED 索引 35–44 对应物理哪 10 颗键 | 电量柱位置 | 实机按 `BATQ` 看 |

> **注**：矩阵引脚也已从固件完整还原，见 [`HARDWARE.md`](HARDWARE.md)。

---

## 9. 与原 `HANDOVER.md` 的结论差异（重要修正）

| 原结论 | 修正后 |
|---|---|
| `DAT_0800EF7C` = `0x40014000` 是"未知外设，可能是无线总线" | ❌ **错**。`0x40014000` 是 **USB 控制器基址**（WB32 `USB_BASE`），`IRQ14_Handler` 是 **USB 中断** |
| 无线模块通过"未知总线"连接，需逻辑分析仪逆向 | ❌ **错**。就是 **UART3 @115200**，协议已完全还原 |
| `0x7E09`/`0x7E0A` 等 5 个键码"未知功能" | 已还原跳转表，见 §4 |
| 无线模块型号未知（BK3633/HS6621/Telink/nRF52 猜测） | ✅ 确认 **Freqchip FR8003A** |
| 电量未知 | ✅ 已完全还原，见本文 |

---

## 10. 参考资料

| 资源 | 用途 |
|---|---|
| [`WestberryTech/qmk_westberry`](https://github.com/WestberryTech/qmk_westberry/tree/tri-mode) → `keyboards/westberry/wireless/module.c` | `md` 协议上游实现，与本固件逐字节吻合 |
| [`dot-agi/fr8003-re`](https://github.com/dot-agi/fr8003-re) | FR8003A 逆向（Akko 5075B 同方案），含 UART 协议、BLE OTA、2.4G 链路 |
| [`ChibiOS-Contrib`](https://github.com/ChibiOS/ChibiOS-Contrib) → `os/common/ext/CMSIS/WB32/WB32FQ95xx/wb32fq95xx.h` | WB32 外设基址权威来源 |
| 本地 `ghidra_out/decompiled_all.c` | 本项目 520 个函数反编译 |
