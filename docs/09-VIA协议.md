# VIA 协议实测对照 —— 官方驱动 vs 固件 vs 本地工具

> 依据：官方 `MAX102json.zip`（含 `max102(1).json` + 说明 docx）、
> `usevia.app` 线上驱动源码、以及本仓库固件反汇编。
>
> 日期：2026-11-10

---

## 1. 官方资料核实结果

`MAX102json.zip` 内容：

| 文件 | 大小 | 结论 |
|---|---|---|
| `MAX102  json/max102(1).json` | 6,183 B | **与本仓库 `tools/max102_via.json` 逐字节完全一致** ✅ |
| `MAX102  json/MAX102-VIA软件说明.docx` | 495,602 B | 仅 3 行内容，且提到 `stars80.json`（厂家复用模板） |
| `MAX102  json/VIA网址.txt` | 19 B | `https://usevia.app/` |

**docx 全文：**

```
网站：https://usevia.app/ 确保这里打开状态
点击 load 选择 stars80.json
点击添加选择 STARS80 设备
完成
```

> 说明厂家只是把 STARS80 的文档改了产品名，实际要加载的是 `max102(1).json`。

---

## 2. 关键发现：官方驱动不使用 `cmd 6`

从 `usevia.app` 压缩源码里提取到命令枚举：

```js
e[e.DYNAMIC_KEYMAP_GET_KEYCODE = 4] = "DYNAMIC_KEYMAP_GET_KEYCODE"
e[e.DYNAMIC_KEYMAP_SET_KEYCODE = 5] = "DYNAMIC_KEYMAP_SET_KEYCODE"
e[e.CUSTOM_MENU_SET_VALUE     = 7] = "CUSTOM_MENU_SET_VALUE"     // ← 6 被跳过
e[e.CUSTOM_MENU_GET_VALUE     = 8] = "CUSTOM_MENU_GET_VALUE"
e[e.CUSTOM_MENU_SAVE          = 9] = "CUSTOM_MENU_SAVE"
e[e.EEPROM_RESET              = 10]
e[e.BOOTLOADER_JUMP           = 11]
...
```

**`5 → 7`，`cmd 6` 在官方驱动里根本不存在。**

这从第三方（官方驱动二进制）独立验证了补丁占用 `cmd 6` 是安全的——
不是"我觉得没人用"，而是"官方枚举里没有这个号"。

---

## 3. 命令号完整对照

| cmd | 官方驱动名称 | 固件 handler | 本补丁 |
|---|---|---|---|
| 1 | GET_PROTOCOL_VERSION | `FUN_08009280` | 不变 |
| 2 | GET_KEYBOARD_VALUE | `FUN_080092F4` | 不变 |
| 3 | SET_KEYBOARD_VALUE | `FUN_080093A8` | 不变 |
| 4 | DYNAMIC_KEYMAP_GET_KEYCODE | `FUN_0800942C` | 不变 |
| 5 | DYNAMIC_KEYMAP_SET_KEYCODE | `FUN_080094B0` | 不变 |
| **6** | **（官方不存在）** | `FUN_08008E34` | **★ 被接管为 GET_BATTERY** |
| 7 | CUSTOM_MENU_SET_VALUE / BACKLIGHT_SET | `0x08008CB8`（thunk @ `0x08008E40`） | 不变 |
| 8 | CUSTOM_MENU_GET_VALUE / BACKLIGHT_GET | `0x08008CB8`（thunk @ `0x08008D6C`） | 不变 |
| 9 | CUSTOM_MENU_SAVE / BACKLIGHT_SAVE | `0x08008CB8`（thunk @ `0x08008D78`） | 不变 |
| 10 | EEPROM_RESET | `FUN_08008C88` | 不变 |
| 11 | BOOTLOADER_JUMP | `FUN_08008C94` | 不变 |
| 12–16 | MACRO_* | — | 不变 |
| 17 | DYNAMIC_KEYMAP_GET_LAYER_COUNT | `FUN_08008D84`（→ `0x08008CB8`） | 不变 |
| 18 | DYNAMIC_KEYMAP_GET_BUFFER | `0x08008CB8`（thunk @ `0x08008D90`） | 不变 |
| 19 | DYNAMIC_KEYMAP_SET_BUFFER | `FUN_08008CAC` | 不变 |
| 20/21 | GET/SET_ENCODER | `FUN_08008F5C` / `FUN_08008F68` | 不变 |

> 注意 `FUN_08008CB8` 是 Ghidra **漏识别**的函数（`push.w` 序言 `2de9f04f`
> 没被当作函数入口）。它同时服务 cmd 7/8/9/17/18 —— 一个"按亮度表批量渲染 LED"
> 的通用引擎，`r1` 是回调参数。

---

## 4. 灯效通道（channel 3）实测语义

官方 JSON 的 `menus`：

```json
{"label":"Brightness","type":"range","options":[0,255],
 "content":["id_qmk_rgb_matrix_brightness", 3, 1]}
{"label":"Effect","type":"dropdown",
 "content":["id_qmk_rgb_matrix_effect", 3, 2], "options":[...]}
{"label":"Effect Speed","type":"range","options":[0,255],
 "content":["id_qmk_rgb_matrix_effect_speed", 3, 3]}
{"label":"Color","type":"color",
 "content":["id_qmk_rgb_matrix_color", 3, 4]}
```

`content` 三元组 = `[id, channel, id]`，所以实际请求是：

```
设置: [0, 7, channel=3, id, ...value]
读取: [0, 8, channel=3, id, nbytes]
```

| 控件 | id | 值 |
|---|---|---|
| Brightness 亮度 | 1 | 1 字节 0–255 |
| Effect 效果 | 2 | 1 字节（见下表） |
| Effect Speed 速度 | 3 | 1 字节 0–255 |
| Color 颜色 | 4 | **3 字节 HSV**（H 0–255, S, V） |

### 效果编号表

| 值 | 名称 | 值 | 名称 |
|---|---|---|---|
| 0 | All Off 全关 | 26 | Hue Pendulum 色相摆动 |
| 2 | Alphas Mods | 29 | Pixel Flow |
| 5 | Breathing 呼吸 | 30 | Pixel Fractal |
| 6 | Band Sat | 33 | Solid Reactive Simple |
| 9 | Band Pinwheel Val | 34 | Solid Reactive |
| 13 | Cycle Left Right | 35 | Solid Reactive Wide |
| 15 | Rainbow Moving Chevron | 43 | Solid Splash |
| 16 | Cycle Out In | 45 | Close All |
| 24 | Jellybean Raindrops | | |
| 25 | Hue Breathing 色相呼吸 | | |

> 这是固件真正支持的效果子集（不是 QMK 全量）。官方 JSON 里列的就是这些。

---

## 5. 键位读写协议（已在实机验证）

`tools/probe_max102.py` 已成功读取全部 5 层，证明：

```
REPORT_SIZE = 33
请求: [0, cmd, ...payload, 补 0]
响应: [0, cmd, ...data, 补 0]
```

### 批量读键位（cmd 18）

```
请求: [0, 18, offset_hi, offset_lo, size]      size ≤ 28
响应: [0, 18, ?, ?, data...]                    data 从 r[4] 开始
```

- 每层 = 6×19×2 = **228 字节**
- 层偏移 = `L * 228`
- 每层 9 次请求（28×8 + 4），5 层共 **45 次**

官方驱动也是这个算法（源码 `fastReadRawMatrix`）：

```js
const i = 28;
for (let l = 0; l < n.length; l += i) {
  const s = n.slice(l, l + i);
  await this.hidCommand(18, [...]);
}
```

### 单键读写（cmd 4/5）

```
读: [0, 4, layer, row, col]        → 响应 r[4..5] = keycode (大端)
写: [0, 5, layer, row, col, hi, lo]
```

---

## 6. 矩阵到布局的映射（已核实）

固件矩阵 `6 行 × 19 列`，扁平索引 = `row * 19 + col`。

官方 JSON 布局行与矩阵行的对应关系：

| 布局行 | 矩阵行 | 说明 |
|---|---|---|
| 0 | 0 | ESC / F1-F12 / INS / PSCR / SCRL / HOME / END |
| 1 | 1 | GRV / 数字 / BSPC / DEL / NUM / PSLS / PAST / PMNS |
| 2 | 2 | TAB / QWERTY / PGUP / P7-P9 / PPLS |
| 3 | 3 | CAPS / ASDF / PGDN / P4-P6 |
| 4 | 4 | LSFT / ZXCV / UP / P1-P3 / PENT（+ 行尾 `5,18` 是 h:2 的高键） |
| 5 | 5 | 底排（LCTL … SPC … MO(1) …） |

⚠️ **两个特殊位置**（容易踩坑）：

- `2,18` 和 `5,18` 在布局里都是 `{"h": 2}` —— 它们是**同一个物理键的两段**
  （右侧高键），固件里是矩阵 (2,18) 和 (5,18)。
- 布局行 4 从 `4,0` 直接跳到 `4,2`，**没有 `4,1`** —— 该位置固件里是
  左 Shift 的一部分（`w:2.25`）。

---

## 7. 本仓库产出的工具

| 位置 | 用途 |
|---|---|
| `tools/patch_battery.py` | 生成电量补丁固件 |
| `tools/read_battery.py` | 命令行读电量 |
| `tools/probe_24g.py` | 2.4G / 接收器通道下探活并读电量 |
| **`web/index.html`** | **本地 WebHID 工具：改键 + 电量 + 灯效**（见 [`web/README.md`](../web/README.md)） |
| **`web/device.json`** | 设备定义（矩阵 / 布局 / 灯效通道） |

本地工具相比官方 `usevia.app` 的优势：

| 项 | usevia.app | 本地工具（`web/`） |
|---|---|---|
| 需要联网 | ✅ 需要 | ❌ 不需要 |
| 显示电量 | ❌ 不支持 | ✅ |
| 需要按厂家说明改文件名 | ✅ 要 load `max102(1).json` | ❌ 开箱即用 |
| 层数 | 只暴露 4 层 | 5 层（含隐藏 BOOT 层） |
| 自定义键码 | 只列 9 个 | 同 9 个 + 完整键码表 |
| 可改代码 | ❌ | ✅ |

---

## 8. 待确认

| # | 项 | 状态 |
|---|---|---|
| 1 | cmd 7/8 的响应切片偏移 | 官方源码是 `slice(0 + a.length)`，`a` 为 payload；本地工具用 `slice(4)`，**需实机校准** |
| 2 | 颜色是否为 HSV 还是另有编码 | 官方 JSON 标的 `type: color`，QMK `id_qmk_rgb_matrix_color` 语义为 HSV，**需实机验证** |
| 3 | 灯效写入是否需要 cmd 9 SAVE 落盘 | 官方代码里 `setCustomMenuValue` 直接 cmd 7，未见 save 调用 → 推断立即生效 |
