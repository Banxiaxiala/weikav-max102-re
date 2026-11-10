# Weikav MAX102 — 硬件与固件逆向

[![QMK](https://img.shields.io/badge/QMK-VIA%20v12-blue)](https://qmk.fm)
[![MCU](https://img.shields.io/badge/MCU-WB32FQ95%20Cortex--M3-orange)]()
[![License](https://img.shields.io/badge/License-MIT%20%2B%20GPL--2.0-green)](docs/NOTICE.md)

维咖 MAX102（Weikav MAX102）三模无线机械键盘的硬件与固件逆向工程记录。

> 所有数据来自**实机读取与反编译**，不是网络传闻，不是猜测。
> 每个结论都标注了证据来源，不确定的地方明确标注"待核实"。

---

## 一句话结论

这是一块**真 QMK 键盘**（VIA 协议 v12，主控 WB32FQ95），固件可完整读取和备份，
**但厂商 Weikav 在 QMK 违规名单上，不提供源码**。

| 问题 | 答案 |
|---|---|
| 是 QMK 键盘吗？ | ✅ 是，VIA 协议版本 12 |
| 主控是什么？ | WB32FQ95（Westberry，Cortex-M3，256KB Flash） |
| 无线模块是什么？ | FR8003A（富芮坤 BLE5.1 + 2.4G SoC） |
| 主控与模块怎么连？ | UART3 @115200，Westberry `md` 协议 |
| QMK 主线支持吗？ | ✅ 支持 MCU，但这块板子没移植 |
| 官方给固件/源码吗？ | ❌ 都不给（在 QMK 违规名单上） |
| 固件能备份吗？ | ✅ 能，ROM DFU 直接裸读 |
| 能刷第三方固件吗？ | ⚠️ 技术上可行，三模功能难保 |
| 刷坏了能救吗？ | ✅ 双重保险（ROM DFU + SWD 焊盘） |

---

## 文档

| 文档 | 内容 |
|---|---|
| **[DEBUG.md](docs/DEBUG.md)** | **调试入口全图** —— DFU / SWD / UART 三层，含救砖流程与常见故障速查 |
| **[ANALYSIS.md](docs/ANALYSIS.md)** | 完整分析报告 —— 硬件识别、固件读取、VIA 协议、5 层键位表、QMK 移植评估 |
| **[BATTERY.md](docs/BATTERY.md)** | 电量链路完整还原 + 三条上报路线（含代码方案） |
| **[DISASSEMBLY.md](docs/DISASSEMBLY.md)** | Ghidra 反编译结果 —— 520 个函数、中断向量表、RAM 布局、字符串 |
| **[HANDOVER.md](docs/HANDOVER.md)** | 项目现状、环境配置、已确认事实清单、风险点 |
| **[NEEDED.md](docs/NEEDED.md)** | 还缺哪些硬件信息、怎么测、哪些其实不需要 |
| **[HARDWARE.md](docs/HARDWARE.md)** | 矩阵 / UART / USB 引脚（全部从固件还原，不用万用表） |
| **[PATCH_PLAN.md](docs/PATCH_PLAN.md)** | 电量二进制补丁的完整设计与验证 |
| **[VIA_PROTOCOL.md](docs/VIA_PROTOCOL.md)** | VIA 命令号实测对照（官方驱动 vs 固件 vs 本地工具） |
| **[NOTICE.md](docs/NOTICE.md)** | ⚠️ **版权与使用声明 —— 使用前必读** |

---

## 目录结构

```
.
├── README.md                  本文件（唯一留在根目录的文档）
├── LICENSE                    MIT（不覆盖固件与 via.json）
│
├── docs/                      全部分析文档
│   ├── DEBUG.md               调试入口（DFU / SWD / UART）
│   ├── ANALYSIS.md            完整分析报告
│   ├── BATTERY.md             电量链路与上报方案
│   ├── DISASSEMBLY.md         反编译结果
│   ├── HANDOVER.md            项目移交文档
│   ├── HARDWARE.md            矩阵 / UART / USB 引脚
│   ├── NEEDED.md              待采集清单
│   ├── PATCH_PLAN.md          电量二进制补丁设计
│   ├── VIA_PROTOCOL.md        VIA 命令号实测对照
│   └── NOTICE.md              版权与使用声明
│
├── firmware/
│   ├── max102_stock_256k.bin  原厂固件全片 256KB（救命用）
│   ├── max102_stock_trimmed.bin  有效区 68KB（反编译用）
│   └── FIRMWARE_BACKUP_INFO.json 校验记录
│
├── tools/
│   ├── probe_max102.py        探测设备、读协议版本、dump keymap
│   ├── backup_config.py       完整备份 keymap + 宏 + 参数
│   ├── decode_keymap.py       把 raw dump 解码成可读键位表
│   ├── read_battery.py        读电量 / 充电状态
│   ├── patch_battery.py       电量二进制补丁工具
│   ├── keymap_readable.txt    工厂默认键位表（5 层全）
│   └── max102_via.json        厂商 VIA 定义
│
├── scripts/
│   ├── Max102Post.java        Ghidra：建向量表符号 + 全段反汇编
│   └── ExportDecomp.java      Ghidra：导出 C 伪代码
│
└── temp/                      临时与本地产物（不进 git）
    ├── max102_info.json       探测器输出
    ├── backup_<时间戳>.json   EEPROM 配置备份
    └── ghidra_out/            Ghidra 反编译产物
```

---

## 快速开始

### 只读探测（不写入键盘）

```bash
pip install hidapi

# 前置：USB 连接 + 电源开关 ON + FN+T 切有线模式
python tools/probe_max102.py      # → temp/max102_info.json
python tools/backup_config.py     # → temp/backup_<时间戳>.json
python tools/decode_keymap.py     # → tools/keymap_readable.txt
```

> 产物位置：`temp/max102_info.json`（探测）、`temp/backup_<时间戳>.json`（备份）、
> `tools/keymap_readable.txt`（可读键位表）。临时产物统一落在 `temp/`，
> 已在 `.gitignore` 中排除。

三个脚本**只发 GET 类命令**，不写 EEPROM、不跳 bootloader。源码可逐行审计。
脚本内部用绝对路径定位仓库，**任意目录下运行都可以**。

预期输出：

```
PROTOCOL_VERSION : 12
FIRMWARE_VERSION : 0.0.0
LAYER_COUNT      : 5
备份 keymap: 5 层 x 6 x 19
  layer 0: 228 bytes, 非零键码 101 个
MACRO_COUNT      : 16
MACRO_BUF_SIZE   : 1984
```

### 读电量（需先刷电量补丁，见 PATCH_PLAN）

```bash
py -3.13 tools/read_battery.py          # 读一次
py -3.13 tools/read_battery.py -w 2     # 每 2 秒刷新
py -3.13 tools/read_battery.py --json   # 给其他程序用
```

### 固件备份（先做这个，再谈其他）

```bash
# 进 DFU：按住 FN → 按住右 Shift → 点一下 ESC
# 装工具：https://github.com/WestberryTech/wb32-dfu-updater/releases

wb32-dfu-updater_cli.exe -l
# Found DFU: [0x342D:0xDFA0] ver=0x0100

wb32-dfu-updater_cli.exe -U max102_stock_256k.bin -Z 262144
wb32-dfu-updater_cli.exe -R      # 复位回正常模式
```

**实测 0.6 秒读完全片。** 本仓库 `firmware/` 已收录校验过的副本：

| 项目 | 值 |
|---|---|
| 大小 | 262,144 B |
| MD5 | `4014df74ebde3479afcfc90460eae28a` |
| SHA256 | `ac842a1134477ad2dc1085b9429fdef0c0cdc0d9554ccecbb51a75968ef9d1b5` |
| 二次读取 | MD5 完全一致 ✅ |
| 有效长度 | `0x10D33`（约 68KB），其后全 `0x00` |

详细步骤与救砖流程见 **[DEBUG.md](docs/DEBUG.md)**。

---

## 关键发现

### 1. 隐藏的 BOOT 层

`LAYER_COUNT=5`，但网页驱动只暴露 4 层。第 5 层只有 ESC 位置是 `QK_BOOT`，
这是官方的隐藏刷机入口：

```
Layer 0  matrix(5,9)  = MO(1)      ← FN 键
Layer 1  matrix(4,12) = MO(4)      ← 右 Shift 位置
Layer 4  matrix(0,0)  = QK_BOOT    ← ESC 位置
```

**按住 FN → 按住右 Shift → 点一下 ESC**

### 2. 固件支持 5 个蓝牙通道

从固件里挖出的字符串：

```
MAX102-BT1   MAX102-BT2   MAX102-BT3   MAX102 BT4   MAX102 BT5
MAX102-2.4G
LEKU                      ← 实际制造商
```

但官方 VIA 只暴露 `DEV BT1/2/3`，**后两个通道被隐藏**。

> 注意 BT4/BT5 用空格而非连字符 —— 这是原厂的不一致，但证实了 5 个通道的存在。

### 3. 官方 VIA JSON 落后于固件

固件用到 `0x7E00`–`0x7E17` 共 24 个 QK_KB 键码，`via.json` 只声明到索引 8。
其中 5 个完全未声明，在 VIA 界面里**选不到**：

```
0x7E09  0x7E0A  0x7E0C  0x7E0D  0x7E0E
```

### 4. 三模走 UART，不是主控直连

固件里**没有任何蓝牙栈代码**，只有设备名字符串。架构是：

```
USB ──► WB32FQ95 ──UART3 @115200──► FR8003A ──► BT / 2.4G
         (键盘主控)   PC10/PC11        (无线 SoC)
```

协议是 Westberry 的 `md` 编解码，**已从固件完整还原**，并与
[`qmk_westberry`](https://github.com/WestberryTech/qmk_westberry/tree/tri-mode)
和 [`fr8003-re`](https://github.com/dot-agi/fr8003-re) 双向交叉验证。

### 5. HardFault 是死循环

反编译确认 NMI / HardFault / MemManage / BusFault / UsageFault **全部是默认弱符号**
（`b .`）。一旦触发硬件异常，固件无任何自救逻辑、不打印任何信息 ——
这就是刷机出错后只能靠 DFU / SWD 的原因。

---

## 为什么不能直接编译 QMK

| 障碍 | 难度 | 说明 |
|---|---|---|
| MCU 支持 | ✅ 无 | QMK 主线完整支持 WB32FQ95 |
| 矩阵引脚 | 🟡 中 | 需万用表测 6×19 |
| RGB LED 协议 | 🟡 中 | 需确认 WS2812 还是私有 |
| ~~无线 UART 协议~~ | ✅ **已解决** | `md` 编解码已完整还原 |
| QMK PR 被拒 | 🟡 中 | Weikav 在违规名单 |

### QMK 违规名单

[`docs/license_violations.md`](https://docs.qmk.fm/license_violations) 第 52 行：

```
| Weikav | Selling tri-mode boards based on QMK without sources, just `via.json` provided. |
```

来自 [issue #24085](https://github.com/qmk/qmk_firmware/issues/24085) ——
QMK 维护者已暂停 Weikav 的所有 PR，直到交出全部源码。

**绕开方式**：放进自己的 fork（GPLv3 允许），或提交到 `qmk_westberry` 的 tri-mode 分支。

---

## 移植路线

### 路线 A：只做有线（2-3 天）

难度低，立刻可用，但三模失效。

1. 测出 `matrix_pins`（6 row × 19 col）
2. 确认 RGB LED 类型
3. 抄 [`keyboards/monsgeek/m1`](https://github.com/qmk/qmk_firmware/tree/master/keyboards/monsgeek/m1) 的结构
4. 写 `keyboard.json`
5. 生成 104 颗 LED 的位置数组
6. 编译刷入

### 路线 B：完整三模（实际剩余 1-2 周）

保留全部功能。最大障碍已消除：

> ✅ 无线模块确认为 **FR8003A**，UART 协议（115200 8N1 + `md` 编解码）
> 已从固件完整还原，与 `qmk_westberry` / `fr8003-re` 双向交叉验证。
> **不需要逻辑分析仪。**

1. 实现 `DEV BT1-5` / `DEV 2.4G` / `HS_BATQ`
2. 电量上报（`0xA6 0x53` → `0x5C`，见 [BATTERY.md](docs/BATTERY.md)）
3. 低功耗调优
4. 可直接复用 `keyboards/westberry/wireless/`

---

## 同 MCU 的 QMK 参考实现

这些板子都用 WB32FQ95，可以直接抄结构：

- [`keyboards/monsgeek/m1`](https://github.com/qmk/qmk_firmware/tree/master/keyboards/monsgeek/m1)
- `keyboards/monsgeek/m2` / `m3` / `m5` / `m6`
- `keyboards/gmmk`
- `keyboards/akko`
- `keyboards/inland`

---

## ⚠️ 免责声明

本项目为**个人硬件研究**，所有固件读取均在**自己拥有的设备**上进行。

- `firmware/` 中的固件**版权归 LEKU / Weikav 所有**，作为 QMK 衍生作品推定为 **GPL-2.0**；
  **厂商从未公开对应源码**，故本仓库无法满足 GPL-2.0 第 3 条（见 **[NOTICE.md](docs/NOTICE.md)**）
- `tools/max102_via.json` 是厂商配置数据，不在 MIT 范围
- 刷机有风险，**后果自负**
- 拆机将使**保修失效**
- 锂电池操作不当有**起火风险**
- **请勿商用，请勿用于仿制**

权利人对收录内容有异议请开 Issue，确认身份后**立即移除**。

完整条款见 **[NOTICE.md](docs/NOTICE.md)**。

希望 Weikav 官方能开源：`support@weikav.com`

---

## 📜 License

本文档与脚本（`README.md`、`docs/*.md`、`tools/*.py`、`scripts/*.java`）以 **MIT** 协议发布。

`temp/` 目录里的东西（探测输出、配置备份、反编译产物）都是本机生成的临时文件，
已被 `.gitignore` 排除，不入库也不属于发布内容。

`firmware/*.bin` 推定为 **GPL-2.0**（QMK 衍生作品），但厂商从未公开源码，
因此无法满足 GPL-2.0 §3 —— 详见 [NOTICE.md](docs/NOTICE.md) 第 2 节。

`tools/max102_via.json` 许可状态不明，不在 MIT 覆盖范围内。

完整条款见 [NOTICE.md](docs/NOTICE.md)。
