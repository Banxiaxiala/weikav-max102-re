# Weikav MAX102 — 固件补丁 + 配置工具

[![QMK](https://img.shields.io/badge/QMK-VIA%20v12-blue)](https://qmk.fm)
[![MCU](https://img.shields.io/badge/MCU-WB32FQ95%20Cortex--M3-orange)]()
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

维咖 MAX102（Weikav MAX102）三模无线机械键盘的**电量上报补丁**与**配置工具**。

> 厂商 Weikav 在 [QMK 违规名单](https://docs.qmk.fm/license_violations)上，不提供源码。
> 本项目通过反编译原厂固件，**在原厂固件基础上做过最小二进制修改**，让键盘能把电量
> 告诉电脑。原厂 19 条 VIA 命令**一个字节都没动**。

---

## 目录

- [这个仓库有什么](#这个仓库有什么)
- [原厂固件 vs 补丁固件](#原厂固件-vs-补丁固件)
- [怎么刷](#怎么刷)
- [怎么获取电量](#怎么获取电量)
- [配置工具](#配置工具)
- [相关项目](#相关项目)
- [免责声明](#免责声明)

---

## 这个仓库有什么

**只有三样东西**，clone 下来约 1 MB：

```
firmware/               原厂固件 + 补丁固件
  max102_stock_256k.bin       262 KB  折腾前的完整备份（回滚用）
  max102_stock_trimmed.bin     69 KB  原厂，实际刷机启动区
  max102_patched_battery.bin   69 KB  补丁版：加了 cmd 20 读电量
  max102_patched_full.bin      69 KB  补丁版：电量 + 附加功能
  FIRMWARE_BACKUP_INFO.json           备份时的设备信息与校验

web/                    配置工具（网页版，单文件无依赖）
  index.html                  完整配置界面
  device.json                 设备定义（矩阵/灯效/键码）
  keymap_default.json         出厂键位快照（没连设备也能预览）

dist/                   打包好的 Windows 程序
  MAX102Config.exe            约 250 KB，双击即用
```

> 分析文档、反编译产物、构建脚本**不在此仓库**。
> 这个仓库是给「我只想刷机和配置」的人用的。

---

## 原厂固件 vs 补丁固件

这是本仓库最重要的部分。**两者只差一个 VIA 命令。**

### 一张表看清区别

| | 原厂 `max102_stock_trimmed.bin` | 补丁 `max102_patched_battery.bin` |
|---|---|---|
| **VIA 协议版本** | v12 | v12（不变） |
| **原厂 19 条命令** | 全部可用 | **全部可用，零改动** |
| **改键 / 灯效 / 宏** | ✅ 支持 | ✅ 支持 |
| **2.4G 无线配置** | ✅ 支持 | ✅ 支持 |
| **蓝牙配置** | ❌ 不支持 | ❌ 不支持 |
| **`cmd 6` 查电量** | 回 `06 00 00 00 00 ...`（**全 0**） | 同样全 0（保持原样） |
| **`cmd 20` 查电量** | 越界，回 `0xFF` ❌ | **返回电量 0-100** ✅ |
| **键盘 LED 电量柱** | ✅ 10 颗灯 | ✅ 不变 |
| **进 DFU 刷机** | FN+RShift+ESC | 同左 |

### 到底改了什么

**只加了一条命令，不删不改任何原有功能。**

原厂固件里 VIA 命令号 `20`（`0x14`）是**越界**的：主控收到它会直接回
`0xFF`，因为厂家只用到了 1–19 号。

我们做的事情：

1. 把 `cmd 20` 的响应接上内存里现成的电量变量（`0x20000C80`，范围 0–100）
2. 因为原厂的命令跳转表是 8 位偏移（跳不过 ~510 字节），换成了 32 位指针表
3. 顺带修正一个跳转表项，让 `cmd 6` 的原有行为保持完全一致

字节层面：**共 100 个字节不同，分布在 25 个区间**。

| 区域 | 偏移（文件内） | 改了什么 |
|---|---|---|
| 命令分发表 | `0xB678`–`0xB687` | 8 位偏移表 → 32 位指针表 |
| `cmd 20` 新函数 | `0xFD82`–`0xFD9D` | 读取电量变量并填响应 |
| 指针表实体 | `0x10CA8`–`0x10CF7` | 20 个函数指针 |

其余 69532 个字节（**99.86%**）完全一致：键位数据区、USB 描述符、
灯效表、宏缓冲、全部原厂代码逻辑一个字节都没动。

> 想验证差异，自己跑：
> ```bash
> cmp -l max102_stock_trimmed.bin max102_patched_battery.bin | wc -l
> # 输出：100
> ```

### 为什么不能改 `cmd 6`

`cmd 6` 是原厂的「读键盘参数」命令，键盘、鼠标、消费者控制等 6 个 HID 集合
都共用这套协议。改它的返回布局会**破坏现有工具**（包括官方的 VIA）。
所以补丁选了空号 `20`，完全不碰原厂已有的东西。

> 想验证差异，自己跑：
> ```bash
> cmp -l max102_stock_trimmed.bin max102_patched_battery.bin | wc -l
> ```
> 差异字节数只有两位数量级，全部集中在跳转表和新增代码处，键位数据区、
> USB 描述符、灯效表全部逐字节相同。

---

## 怎么刷

### 需要

- Windows
- [WB32 DFU 刷机工具](https://github.com/WestberryTech/wb32-dfu-updater/releases)
  （`wb32-dfu-updater_cli.exe`）
- **USB 线**（刷机必须插线，2.4G / 蓝牙都刷不了）

### 步骤

```bat
rem 1. 键盘进 DFU：按住 FN → 按住右 Shift → 点一下 ESC
rem    （指示灯会灭，设备管理器出现 WB32 DFU 设备）

rem 2. 刷补丁
wb32-dfu-updater_cli.exe -t WB32 -D max102_patched_battery.bin

rem 3. 拔插一次 USB，让键盘重启
```

### 回滚

```bat
wb32-dfu-updater_cli.exe -t WB32 -D max102_stock_trimmed.bin
```

**刷之前强烈建议先自己备份一遍**，别完全信仓库里的文件（虽然它们是从实机读的）：

```bat
wb32-dfu-updater_cli.exe -t WB32 -U my_backup.bin
```

---

## 怎么获取电量

电量有三条通路，**情况完全不同**，别混：

### 通路对比

| 通路 | 不需要 USB 线 | 需要刷补丁 | 谁在读 |
|---|---|---|---|
| **2.4G 接收器** | ✅ | ✅ **必须** | VIA `cmd 20` |
| **USB 有线** | ❌ | ✅ **必须** | VIA `cmd 20` |
| **蓝牙** | ✅ | ❌ 不需要 | 系统属性 / BLE GATT |

### 2.4G / USB：走 VIA `cmd 20`

刷了补丁之后，键盘会响应：

```
请求（33 字节，第 0 字节是 report id 占位）：
  00 14 00 00 ...

响应：
  00 14 00 00 64 02 01 01 ...
```

| 偏移 | 含义 | 值 |
|---|---|---|
| `[1]` | 命令码 | `0x14` = 20 |
| `[4]` | **电量百分比** | `0x00`–`0x64`（0–100） |
| `[5]` | 连接状态 | `0` 未初始化 / `1` 配对中 / `2` 已连接 / `3` 已断开 / `4` 被拒绝 |
| `[6]` | 无线模块版本 | 当前为 `1` |
| `[7]` | 指示灯位 | bit0 = Caps Lock |

**实测样本**（2.4G 下）：

```
14 00 00 00 64 02 01 01
             │  │  │  └─ Caps 开
             │  │  └──── 模块 v1
             │  └─────── 已连接
             └────────── 100%
```

**Python 示例**（实测可跑）：

```python
import hid

# 找 VIA 接口（usagePage 0xFF60 / usage 0x61）
devs = [d for d in hid.enumerate(0x342D, 0xE537)
        if d["usage_page"] == 0xFF60 and d["usage"] == 0x61]
d = hid.device()
d.open_path(devs[0]["path"])

# ⚠️ 必须补一个 0 在最前面（report id 占位），共 33 字节。
#    直接发 [0x14]+32个0 会被当成无 report id 的错误帧，回 0xFF。
d.write([0] + [0x14] + [0] * 31)
r = d.read(33, timeout_ms=600)

battery = r[4]          # 0-100
state   = r[5]          # 2 = 已连接
print(f"电量 {battery}%  状态 {state}")
# 实测输出: 电量 100%  状态 2
```

> 🔑 **这个 0 不能省**。HID 报告的第一个字节永远是 report id；
> 本设备声明为 0（无编号），但**仍占一个字节**。填错会导致固件
> 把命令码当 report id 解读，直接回 `0xFF`。

> ⚠️ **注意**：原厂固件的 `cmd 6` 读电量会回全 0。那是「读键盘参数」命令，
> 不是电量命令。**只有 `cmd 20` 能给电量，而且必须刷补丁。**

### 蓝牙：不需要补丁，系统自己就有

蓝牙模式下电量走 **BLE 标准 Battery Service**，跟补丁无关：

```
GATT 服务 0x180F
  └─ 0x2A19  Battery Level   [Read, Notify]
```

Windows / Android 会自动订阅并在「设置 → 蓝牙」里显示百分比。

程序里读的话，**最省事的办法是直接问 Windows**（不用连 GATT）：

```
PnP 设备属性 {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2  →  电量百分比
```

即 `DEVPKEY_Bluetooth_Battery`。C# / Python 都能读，毫秒级返回。

```python
# 纯 ctypes，无第三方依赖（实测输出 ('MAX102-BT1', 100)）
import ctypes
import ctypes.wintypes as wt
import winreg

BATTERY_FMTID = "{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"
BATTERY_PID = 2


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


class DEVPROPKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", ctypes.c_ulong)]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("ClassGuid", GUID),
                ("DevInst", wt.DWORD),
                ("Reserved", ctypes.POINTER(ctypes.c_ulong))]


setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
setupapi.SetupDiGetClassDevsW.restype = wt.HANDLE
setupapi.SetupDiEnumDeviceInfo.argtypes = [
    wt.HANDLE, wt.DWORD, ctypes.POINTER(SP_DEVINFO_DATA)]
setupapi.SetupDiGetDeviceInstanceIdW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), wt.LPWSTR, wt.DWORD,
    ctypes.POINTER(wt.DWORD)]
setupapi.SetupDiGetDevicePropertyW.argtypes = [
    wt.HANDLE, ctypes.POINTER(SP_DEVINFO_DATA), ctypes.POINTER(DEVPROPKEY),
    ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p, wt.DWORD,
    ctypes.POINTER(wt.DWORD), wt.DWORD]
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wt.HANDLE]

ENUM_KEY = "SYSTEM\\CurrentControlSet\\Enum\\"


def get_battery_percent():
    """返回 (设备名, 电量%)，找不到返回 None"""
    flags = 0x02 | 0x04
    h = setupapi.SetupDiGetClassDevsW(None, None, None, flags)
    if not h or h == wt.HANDLE(-1).value:
        return None
    try:
        did = SP_DEVINFO_DATA()
        did.cbSize = ctypes.sizeof(did)
        i = 0
        while setupapi.SetupDiEnumDeviceInfo(h, i, ctypes.byref(did)):
            i += 1
            buf = ctypes.create_unicode_buffer(1024)
            setupapi.SetupDiGetDeviceInstanceIdW(
                h, ctypes.byref(did), buf, 1024, None)
            iid = buf.value
            if not iid.upper().startswith("BTHLE"):
                continue

            key = DEVPROPKEY()
            ctypes.windll.ole32.CLSIDFromString(
                ctypes.c_wchar_p(BATTERY_FMTID), ctypes.byref(key.fmtid))
            key.pid = BATTERY_PID

            ptype = ctypes.c_ulong()
            data = ctypes.create_string_buffer(64)
            ok = setupapi.SetupDiGetDevicePropertyW(
                h, ctypes.byref(did), ctypes.byref(key),
                ctypes.byref(ptype), data, 64, None, 0)
            if ok and ptype.value == 3:
                try:
                    with winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE, ENUM_KEY + iid) as k:
                        name = winreg.QueryValueEx(k, "FriendlyName")[0]
                        if ";" in name:
                            name = name.rsplit(";", 1)[-1]
                except OSError:
                    name = iid
                return name, data.raw[0]
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(h)
    return None


print(get_battery_percent())
```


> 注意：这个属性只对**蓝牙**设备有。2.4G 下 Windows 不显示电量（没有 GATT），
> 得走上面的 `cmd 20`。

### 为什么两条路差这么多

电量**来源相同**（都是无线模块 FR8003A 测的），但暴露方式完全不同：

| | 蓝牙 | 2.4G / USB |
|---|---|---|
| 机制 | BLE GATT 标准服务 | UART 私有协议 → VIA 命令 |
| 需要主动问吗 | ❌ 不用，系统自动订阅 | ✅ **必须**发 `cmd 20` |
| 不打补丁能看到吗 | ✅ 能 | ❌ 不能（厂家只点了 10 颗 LED） |

实测验证：2.4G 下**不发任何命令，监听 8 秒收到 0 个包** —— 不问不说。

> 厂家固件收到无线模块发来的电量后，**只点亮键盘上的 10 颗 LED 做电量柱，
> 从不告诉电脑**。补丁补的就是这一步。

---

## 配置工具

`dist/MAX102Config.exe`（约 250 KB，单文件，零依赖）

### 能做什么

- **2.4G 无线改键**：5 层全支持，不需要插线
- **灯效调节**：亮度 / 速度 / 效果 / 颜色
- **电量显示**：走 `cmd 20`
- **没连设备也能看**：内置出厂键位快照，打开就能看到完整布局
- **按键音效**：WebAudio 实时合成（五声 / 半音 / 随机三种音阶）
- **层锁**：默认只读，防止误改层 0 和 BOOT 层

### 怎么用

双击 `MAX102Config.exe` → 浏览器自动打开 → 点「连接键盘」→ 选 `MAX102-2.4G`

> 首次会弹设备授权框，授权一次即可（按浏览器 profile 记住）。

### 为什么是「exe 打开浏览器」

WebHID 只在**安全上下文**可用：

| 打开方式 | WebHID |
|---|---|
| `file:///...` 双击 html | ❌ 浏览器直接禁用 |
| `http://127.0.0.1` | ✅ |

所以哪怕页面完全自包含，也必须从本地端口提供。exe 做的事就是：
**起一个只监听 127.0.0.1 的迷你 HTTP 服务 → 打开浏览器 → 托盘驻留**。

不需要 Python、不需要 Node、不需要联网。

### 已知限制

| 限制 | 说明 |
|---|---|
| 蓝牙下不能配置 | 蓝牙通道没有 VIA 接口（7 个 HID 集合里没有 `0xFF60/0x61`） |
| 需要 Chromium 系浏览器 | Firefox / Safari 不支持 WebHID |
| 灯效颜色看灯效 | 彩虹/循环类灯效自己跑色相，改颜色无效（工具会自动切到「单点反应」） |
| DFU 按钮无效 | 原厂固件 `cmd 11` 是假实现，进 DFU 只能按键 |

---

## 相关项目

### 外设电量（托盘监控工具）

> 📌 **仓库地址待补充** —— 该项目目前尚未发布，发布后在此填写。

一个托盘小工具，**一个图标同时显示鼠标 / 耳机 / 键盘的电量**。

它读 MAX102 电量的方式和本项目完全对应：

- **2.4G 模式** → 发本项目补丁提供的 `cmd 20`，拿到百分比 + 连接状态
- **蓝牙模式** → 读 Windows 的 `DEVPKEY_Bluetooth_Battery` 系统属性

```
托盘监控程序  ──┬── 2.4G dongle  ──→ VIA cmd 20 ──→ 本补丁固件 ✅
                └── 蓝牙          ──→ 系统 PnP 属性 ──→ FR8003A 模块 ✅
```

**两个项目的关系**：

- 想让托盘工具在 **2.4G 模式**下显示电量 → **必须刷本项目的补丁固件**
- 只用**蓝牙模式** → 不用刷固件，托盘工具直接能读

> 如果你只想看电量、不想折腾固件 → 用蓝牙模式 + 那个托盘工具就够了。
> 想 2.4G 下也显示，或者想在无线下改键 → 刷本项目的补丁。

---

## 免责声明

- 固件补丁是**二进制修改**，理论上有变砖风险。虽然实测稳定，但请自行评估。
- 刷机前请**自行备份**原厂固件。仓库里的 `max102_stock_256k.bin` 来自实机读取，
  但不同批次可能有差异。
- 本项目与原厂（Weikav / 维咖）无关，不含任何厂商私有源码。
- 原厂固件版权归厂商所有，此处仅作**备份与互操作性研究**用途。

---

## 许可

本仓库的补丁、配置工具与文档：**MIT**

原厂固件二进制：版权归维咖所有，此处仅为备份用途。
