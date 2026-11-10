# Weikav MAX102 硬件与固件逆向分析报告

> 本文所有数据均来自**实机读取**，非网络推测。
> 设备：Weikav MAX102（维咖 MAX102）三模无线机械键盘
> 分析日期：2026-11-10

---

## 1. 结论速览

| 项目 | 结论 |
|---|---|
| 主控 MCU | **WB32FQ95**（Westberry 韦斯特伯里，Cortex-M3，256KB Flash） |
| 是否 QMK 键盘 | **是**，VIA 协议版本 12 |
| QMK 主线支持 | ✅ 支持（`WB32FQ95` + `wb32-dfu` bootloader） |
| 官方是否给固件 | ❌ 不给。Weikav 在 QMK 违规名单上 |
| 固件能否备份 | ✅ **能**，ROM DFU 可直接裸读 Flash |
| 三模架构 | 主控 + 外部无线模块（UART 通信） |
| 可救砖性 | ✅✅ 双保险：ROM DFU + 4 针 SWD |

**一句话**：这是一块**真 QMK 键盘**，固件可以完整备份和刷写，但官方不给源码；QMK 移植技术可行，工作量大头在**无线模块的 UART 协议逆向**。

---

## 2. 硬件识别

### 2.1 PCB 丝印

```
MA102-QMK-V1
2025 05 26
```

`-QMK` 字样是厂家自己印的，直接表明设计基于 QMK。

### 2.2 主控

照片中 U7 位置，QFP48 封装，丝印：

```
WB32F
0936TB
AP4697
2532
```

- `WB32F` = **WB32FQ95**（Westberry Technology，常州）
- `2532` = 2025 年第 32 周生产
- 板子设计日期 2025-05-26，芯片 2025 年 8 月，时序合理

### 2.3 调试接口

```
CON2:  GND SWCLK SWDIO 3.3V
```

完整的 4 线 SWD 焊盘，**未焊接排针但裸露可用**。这是厂家为救砖留的，也意味着：

- 可以外部供电
- 可以用 SWD 探针做深度调试
- **注意**：OpenOCD 目前没有 WB32 的 flash 驱动（`src/flash/nor/` 里没有），所以 SWD 只能连 core、跑断点，**不能替代 DFU 做 flash 读写**

### 2.4 RGB 与其它器件

| 丝印 | 说明 |
|---|---|
| `LED71` … `LED104` | 单颗 RGB LED，共约 104 颗，串行驱动 |
| `DW34/DW43/DW44/DW57` | 二极管阵列（矩阵防鬼键） |
| `U8` (SOP8) | SPI Flash，可能存灯效资源或配置 |
| `CON3 3.3V` | 额外的 3.3V 测试点 |
| `Y1` | 晶振 |
| 电池 | 10000mAh（官方标称） |

### 2.5 USB 标识

| 模式 | VID | PID |
|---|---|---|
| 正常工作 | `0x342D` | `0xE537` |
| DFU 模式 | `0x342D` | `0xDFA0` |

HID 接口布局（正常工作模式）：

```
interface 0: usage_page=1      usage=6    （键盘）
interface 1: usage_page=65376  usage=97   （VIA 通道，REPORT_SIZE=33）
interface 2: usage_page=1/12/... （多媒体、系统控制等）
```

---

## 3. 固件读取与备份

### 3.1 为什么能读

WB32 的 **DFU bootloader 固化在 ROM**（地址 `0x1FFFE000`），官方 `wb32-dfu-updater` 工具支持 `-U`（upload）操作，可直接从 `0x08000000` 裸读 Flash。

这一点很关键：**不需要 OpenOCD，不需要拆焊，不需要专用编程器。**

### 3.2 进入 DFU 的方法（从固件实读的层键链推导）

```
Layer 0  matrix(5,9)  = MO(1)      ← FN 键
Layer 1  matrix(4,12) = MO(4)      ← 右 Shift 位置
Layer 4  matrix(0,0)  = QK_BOOT    ← ESC 位置
```

**操作方法：按住 FN → 按住右 Shift → 点一下 ESC**

这是官方预留的隐藏第 5 层（`LAYER_COUNT=5`，但网页驱动只暴露 4 层）。

### 3.3 读取命令

```bash
# 列设备
wb32-dfu-updater_cli.exe -l

# 全片读取 256KB
wb32-dfu-updater_cli.exe -U max102_stock_256k.bin -Z 262144

# 复位回正常模式
wb32-dfu-updater_cli.exe -R
```

**实测耗时 0.6 秒**。`-Z` 必须显式指定，工具不会自动探测容量。

### 3.4 备份校验结果

| 项目 | 值 |
|---|---|
| 文件大小 | 262,144 B |
| MD5 | `4014df74ebde3479afcfc90460eae28a` |
| SHA256 | `ac842a1134477ad2dc1085b9429fdef0c0cdc0d9554ccecbb51a75968ef9d1b5` |
| 二次读取 | **MD5 完全一致** ✅ |
| 有效长度 | 0x10D33（约 68KB），其后全 `0x00` |
| 初始 SP | `0x20000400`（SRAM 1KB 已用） |
| Reset Handler | `0x080001B9`（Thumb） |
| 向量表项 | 128 项 |

**截断建议**：截到 `0x11000`（69632 B，4KB 对齐）即为完整有效固件。

---

## 4. 固件内部结构分析

### 4.1 关键字符串

| 字符串 | 地址 | 含义 |
|---|---|---|
| `LEKU` | 0x0F520 | **实际制造商名**（USB 描述符） |
| `MAX102-2.4G` | 0x0F52F | 2.4G 接收器配对名 |
| `MAX102` | 0x0F53E | USB 产品名 |
| `MAX102-BT1` | 0x0F545 | 蓝牙通道 1 设备名 |
| `MAX102-BT2` | 0x0F551 | 蓝牙通道 2 |
| `MAX102-BT3` | 0x0F55D | 蓝牙通道 3 |
| `MAX102 BT4` | 0x0F569 | 蓝牙通道 4（注意是空格不是连字符） |
| `MAX102 BT5` | 0x0F574 | 蓝牙通道 5 |

⚠️ **重要发现**：固件里有 **5 个蓝牙通道**（BT1-BT5），而 VIA 定义只暴露了 `DEV BT1/2/3` 三个。说明：

- 硬件/固件支持 5 个配对槽
- 官方软件只开放 3 个
- 另 2 个槽位被隐藏

### 4.2 其它字符串

```
REENT malloc succeeded
../../../../../../../../newlib/libc/stdlib/rand.c
assertion "%s" failed: file "%s", line %d%s%s
0123456789ABCDEF
0123456789abcdef
```

→ 标准 **newlib**（`arm-none-eabi-gcc` 工具链）编译产物。`rand.c` 路径说明用了 `rand()`，可能与灯效随机数有关。

### 4.3 无无线协议栈

固件里**没有任何蓝牙栈或无线协议代码的痕迹** —— 只有蓝牙设备名字符串。

结合主板上**只有一颗 U7 主控**，可断定架构为：

```
        ┌──────────────┐   UART   ┌──────────────┐
USB ────│ WB32FQ95     │◄────────►│ 无线模块      │─── BT / 2.4G
        │ (键盘主控)    │          │ (BK/HS/Telink)│
        └──────────────┘          └──────────────┘
              │
              ▼
        RGB LED x104 / 矩阵
```

这正是 `WestberryTech/qmk_westberry` 仓库 `tri-mode` 分支所支持的架构。

---

## 5. VIA 协议实测

### 5.1 版本信息

| 参数 | 实测值 |
|---|---|
| PROTOCOL_VERSION | **12** |
| FIRMWARE_VERSION | `0.0.0`（厂家未填，4 字节全 0） |
| LAYER_COUNT | **5** |
| 矩阵 | 6 rows × 19 cols = 114 位置，实际 101 键 |
| MACRO_COUNT | 16 |
| 宏缓冲 | 1984 字节（当前全空） |
| LAYOUT_OPTIONS | `00 00 00 00` |

### 5.2 命令集（从官方网页驱动逆向）

```c
// 标准 VIA
GET_PROTOCOL_VERSION              = 1
GET_KEYBOARD_VALUE                = 2
SET_KEYBOARD_VALUE                = 3
DYNAMIC_KEYMAP_GET_KEYCODE        = 4
DYNAMIC_KEYMAP_SET_KEYCODE        = 5
CUSTOM_MENU_SET_VALUE             = 7
CUSTOM_MENU_GET_VALUE             = 8
CUSTOM_MENU_SAVE                  = 9
EEPROM_RESET                      = 10
BOOTLOADER_JUMP                   = 11
DYNAMIC_KEYMAP_MACRO_GET_COUNT    = 12
DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE = 13
DYNAMIC_KEYMAP_MACRO_GET_BUFFER   = 14
DYNAMIC_KEYMAP_MACRO_SET_BUFFER   = 15
DYNAMIC_KEYMAP_MACRO_RESET        = 16
DYNAMIC_KEYMAP_GET_LAYER_COUNT    = 17
DYNAMIC_KEYMAP_GET_BUFFER         = 18
DYNAMIC_KEYMAP_SET_BUFFER         = 19
DYNAMIC_KEYMAP_GET_ENCODER        = 20
DYNAMIC_KEYMAP_SET_ENCODER        = 21

// 厂家私有：灯效配置（非标准 VIA）
BACKLIGHT_CONFIG_SET_VALUE        = 7
BACKLIGHT_CONFIG_GET_VALUE        = 8
BACKLIGHT_CONFIG_SAVE             = 9
```

### 5.3 keyboard value 枚举（厂家扩展）

```c
UPTIME              = 1
LAYOUT_OPTIONS      = 2
SWITCH_MATRIX_STATE = 3
FIRMWARE_VERSION    = 4
DEVICE_INDICATION   = 5
```

### 5.4 报文格式

```
REPORT_SIZE = 33

请求: [0, cmd, ...payload, padding...]
响应: [0, cmd, ...data, padding...]
```

读取 buffer 时格式特殊：

```
cmd 18: [offset_hi, offset_lo, size]   size <= 28
响应 data 从 r[4] 开始
```

---

## 6. 完整键位表（实读）

### Layer 0 — 基础层

```
ESC  F1   F2   F3   F4   F5   F6   F7   F8   F9   F10  F11  F12  INS  PSCR SCRL HOME END
GRV  1    2    3    4    5    6    7    8    9    0    MINS EQL  BSPC DEL  NUM  PSLS PAST PMNS
TAB  Q    W    E    R    T    Y    U    I    O    P    LBRC RBRC BSLS PGUP P7   P8   P9   PPLS
CAPS A    S    D    F    G    H    J    K    L    SCLN QUOT ENT  PGDN P4   P5   P6
LSFT Z    X    C    V    B    N    M    COMM DOT  SLSH RSFT UP   P1   P2   P3   PENT
LCTL LGUI LALT SPC  MO(1) RCTL LEFT DOWN RGHT P0   PDOT
```

### Layer 1 — FN 层（媒体 / 三模 / 灯效）

```
CLR_EE MYCM WHOM MAIL CALC MSEL MSTP MPRV MPLY MNXT MUTE VOLD VOLU ---- ---- ---- ---- ----
----   ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- ---- KB0A ---- ---- ---- ---- ----
----   BT1  BT2  BT3  2.4G USB  ---- ---- ---- ---- ---- KB0C KB0D UG_NEXT ---- ---- ---- ---- ----
----   ---- ---- NOSEC ---- ---- ---- ---- ---- ---- ---- ---- UG_HUEU ---- ---- ---- ----
----   ---- ---- ---- ---- ---- ---- KB09 ---- ---- ---- MO(4) UG_VALU ---- ---- ---- ---- ----
BATQ   MAGIC_TOGGLE_GUI  ----  WHITE  ---- ---- UG_SPDD UG_VALD UG_SPDU ---- ----
```

### Layer 2 — 第二基础层

与 Layer 0 基本相同，但 FN 键指向 `MO(3)` 而非 `MO(1)`。

### Layer 3 — 第二 FN 层

与 Layer 1 结构相同，F 区换成 `BRID BRIU MCTL LPAD`。

### Layer 4 — BOOT 层（隐藏）

```
QK_BOOT ---- ---- ---- ...（其余全 TRNS）
   ↑ 位于 matrix(0,0) = ESC 键位置
```

### 自定义键码（QK_KB 区 0x7E00+）

| 键码 | 索引 | 名称 | 功能 |
|---|---|---|---|
| `0x7E00` | 0 | `DEV BT1` | 切到蓝牙 1 |
| `0x7E01` | 1 | `DEV BT2` | 切到蓝牙 2 |
| `0x7E02` | 2 | `DEV BT3` | 切到蓝牙 3 |
| `0x7E03` | 3 | `DEV 2.4G` | 切到 2.4G |
| `0x7E04` | 4 | `DEV USB` | 切到 USB |
| `0x7E05` | 5 | `display test white` | 白色测试灯 |
| `0x7E06` | 6 | `HS_BATQ` | 查询电量 |
| `0x7E07` | 7 | `Bluetooth no secret pairing channel` | 免密钥配对 |
| `0x7E08` | 8 | `Recording lighting effects` | 录音灯效 |
| `0x7E09` | 9 | ⚠️ **未声明** | **切换主机通道**（`FUN_0800417e`） |
| `0x7E0A` | 10 | ⚠️ **未声明** | 未细查（`FUN_08004d93`） |
| `0x7E0C` | 12 | ⚠️ **未声明** | `FUN_0800491d` |
| `0x7E0D` | 13 | ⚠️ **未声明** | `FUN_0800497d` |
| `0x7E0E` | 14 | ⚠️ **未声明** | `FUN_08004d39` |

**官方 `via.json` 只声明到索引 8**，固件实际用到 **24 个**（`0x7E00`–`0x7E17`）。
跳转表已完整还原（`tbb @0x0800403C` + `tbh @0x0800436E`），全表见
[`BATTERY.md`](BATTERY.md) §4。

---

## 7. VIA 定义文件缺陷

官方 `max102(1).json`：

```json
{
  "name": "MAX102",
  "vendorId": "0x342d",
  "productId": "0xE537",
  "keycodes": ["qmk_lighting"],
  "matrix": {"rows": 6, "cols": 19},
  "customKeycodes": [ ... 9 项 ... ],
  "layouts": { "keymap": [ ... 101 键 ... ] }
}
```

**问题清单**：

| 问题 | 影响 |
|---|---|
| 只声明 9 个 customKeycode | 5 个隐藏功能无法在 VIA 中选择 |
| 没有声明 layer 4 | 用户不知道有 BOOT 层 |
| `lighting` 字段缺失 | VIA 的灯效面板可能不完整 |
| 使用旧版 `layouts.keymap` 格式 | 不是 VIA v3 的新格式 |
| `firmware_version` 为 0.0.0 | 无法追溯版本 |

### 灯效支持（从 json 的 menus 提取）

`qmk_lighting` 菜单声明了 RGB Matrix 效果：

```
All Off(0)  Alphas Mods(2)  Breathing(5)  Band Sat(6)  Band Pinwheel Val(9)
Cycle Left Right(13)  Rainbow Moving Chevron(15)  Cycle Out In(16)
Jellybean Raindrops(24)  Hue Breathing(25)  Hue Pendulum(26)
Pixel Flow(29)  Pixel Fractal(30)  Solid Reactive Simple(33)
Solid Reactive(34)  Solid Reactive Wide(35)  Solid Splash(43)  Close All(45)
```

参数：Brightness(0-255), Effect Speed(0-255), Color(HSV)

---

## 8. QMK 移植可行性评估

### 8.1 好消息

QMK 主线对 `WB32FQ95` 的支持是**完整的**：

| 组件 | 状态 | 位置 |
|---|---|---|
| MCU 选择 | ✅ | `platforms/chibios/mcu_selection.mk` |
| ChibiOS 移植 | ✅ | `ChibiOS-Contrib/os/hal/ports/WB32/WB32FQ95xx/` |
| 驱动 | ✅ | GPIO / SPI / I2C / TIM / UART / USB / DMA / ADC |
| 链接脚本 | ✅ | `WB32FQ95x9.ld` (96K) / `xB.ld` (128K) / `xC.ld` (256K) |
| 板级定义 | ✅ | `GENERIC_WB32_FQ95XX` |
| Bootloader | ✅ | `wb32-dfu` (ROM, `0x1FFFE000`) |
| 刷写工具 | ✅ | `wb32-dfu-updater_cli` |

**量产参考实现**（同 MCU，可直接抄结构）：

- `keyboards/monsgeek/m1` — 有完整 `mcuconf.h` / `halconf.h` / `keyboard.json`
- `keyboards/monsgeek/m2/m3/m5/m6`
- `keyboards/gmmk`
- `keyboards/akko`
- `keyboards/inland`

`monsgeek/m1` 的关键配置：

```json
{
  "processor": "WB32FQ95",
  "bootloader": "wb32-dfu",
  "features": { "bootmagic": true, "nkro": true, "encoder": true, "rgb_matrix": true },
  "matrix_pins": {
    "cols": ["C1","C2","C3","A0","A1","A2","A3","A4","A5","A6","A7","C4","C5","B0","B1","B2"],
    "rows": ["B15","C6","C7","C8","C9","A8"]
  },
  "diode_direction": "ROW2COL",
  "dynamic_keymap": { "layer_count": 6 }
}
```

### 8.2 坏消息

| 障碍 | 严重程度 | 说明 |
|---|---|---|
| ~~**无线功能无源码**~~ | ✅ **已解决** | BT/2.4G 走 **UART3 @115200**，`md` 协议**已 100% 还原**（见 [`BATTERY.md`](BATTERY.md)），无线模块确认为 **Freqchip FR8003A** |
| **矩阵引脚未知** | 🟡 中 | 需万用表逐一测（6×19=114 点） |
| **RGB LED 类型未知** | 🟡 中 | 需确认是 WS2812 还是私有协议 |
| **QMK 违规名单** | 🟡 中 | Weikav 在 `docs/license_violations.md` 上，PR 会被拒 |
| **无 SWD flash 算法** | 🟢 低 | 但有 ROM DFU，不影响 |

### 8.3 QMK 违规名单（重要）

`qmk/qmk_firmware/docs/license_violations.md` 第 52 行：

```
| Weikav | Selling tri-mode boards based on QMK without sources, just `via.json` provided. |
```

来自 QMK 维护者 tzarc 的 issue #24085：

> Vendors who submit PRs whilst not providing full sources for all of their shipping boards will be put on hold until source code for all violating keyboards are provided.

**这意味着**：即使你写好了 Max102 的 QMK 移植，**提交 Pull Request 到 QMK 主线会被拒绝**，除非 Weikav 先交出全部源码。

**绕开方式**：
1. 放在自己的 fork 里（GPLv3 允许）
2. 提交到 `WestberryTech/qmk_westberry` 的 `tri-mode` 分支（非官方主线）

---

## 9. 三模无线架构

### 9.1 Westberry 官方方案

`WestberryTech/qmk_westberry`，默认分支 **`tri-mode`**，包含：

```
keyboards/westberry/wireless/
├── wireless.c      主入口
├── wireless.h      wireless_init / wireless_devs_change
├── transport.c     TRANSPORT_USB / TRANSPORT_WLS 切换
├── module.c        设备枚举
├── smsg.c          消息队列
├── md_raw.c        底层 UART 收发
├── lowpower.c      低功耗
└── lpwr_wb32.c     WB32 专用低功耗
```

### 9.2 设备枚举（`module.h`）

```c
enum {
    DEVS_USB = 0,
    DEVS_BT1, DEVS_BT2, DEVS_BT3, DEVS_BT4, DEVS_BT5,
    DEVS_2G4,
};
```

**这与我们从固件里挖出的 `MAX102-BT1` … `MAX102 BT5` 完全对应！**

→ 说明 Max102 用的就是这套 Westberry 参考方案的变体，**5 个蓝牙槽 + 2.4G + USB**。

### 9.3 通信协议（`module.h`）

```c
enum {
    MD_SND_CMD_SEND_KB       = 0xA1,
    MD_SND_CMD_SEND_NKRO     = 0xA2,
    MD_SND_CMD_SEND_CONSUMER = 0xA3,
    MD_SND_CMD_SEND_SYSTEM   = 0xA4,
    MD_SND_CMD_SEND_FN       = 0xA5,
    MD_SND_CMD_SEND_MOUSE    = 0xA8,
    MD_SND_CMD_SEND_DEVINFO  = 0xA9,
};
```

- `MD_SND_CMD_KB_LEN = 8`
- `MD_SND_CMD_NKRO_LEN = 14`
- `MD_SND_CMD_DEVINFO_LEN = 18`
- `MD_SND_CMD_MANUFACTURER_LEN = 46`
- `MD_SND_CMD_PRODUCT_LEN = 46`

### 9.4 移植到 Max102 需要做的事（已大幅收敛）

| # | 事项 | 状态 |
|---|---|---|
| 1 | 无线模块型号 | ✅ **Freqchip FR8003A**（用户提供） |
| 2 | UART 协议是否符合 `md` 命令集 | ✅ **完全符合**，逐字节交叉验证 |
| 3 | UART 引脚 | 🟡 固件推 **PC10/PC11**，待万用表确认 |
| 4 | 直接复用 `keyboards/westberry/wireless/` | ✅ 可以，无需自写 transport |
| 5 | 电量 | ✅ 已还原：`0xA6 0x53` 查询 → `0x5C <0-100>` 返回 |
| 6 | 充电状态 | 🟡 需确认 X14076 的 CHRG/STDBY 接谁 |

---

## 10. 两条移植路线

### 路线 A：只做有线版（推荐起步）

**工作量：2-3 天**

```
优点：难度低，立刻可用
缺点：三模失效，变成纯有线键盘
```

需要做的：

1. 万用表测 6 row × 19 col 引脚映射
2. 确认 RGB LED 协议（WS2812？）
3. 抄 `monsgeek/m1` 结构建 `keyboards/weikav/max102/`
4. 写 `keyboard.json`（matrix_pins / rgb_matrix / processor）
5. 生成 `rgb_matrix` 的 LED 位置数组（104 颗）
6. 编译、刷入、测试

### 路线 B：完整三模（长期）

**工作量：2-4 周（协议障碍已消除，实际剩余 ~1-2 周）**

```
优点：保留全部功能
缺点：仍需测引脚
```

> ✅ **原本最大的障碍已解决**：无线协议不是"未知、需逻辑分析仪"。
> UART3 @115200 + `md` 编解码**已从固件完整还原**，并与
> `WestberryTech/qmk_westberry` 及 `dot-agi/fr8003-re` 双向交叉验证。
> 详见 [`BATTERY.md`](BATTERY.md)。

在路线 A 基础上加：

1. ~~拆无线模块屏蔽罩识别型号~~ → ✅ 已确认 **FR8003A**
2. ~~逻辑分析仪抓 UART~~ → ✅ 协议已知（115200 8N1，`md` 编解码）
3. ✅ 直接接入 `keyboards/westberry/wireless/`
4. 实现 `DEV BT1-5` / `DEV 2.4G` / `DEV USB` 键码
5. 实现电量查询（`HS_BATQ`）＋ **上报给主机**（见 [`BATTERY.md`](BATTERY.md)）
6. 低功耗调优（10000mAh 电池，休眠电流要压到 μA 级）

---

## 11. 安全须知

### 11.1 已具备的恢复手段

| 手段 | 可用性 | 说明 |
|---|---|---|
| ROM DFU | ✅ | 按住 FN+右Shift+ESC，`wb32-dfu-updater` 刷回 |
| 原厂固件备份 | ✅ | `max102_stock_256k.bin`（MD5 已验证） |
| SWD 调试口 | ⚠️ | 能连 core，但无 OpenOCD flash 驱动 |
| EEPROM 配置备份 | ✅ | `backup_*.json`（5 层 keymap + 宏） |

### 11.2 风险点

| 风险 | 后果 | 规避 |
|---|---|---|
| 擦除 ROM bootloader 区 | **变砖**，无 OpenOCD 可救 | 永远只操作 `0x08000000` 起的区域 |
| 刷了错的固件 | 键盘无响应 | 有备份，可 DFU 刷回 |
| 无线模块固件被覆盖 | 三模失效 | 不要碰无线模块的 Flash |
| `-Z` 参数给错 | 读不全 / 读越界 | 固定用 `262144` |

### 11.3 刷回原厂固件

```bash
cd C:\Users\bx129\wb32tool

# 1. 进 DFU：按住 FN → 按住右 Shift → 点 ESC
# 2. 确认设备
wb32-dfu-updater_cli.exe -l
#    应显示: Found DFU: [0x342D:0xDFA0] ...

# 3. 刷回
wb32-dfu-updater_cli.exe -D "C:\path\to\max102_stock_trimmed.bin" -s 0x08000000

# 4. 复位
wb32-dfu-updater_cli.exe -R
```

---

## 12. 附：所有工具命令速查

```bash
# ===== DFU 操作 =====
wb32-dfu-updater_cli.exe -l                          # 列 DFU 设备
wb32-dfu-updater_cli.exe -U out.bin -Z 262144        # 全片读取（备份）
wb32-dfu-updater_cli.exe -D fw.bin -s 0x08000000     # 写入固件
wb32-dfu-updater_cli.exe -R                          # 复位

# ===== VIA 配置操作（只读） =====
python probe_max102.py      # 探测 + dump keymap
python backup_config.py     # 完整备份（keymap + 宏）
python decode_keymap.py     # 生成可读键位表

# ===== 驱动安装（管理员） =====
cd C:\Users\bx129\wb32tool\wb_dfu_usb_driver_v1.0.0.0
dpinst_amd64.exe            # 安装 WinUSB 驱动
dpinst_amd64.exe /u wb_device_in_dfu_mode.inf   # 卸载
```

---

## 13. 参考资料

| 资源 | 链接 |
|---|---|
| 官方软件下载页 | https://weikav.com/waikv-software/ |
| 官方在线驱动 | https://weikavmax102.hsgaming.cn/ |
| QMK 违规名单 | https://docs.qmk.fm/license_violations |
| QMK issue #24085 | https://github.com/qmk/qmk_firmware/issues/24085 |
| WB32 DFU 工具 | https://github.com/WestberryTech/wb32-dfu-updater |
| WB32 tri-mode QMK | https://github.com/WestberryTech/qmk_westberry/tree/tri-mode |
| QMK WB32 支持 | `platforms/chibios/mcu_selection.mk` |
| MonsGeek M1 参考 | `keyboards/monsgeek/m1` |
| 官方 VIA JSON | Google Drive `1lwphtjmT30NadFdWSNm72u7c65urxBe9` |

---

## 14. 免责声明

本项目为**个人硬件研究**，所有固件读取均在自己拥有的设备上进行。

- 固件文件**不包含在本仓库**（版权归 LEKU / Weikav 所有）
- 刷机有风险，**后果自负**
- 拆机将使保修失效
- 不要商用，不要用于仿制

如果 Weikav 官方愿意开源，请直接联系他们：
`support@weikav.com`
