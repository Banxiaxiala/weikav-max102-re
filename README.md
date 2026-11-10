# Weikav MAX102 — 硬件与固件逆向

[![QMK](https://img.shields.io/badge/QMK-VIA%20v12-blue)](https://qmk.fm)
[![MCU](https://img.shields.io/badge/MCU-WB32FQ95%20Cortex--M3-orange)]()
[![License](https://img.shields.io/badge/License-MIT%20%2B%20GPL--2.0-green)](docs/10-版权声明.md)

维咖 MAX102（Weikav MAX102）三模无线机械键盘的硬件与固件逆向工程记录，
包含**已实机验证的二进制补丁**（电量上报）。

> 所有数据来自**实机读取与反编译**，不是网络传闻，不是猜测。
> 每个结论都标注了证据来源，不确定的地方明确标注"待核实"。
>
> **范围说明**：本项目只做原厂固件的研究与二进制修改，**不涉及 QMK 移植**。

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
| 官方给固件/源码吗？ | ❌ 都不给（在 QMK 违规名单上） |
| 固件能备份吗？ | ✅ 能，ROM DFU 直接裸读 |
| 能改固件吗？ | ✅ 能，二进制补丁直接改原厂固件（已实现电量上报） |
| 刷坏了能救吗？ | ✅ 双重保险（ROM DFU + SWD 焊盘） |

---

## 文档

| 文档 | 内容 |
|---|---|
| **[调试指南.md](docs/03-调试指南.md)** | **调试入口全图** —— DFU / SWD / UART 三层，含救砖流程与常见故障速查 |
| **[分析报告.md](docs/02-分析报告.md)** | 完整分析报告 —— 硬件识别、固件读取、VIA 协议、5 层键位表 |
| **[电量链路.md](docs/06-电量链路.md)** | 电量链路完整还原 + 三条上报路线（含代码方案） |
| **[反汇编.md](docs/04-反汇编.md)** | Ghidra 反编译结果 —— 520 个函数、中断向量表、RAM 布局、字符串 |
| **[项目移交.md](docs/01-项目移交.md)** | 项目现状、环境配置、已确认事实清单、风险点 |
| **[硬件引脚.md](docs/05-硬件引脚.md)** | 矩阵 / UART / USB 引脚（全部从固件还原，不用万用表） |
| **[电量补丁方案.md](docs/07-电量补丁方案.md)** | 电量二进制补丁的完整设计与验证（**改固件的模版**） |
| **[待采集清单.md](docs/09-待采集清单.md)** | 下一个补丁缺什么、怎么测 |
| **[VIA协议.md](docs/08-VIA协议.md)** | VIA 命令号实测对照（官方驱动 vs 固件 vs 本地工具） |
| **[web/README.md](web/README.md)** | **本地 WebHID 工具使用说明** —— 改键 + 电量 + 灯效，不联网 |
| **[版权声明.md](docs/10-版权声明.md)** | ⚠️ **版权与使用声明 —— 使用前必读** |

---

## 目录结构

```
.
├── README.md                  本文件（唯一留在根目录的文档）
├── LICENSE                    MIT（不覆盖固件与 via.json）
│
├── docs/                      全部分析文档（按阅读顺序编号）
│   ├── 01-项目移交.md         项目现状、风险点（先读这个）
│   ├── 02-分析报告.md         完整分析报告
│   ├── 03-调试指南.md         调试入口（DFU / SWD / UART）
│   ├── 04-反汇编.md           反编译结果
│   ├── 05-硬件引脚.md         矩阵 / UART / USB 引脚
│   ├── 06-电量链路.md         电量链路与上报方案
│   ├── 07-电量补丁方案.md     电量二进制补丁设计
│   ├── 08-VIA协议.md          VIA 命令号实测对照
│   ├── 09-待采集清单.md       待采集清单
│   └── 10-版权声明.md         版权与使用声明
│
├── firmware/
│   ├── max102_stock_256k.bin  原厂固件全片 256KB（救命用）
│   ├── max102_stock_trimmed.bin  有效区 68KB（反编译 / 回退用）
│   ├── max102_patched_battery.bin  ★ 电量补丁固件（可刷）
│   └── FIRMWARE_BACKUP_INFO.json 校验记录
│
├── tools/
│   ├── probe_max102.py        探测设备、读协议版本、dump keymap
│   ├── backup_config.py       完整备份 keymap + 宏 + 参数
│   ├── decode_keymap.py       把 raw dump 解码成可读键位表
│   ├── read_battery.py        读电量 / 充电状态
│   ├── probe_24g.py           2.4G / 接收器通道下读电量（探活 + 汇总判定）
│   ├── patch_battery.py       电量二进制补丁工具
│   ├── keymap_readable.txt    工厂默认键位表（5 层全）
│   └── max102_via.json        厂商 VIA 定义
│
├── web/                       本地 VIA 工具（改键 + 电量 + 灯效）
│   ├── index.html             单文件 WebHID 前端
│   ├── device.json            设备定义（矩阵 / 布局 / 灯效通道）
│   └── README.md              使用说明
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

### 读电量（需先刷电量补丁，见 [电量补丁方案.md](docs/07-电量补丁方案.md)）

```bash
py -3.13 tools/read_battery.py          # 读一次
py -3.13 tools/read_battery.py -w 2     # 每 2 秒刷新
py -3.13 tools/read_battery.py --json   # 给其他程序用
```

### 本地改键 / 看电量（图形界面，推荐）

`web/` 是一个单文件 WebHID 前端，不联网、不依赖 `usevia.app`。
Chrome / Edge 直接打开 `web/index.html` 即可，详见 **[web/README.md](web/README.md)**：

- 改键：5 层（含隐藏 BOOT 层）全文读写，写前有读回验证
- 看电量：每 3 秒刷新（需先刷电量补丁）
- 灯效：亮度 / 效果 / 速度 / 颜色（HSV）

### 2.4G 模式能读吗（实测工具）

```bash
py -3.13 tools/probe_24g.py            # 枚举 HID → 探活 → 读电量 → 给结论
py -3.13 tools/probe_24g.py --json     # 机器可读
```

只发 GET 类命令（`cmd 1` / `cmd 6`），不写 EEPROM、不跳 bootloader。
要回答的是：**接收器会不会把 vendor HID 原样透传给主机**——这只能在实机上试。

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

详细步骤与救砖流程见 **[调试指南.md](docs/03-调试指南.md)**。

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

## 为什么不去移植 QMK

| 障碍 | 难度 | 说明 |
|---|---|---|
| **拿不到源码** | 🔴 **致命** | 厂商从未公开，Weikav 在违规名单 —— 光这一条就堵死了 |
| ~~MCU 支持~~ | ✅ 无 | QMK 主线完整支持 WB32FQ95 |
| ~~矩阵引脚~~ | ✅ 已解决 | 已从固件还原（[硬件引脚.md](docs/05-硬件引脚.md)） |
| ~~无线 UART 协议~~ | ✅ **已解决** | `md` 编解码已完整还原 |
| RGB LED 协议 | 🟡 中 | 需确认 WS2812 还是私有（改灯效才需要） |
| QMK PR 被拒 | 🟡 中 | Weikav 在违规名单 |

> 技术障碍其实都清得差不多了，**唯一真正堵死的是“没有源码”**。
> 所以本项目放弃移植，所有改动都通过二进制补丁直接写进原厂固件，见
> **[电量补丁方案.md](docs/07-电量补丁方案.md)**。

### QMK 违规名单

[`docs/license_violations.md`](https://docs.qmk.fm/license_violations) 第 52 行：

```
| Weikav | Selling tri-mode boards based on QMK without sources, just `via.json` provided. |
```

来自 [issue #24085](https://github.com/qmk/qmk_firmware/issues/24085) ——
QMK 维护者已暂停 Weikav 的所有 PR，直到交出全部源码。

**这直接决定了本项目的做法**：拿不到源码 → 不可能编译开源固件 →
只能在原厂二进制上打补丁。

---

## 怎么改固件

### 路线 A：二进制补丁（本项目采用，已实现）

不改原厂任何原有逻辑，只在已验证的空白区加 handler + 改一张跳转表。

1. 反编译定位命令分发器与数据地址（[反汇编.md](docs/04-反汇编.md)）
2. 在空白区写新 handler（汇编片段，43 字节）
3. 改表项把新命令挂上去
4. DFU 刷入，用 `tools/read_battery.py` 验证

已落地成果：**电量上报**（[电量补丁方案.md](docs/07-电量补丁方案.md)）。
下一步的工程清单见 [待采集清单.md](docs/09-待采集清单.md)。

### 路线 B：等厂商开源

拿到源码才能编译。目前无进展，不在本项目工作范围内。

---

## 改固件的通用流程

下一个功能（充电状态上报）会用同一套动作，只是改的点不同：

| 步 | 做什么 | 工具 |
|---|---|---|
| 1 | 定位要改的函数 / 表项 / 数据地址 | Ghidra（`scripts/*.java`） |
| 2 | 确认目标字节区可写（找空白区） | `tools/patch_battery.py` 里的校验逻辑 |
| 3 | 写 handler + 改表项 | 手工汇编 / Capstone 校验 |
| 4 | 生成补丁固件，二分校验 | `tools/patch_battery.py` |
| 5 | DFU 刷入 + 工具验证 | `wb32-dfu-updater_cli` + `tools/*.py` |
| 6 | 不对就刷回原厂 | `firmware/max102_stock_256k.bin` |

---

## 同 MCU 的 QMK 参考实现

这些板子都用 WB32FQ95，可作为**阅读反编译代码时的对照**（同样的外设库、
同样的寄存器布局），用来推断某个函数在干什么：

- [`keyboards/monsgeek/m1`](https://github.com/qmk/qmk_firmware/tree/master/keyboards/monsgeek/m1)
- `keyboards/monsgeek/m2` / `m3` / `m5` / `m6`
- `keyboards/gmmk`
- `keyboards/akko`
- `keyboards/inland`

---

## ⚠️ 免责声明

本项目为**个人硬件与固件研究**：读取、理解并**直接修改**自己拥有的设备上的固件。
**不做移植，不分发修改后的固件包。**

- `firmware/` 中的固件**版权归 LEKU / Weikav 所有**，作为 QMK 衍生作品推定为 **GPL-2.0**；
  **厂商从未公开对应源码**，故本仓库无法满足 GPL-2.0 第 3 条（见 **[版权声明.md](docs/10-版权声明.md)**）
- `tools/max102_via.json` 是厂商配置数据，不在 MIT 范围
- 刷机有风险，**后果自负**
- 拆机将使**保修失效**
- 锂电池操作不当有**起火风险**
- **请勿商用，请勿用于仿制**

权利人对收录内容有异议请开 Issue，确认身份后**立即移除**。

完整条款见 **[版权声明.md](docs/10-版权声明.md)**。

希望 Weikav 官方能开源：`support@weikav.com`

---

## 📜 License

本文档与脚本（`README.md`、`docs/*.md`、`tools/*.py`、`scripts/*.java`、`web/*`）以 **MIT** 协议发布。

`temp/` 目录里的东西（探测输出、配置备份、反编译产物）都是本机生成的临时文件，
已被 `.gitignore` 排除，不入库也不属于发布内容。

`firmware/*.bin` 推定为 **GPL-2.0**（QMK 衍生作品），但厂商从未公开源码，
因此无法满足 GPL-2.0 §3 —— 详见 [版权声明.md](docs/10-版权声明.md) 第 2 节。

`tools/max102_via.json` 许可状态不明，不在 MIT 覆盖范围内。

完整条款见 [版权声明.md](docs/10-版权声明.md)。
