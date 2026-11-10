# Weikav MAX102 — QMK Hardware Reverse Engineering

[![QMK](https://img.shields.io/badge/QMK-WB32FQ95-blue)](https://qmk.fm)
[![VIA](https://img.shields.io/badge/VIA%20protocol-v12-green)]()
[![MCU](https://img.shields.io/badge/MCU-WB32FQ95%20Cortex--M3-orange)]()

维卡 MAX102（Weikav MAX102）三模无线机械键盘的**硬件与固件逆向工程**记录。

所有数据来自**实机读取**，不是网络传闻，不是猜测。

---

## 🔍 一句话结论

这是一块**真 QMK 键盘**（VIA 协议 v12，主控 WB32FQ95），固件可以完整读取和备份，
**但厂商 Weikav 在 QMK 违规名单上，不提供源码**。

| 问题 | 答案 |
|---|---|
| 是 QMK 键盘吗？ | ✅ 是，协议版本 12 |
| 主控是什么？ | WB32FQ95（Westberry，Cortex-M3，256KB Flash） |
| QMK 主线支持吗？ | ✅ 支持 MCU，但**这块板子没移植** |
| 官方给固件/源码吗？ | ❌ 都不给（在 QMK 违规名单上） |
| 固件能备份吗？ | ✅ **能**，ROM DFU 直接裸读 |
| 能刷第三方固件吗？ | ⚠️ 技术上可行，三模功能难保 |
| 刷坏了能救吗？ | ✅ 双重保险（ROM DFU + SWD 焊盘） |

---

## 📖 完整分析

详细报告见 **[ANALYSIS.md](ANALYSIS.md)**，包含：

- 硬件识别（PCB 丝印、主控、SWD、RGB）
- 固件读取方法与校验结果
- 固件内部结构（字符串、向量表、工具链）
- VIA 协议完整命令集
- **全部 5 层键位表（实读）**
- 官方 VIA JSON 的缺陷清单
- QMK 移植可行性评估
- 三模无线架构分析
- 刷机安全须知

---

## 🛠 工具脚本

三个 Python 脚本，全部**只读**，不会写入键盘：

| 脚本 | 功能 |
|---|---|
| [`probe_max102.py`](probe_max102.py) | 探测设备、读取协议版本、dump keymap |
| [`backup_config.py`](backup_config.py) | 完整备份 keymap + 宏 + 参数 |
| [`decode_keymap.py`](decode_keymap.py) | 把 raw dump 解码成可读键位表 |

### 依赖

```bash
pip install hidapi
```

### 用法

```bash
# 1. 键盘用 USB 线连接，电源开关 ON，按 FN+T 切有线模式
# 2. 探测
python probe_max102.py

# 3. 备份
python backup_config.py

# 4. 解码
python decode_keymap.py     # 输出 keymap_readable.txt
```

输出示例：

```
PROTOCOL_VERSION : 12
FIRMWARE_VERSION : 0.0.0
LAYER_COUNT      : 5
备份 keymap: 5 层 x 6 x 19
  layer 0: 228 bytes, 非零键码 101 个
  ...
MACRO_COUNT      : 16
MACRO_BUF_SIZE   : 1984
```

---

## 🔧 固件备份（DFU）

### 进 DFU 的方法

固件里藏了一个隐藏的第 5 层，键位链是：

```
Layer 0  matrix(5,9)  = MO(1)      ← FN 键
Layer 1  matrix(4,12) = MO(4)      ← 右 Shift 位置
Layer 4  matrix(0,0)  = QK_BOOT    ← ESC 位置
```

**按住 FN → 按住右 Shift → 点一下 ESC**

### 读取全片 256KB

```bash
# 装工具
# https://github.com/WestberryTech/wb32-dfu-updater/releases

wb32-dfu-updater_cli.exe -l
# Found DFU: [0x342D:0xDFA0] ver=0x0100

wb32-dfu-updater_cli.exe -U max102_stock_256k.bin -Z 262144

wb32-dfu-updater_cli.exe -R      # 复位回正常模式
```

**实测 0.6 秒读完全片。**

### 本次备份的校验值

| 项目 | 值 |
|---|---|
| 大小 | 262,144 B |
| MD5 | `4014df74ebde3479afcfc90460eae28a` |
| SHA256 | `ac842a1134477ad2dc1085b9429fdef0c0cdc0d9554ccecbb51a75968ef9d1b5` |
| 二次读取 | MD5 完全一致 ✅ |
| 有效长度 | 0x10D33（约 68KB），其后全 0x00 |

> ⚠️ **固件二进制不在本仓库**（版权归 LEKU / Weikav）。校验值在此供比对。

---

## 🧩 关键发现

### 1. 隐藏的 BOOT 层

`LAYER_COUNT=5`，但网页驱动只暴露 4 层。第 5 层只有 ESC 位置是 `QK_BOOT`，
这是官方的隐藏刷机入口。

### 2. 固件支持 5 个蓝牙通道

从固件里挖出的字符串：

```
MAX102-BT1   MAX102-BT2   MAX102-BT3   MAX102 BT4   MAX102 BT5
MAX102-2.4G
LEKU                      ← 实际制造商
```

但官方 VIA 只暴露 `DEV BT1/2/3`，**后两个通道被隐藏**。

### 3. 官方 VIA JSON 落后于固件

固件用到 5 个没声明的自定义键码：

```
0x7E09  0x7E0A  0x7E0C  0x7E0D  0x7E0E
```

这 5 个功能在 VIA 界面里**选不到**。

### 4. 三模走 UART，不是主控直连

固件里**没有任何蓝牙栈代码**，只有设备名字符串。
说明架构是：

```
USB ──► WB32FQ95 ──UART──► 无线模块 ──► BT / 2.4G
         (键盘主控)          (待识别)
```

这正是 [`WestberryTech/qmk_westberry`](https://github.com/WestberryTech/qmk_westberry/tree/tri-mode)
的 `tri-mode` 分支所支持的架构。

---

## 🚧 为什么不能直接编译 QMK

| 障碍 | 难度 | 说明 |
|---|---|---|
| MCU 支持 | ✅ 无 | QMK 主线完整支持 WB32FQ95 |
| 矩阵引脚 | 🟡 中 | 需万用表测 6×19 |
| RGB LED 协议 | 🟡 中 | 需确认 WS2812 还是私有 |
| **无线 UART 协议** | 🔴 高 | 需逻辑分析仪逆向 |
| **QMK PR 被拒** | 🟡 中 | Weikav 在违规名单 |

### QMK 违规名单

[`docs/license_violations.md`](https://docs.qmk.fm/license_violations) 第 52 行：

```
| Weikav | Selling tri-mode boards based on QMK without sources, just `via.json` provided. |
```

来自 [issue #24085](https://github.com/qmk/qmk_firmware/issues/24085) ——
QMK 维护者已暂停 Weikav 的所有 PR，直到交出全部源码。

**绕开方式**：放进自己的 fork（GPLv3 允许），或提交到 `qmk_westberry` 的 tri-mode 分支。

---

## 🗺 移植路线

### 路线 A：只做有线（2-3 天）

难度低，立刻可用，但三模失效。

1. 测出 `matrix_pins`（6 row × 19 col）
2. 确认 RGB LED 类型
3. 抄 [`keyboards/monsgeek/m1`](https://github.com/qmk/qmk_firmware/tree/master/keyboards/monsgeek/m1) 的结构
4. 写 `keyboard.json`
5. 生成 104 颗 LED 的位置数组
6. 编译刷入

### 路线 B：完整三模（2-4 周）

保留全部功能，需要逻辑分析仪。

1. 拆无线模块看型号
2. 抓 UART 波形
3. 对照 `keyboards/westberry/wireless/md_raw.c` 验证协议
4. 接入 Westberry 的 wireless 模块
5. 实现 `DEV BT1-5` / `DEV 2.4G` / `HS_BATQ`
6. 低功耗调优

---

## ✅ 同 MCU 的 QMK 参考实现

这些板子都用 WB32FQ95，可以直接抄结构：

- [`keyboards/monsgeek/m1`](https://github.com/qmk/qmk_firmware/tree/master/keyboards/monsgeek/m1)
- `keyboards/monsgeek/m2` / `m3` / `m5` / `m6`
- `keyboards/gmmk`
- `keyboards/akko`
- `keyboards/inland`

---

## ⚠️ 免责声明

本项目为**个人硬件研究**。

- 所有固件读取均在**自己拥有的设备**上进行
- **固件文件不包含在本仓库**，版权归 LEKU / Weikav 所有
- 刷机有风险，**后果自负**
- 拆机将使保修失效
- 请勿商用，请勿用于仿制

希望 Weikav 官方能开源：`support@weikav.com`

---

## 📜 License

本仓库的**文档和脚本**以 MIT 协议发布。
固件相关的一切权利归原厂所有。
