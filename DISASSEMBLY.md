# MAX102 固件反汇编分析

> 基于 Ghidra 12.2 对原厂固件的完整反编译结果
> 分析对象：`max102_stock_trimmed.bin`（69,632 字节）
> 分析日期：2026-11-10

---

## 1. 概览

| 项目 | 值 |
|---|---|
| 分析工具 | Ghidra 12.2 (JDK 25) + Capstone 5.0 |
| 处理器 | `ARM:LE:32:Cortex` (Cortex-M3, Thumb) |
| 基址 | `0x08000000` |
| 文件大小 | 69,632 字节 |
| 有效向量表 | 56 项（40 个外部 IRQ，其中 10 个有实现） |
| 指令总数 | 28,781 |
| **识别函数** | **520 个** |
| 反编译成功 | 520 / 520（100%） |
| 可读字符串 | 49 条 |

---

## 2. 中断向量表

| 向量 | 地址 | 状态 |
|---|---|---|
| Initial SP | `0x20000400` | — |
| Reset_Handler | `0x080001B9` | ✅ 实现 |
| NMI / HardFault / MemManage / BusFault / UsageFault | `0x080001BB` | ⚠️ 默认弱符号（`b .` 死循环） |
| SVC_Handler | `0x0800D231` | ✅ 实现 |
| PendSV_Handler | `0x080001BB` | ⚠️ 默认 |
| SysTick_Handler | `0x0800E69B` | ✅ 实现 |
| IRQ6–IRQ10 | `0x0800E391`–`0x0800E431` | ✅ |
| IRQ14 | `0x0800ED65` | ✅ 最大 IRQ 函数（536 字节，6 calls） |
| IRQ16 | `0x0800E459` | ✅ |
| IRQ26 / IRQ27 | `0x0800E951` / `0x0800E965` | ✅ |
| IRQ32 | `0x0800E6B9` | ✅ |
| IRQ33 | `0x0800E4BD` | ✅ |
| 其余 30 个 IRQ | `0x080001BB` | ⚠️ 未使用 |

**观察**：HardFault 是弱符号，意味着**固件没有自定义异常处理**，一旦触发硬件异常就是死循环（无日志、无法恢复）。这也解释了为什么刷机出错后只能靠 DFU/SWD 救。

---

## 3. 关键函数识别

### 3.1 Bootloader 跳转 —— 已完整还原

**`FUN_0800BCB4` @ `0x0800BCB4`**

反编译结果：

```c
void bootloader_jump_custom(void) {
    int magic = *(int *)(DAT_0800bce0 + -4);      // MAGIC_ADDR = __ram0_end__ - 4
    if (magic != DAT_0800bce4)                    // 0xDEADBEEF
        return;
    *(undefined4 *)(DAT_0800bce0 + -4) = 0;       // 清除 magic
    if (isCurrentModePrivileged()) {
        setThreadModePrivileged(1);
        if (isThreadMode())
            setStackMode(isUsingMainStack());
    }
    if (isCurrentModePrivileged())
        setMainStackPointer(*DAT_0800bce8);       // DAT_0800bce8 = 0x1FFFE000  ← ROM bootloader
    enableIRQinterrupts();
    (*(code *)DAT_0800bce8[1])(...);              // 跳转到 (0x1FFFE004) = bootloader 的 Reset
    while(1);
}
```

**这与 QMK 官方 `platforms/chibios/bootloaders/wb32_dfu.c` 的实现逐字对应**：

```c
#define BOOTLOADER_MAGIC 0xDEADBEEF
#define MAGIC_ADDR (unsigned long *)(SYMVAL(__ram0_end__) - 4)

__attribute__((weak)) void bootloader_jump(void) {
    *MAGIC_ADDR = BOOTLOADER_MAGIC;
    NVIC_SystemReset();
}

void enter_bootloader_mode_if_requested(void) {
    unsigned long *check = MAGIC_ADDR;
    if (*check == BOOTLOADER_MAGIC) {
        *check = 0;
        __set_CONTROL(0);
        __set_MSP(*(__IO uint32_t *)WB32_BOOTLOADER_ADDRESS);
        __enable_irq();
        typedef void (*BootJump_t)(void);
        BootJump_t boot_jump = *(BootJump_t *)(WB32_BOOTLOADER_ADDRESS + 4);
        boot_jump();
        while (1);
    }
}
```

**结论**：厂家直接用 QMK 的 WB32 支持，`BOOTLOADER = wb32-dfu`。

---

### 3.2 VIA 命令分发器 —— 完整还原

**`FUN_08009868` @ `0x08009868`**（1670 字节，54 个调用，**最大函数**）

这是一个巨大的 `switch` 分发器，case 数量 **0x01 – 0x2D 共 45 个命令**。

#### 完整命令表（反编译还原）

| cmd | 十进制 | 名称 | Handler |
|---|---|---|---|
| `0x01` | 1 | `GET_PROTOCOL_VERSION` | `thunk_FUN_0800a320` |
| `0x02` | 2 | `GET_KEYBOARD_VALUE` | `FUN_080092F4` |
| `0x03` | 3 | `SET_KEYBOARD_VALUE` | `FUN_080093A8` |
| `0x04` | 4 | `DYNAMIC_KEYMAP_GET_KEYCODE` | `FUN_0800942C` |
| `0x05` | 5 | `DYNAMIC_KEYMAP_SET_KEYCODE` | `FUN_080094B0` |
| `0x06` | 6 | **厂家私有**（网页驱动未使用） | `FUN_08008E34` |
| `0x07` | 7 | `BACKLIGHT_CONFIG_SET_VALUE` | `FUN_08008E40` |
| `0x08` | 8 | `BACKLIGHT_CONFIG_GET_VALUE` | `FUN_08008D6C` |
| `0x09` | 9 | `BACKLIGHT_CONFIG_SAVE` | `FUN_08008D78` |
| `0x0A` | 10 | `EEPROM_RESET` | `FUN_08008C88` |
| `0x0B` | 11 | `BOOTLOADER_JUMP` | `FUN_08008C94` |
| `0x0C` | 12 | `DYNAMIC_KEYMAP_MACRO_GET_COUNT` | `FUN_08008E4C` |
| `0x0D` | 13 | `MACRO_GET_BUFFER_SIZE` | `FUN_08008E58` |
| `0x0E` | 14 | `MACRO_GET_BUFFER` | `FUN_08008E64` |
| `0x0F` | 15 | `MACRO_SET_BUFFER` | `FUN_08008E70` |
| `0x10` | 16 | `MACRO_RESET` | `FUN_08008CA0` |
| `0x11` | 17 | `DYNAMIC_KEYMAP_GET_LAYER_COUNT` | `FUN_08008D84` |
| `0x12` | 18 | `DYNAMIC_KEYMAP_GET_BUFFER` | `FUN_08008D90` |
| `0x13` | 19 | `DYNAMIC_KEYMAP_SET_BUFFER` | `FUN_08008CAC` |
| `0x14` | 20 | `GET_ENCODER` | `FUN_08008F5C` |
| `0x15` | 21 | `SET_ENCODER` | `FUN_08008F68` |
| `0x16` | 22 | **厂家私有** | `FUN_08008F74` |
| `0x17` | 23 | **厂家私有** | `FUN_08009560` |
| `0x18` | 24 | **厂家私有** | `FUN_080095D4` |
| `0x19` | 25 | **厂家私有** | `FUN_08009648` |
| `0x1A` | 26 | **厂家私有** | `FUN_08008E7C` |
| `0x1B` | 27 | **厂家私有** | `FUN_08008E88` |
| `0x1C` | 28 | **厂家私有**（复杂：3 个调用） | `FUN_08008B88`, `FUN_08007E74` |
| `0x1D` | 29 | **厂家私有** | `thunk_FUN_0800A320`, `FUN_08007E74` |
| `0x1E` | 30 | **厂家私有** | `thunk_FUN_0800A320`, `FUN_08008B88`, `FUN_080086D8` |
| `0x1F` | 31 | **厂家私有** | `FUN_080096FC` |
| `0x20` | 32 | **厂家私有** | `FUN_0800890C` |
| `0x21`–`0x2C` | 33–44 | **厂家私有** | `FUN_08009xxx` 系列 |
| `0x2D` | 45 | **厂家私有** | `FUN_0800982C` |

**重要发现**：

- **命令 6 是厂家私有**，网页驱动代码里没有——说明官方网页驱动也没用全功能
- **命令 22–45 全部是厂家私有**，官方 `via.json` 完全没有描述
- 这解释了为什么固件里有 **5 个未声明的自定义键码**（`0x7E09/0A/0C/0D/0E`）——它们通过私有命令配置

#### 命令 11 = BOOTLOADER_JUMP 的反编译

```c
void cmd_bootloader_jump(void) {   // FUN_08008C94
    FUN_08008BB0(param_1, DAT_08008C9C);
    return;
}
```

它调用的 `FUN_08008BB0` 内部会走到 `FUN_0800BCB4`（上面分析过的跳转函数）。

---

### 3.3 层键（Layer Key）处理器

**`FUN_08008D84`（cmd 17, GET_LAYER_COUNT）和 `FUN_08008D90`（cmd 18, GET_BUFFER）反编译高度相似**，说明 Ghidra 识别到一个共享模式：

> 原厂反编译/反汇编代码已移除（版权归 LEIKU / Weikav）。
> 行为结论见上下文文字说明；如需原始代码，请用 `firmware/` 自行复现。


**`0x158 = 344`** 正是 `172 键 × 2 字节`。而我们的矩阵是 `6 × 19 = 114`，说明**固件内部的 keymap 缓冲区按更大的矩阵分配**（可能是为其他型号预留）。

---

### 3.4 编译期内联函数

| 函数 | 识别结果 |
|---|---|
| `FUN_08000244` | **`__aeabi_uldivmod`** —— 64 位无符号除法（GCC 内联，724 字节） |
| `FUN_08009A08` | 大整数运算辅助 |
| `Reset_Handler` | 已识别为 `disableIRQinterrupts` / `setMainStackPointer` / `setProcessStackPointer` 组合 |

---

## 4. 全局变量映射

从反编译结果反查 literal pool，确认了大量 RAM 变量地址：

| 符号 | 指向 | 区域 | 推测用途 |
|---|---|---|---|
| `DAT_08009A9C` | `0x200032B8` | RAM | 计时器 tick |
| `DAT_08009AA0` | `0x20003100` | RAM | 主状态结构体 |
| `DAT_08009AA4` | `0x20003DC8` | RAM | **VIA 命令参数缓冲区** |
| `DAT_08009AA8` | `0x20000F65` | RAM | **当前命令码** |
| `DAT_08009AAC` | `0x20000F60` | RAM | **响应缓冲区**（被引 31 次，最热） |
| `DAT_08009AB0` | `0x20003DD0` | RAM | 时间戳 |
| `DAT_08009AB4` | `0x20003DD4` | RAM | 临时缓冲 |
| `DAT_08009AB8` | `0x20000F63` | RAM | 层号 |
| `DAT_08009194` | `0x20003DD4` | RAM | 高频（30 次引用） |
| `DAT_080091A0` | `0x20003DC8` | RAM | 高频（20 次引用） |
| `DAT_0800E528` | `0x20003FD8` | RAM | 18 次引用 |
| `DAT_080072C4` | `0x20003D94` | RAM | 18 次引用 |
| `DAT_0800EF7C` | **`0x40014000`** | **外设** | ⚠️ 需查明（WB32 特有外设） |
| `DAT_0800D2C4` | `0xE000ED00` | SCB | CPUID 寄存器 |
| `DAT_0800BCE8` | **`0x1FFFE000`** | ROM | **WB32 DFU bootloader 基址** |

**`0x40014000`** 不在标准 STM32 外设映射内（STM32 的 `0x40014000` 是 SPI3，但 WB32 可能有差异）。这是 WB32 特有模块，可能是：

- QSPI 控制器（`monsgeek/m1` 用了 `WB32_SPI_USE_QSPI`）
- 或者无线模块的 UART

---

## 5. RAM 布局推断

| 地址范围 | 大小 | 推测用途 |
|---|---|---|
| `0x20000000` – `0x20000400` | 1 KB | ✅ **已用**（Initial SP = `0x20000400`，说明启动时有 1KB 静态数据在栈下） |
| `0x20000D89` – `0x20000F65` | ~500 B | VIA 命令缓冲区群 |
| `0x20003000` – `0x20003300` | ~768 B | 主状态结构 |
| `0x2000395E` | — | 中型结构 |
| `0x20003D00` – `0x20004300` | ~1.5 KB | VIA 响应 + 配置区（最热，密集引用） |

总计可推断使用了约 **17 KB RAM**（WB32FQ95 有 32 KB SRAM）。

---

## 6. 字符串与设备标识

| 地址 | 字符串 | 类型 |
|---|---|---|
| `0x0800F520` | `LEKU` | UTF-16LE — **制造业者** |
| `0x0800F52F` | `MAX102-2.4G` | UTF-16LE — 2.4G 接收器配对名 |
| `0x0800F53E` | `MAX102` | UTF-16LE — USB 产品名 |
| `0x0800F545` | `MAX102-BT1` | ASCII — 蓝牙通道 1 |
| `0x0800F551` | `MAX102-BT2` | ASCII — 蓝牙通道 2 |
| `0x0800F55D` | `MAX102-BT3` | ASCII — 蓝牙通道 3 |
| `0x0800F569` | `MAX102 BT4` | ASCII — 蓝牙通道 4（空格） |
| `0x0800F574` | `MAX102 BT5` | ASCII — 蓝牙通道 5（空格） |

⚠️ **注意 BT4/BT5 用空格，BT1-3 用连字符**，这是原厂的不一致，但证实了 5 个通道的存在。

**工具链证据**：

```
0x0800xxxx  "REENT malloc succeeded"
0x0800xxxx  "../../../../../../../../newlib/libc/stdlib/rand.c"
0x0800xxxx  "assertion \"%s\" failed: file \"%s\", line %d%s%s"
```

→ 标准 **newlib**（`arm-none-eabi-gcc`）。路径深度 8 层说明编译环境是深目录结构（如 `qmk_firmware/tmk_core/protocol/chibios/...`）。

---

## 7. 无线架构确认（关键）

固件里**只有蓝牙设备名字符串，没有任何蓝牙栈代码**：

- ❌ 无 HCI 命令处理
- ❌ 无 L2CAP / ATT / SM
- ❌ 无 2.4G 跳频逻辑
- ❌ 无连接状态机

**唯一相关的**是 `FUN_0800B662` @ `0x0800B662`（452 字节，23 calls），它的 switch 结构像是一个**命令转发器**：

> 原厂反编译/反汇编代码已移除（版权归 LEIKU / Weikav）。
> 行为结论见上下文文字说明；如需原始代码，请用 `firmware/` 自行复现。


**`case 3` 循环查询 6 个设备** —— 这与 `DEVS_USB/DEVS_BT1..BT5/DEVS_2G4` 的枚举完全对应！

→ **确认**：无线模块通过某条总线（UART 或 SPI）挂在这颗主控上，固件通过 `FUN_0800B4F0` 下发命令、`FUN_080073CC` 查询状态。

**这条总线极可能就是 `0x40014000` 那个外设。**

---

## 8. Harness：如何在本地验证分析结果

### 8.1 反汇编（Capstone，无需 Ghidra）

```bash
python disasm_max102.py max102_stock_trimmed.bin
# 输出 max102_disasm.asm + max102_analysis.md
```

### 8.2 反编译（Ghidra headless）

```bash
# 前置：JDK 25+ 和 Ghidra 12.2
set JAVA_HOME=C:\Program Files\Microsoft\jdk-25.0.5.21-hotspot

# 1. 导入
ghidra_12.2_PUBLIC\support\analyzeHeadless.bat ^
    <projdir> max102 ^
    -import max102_stock_trimmed.bin ^
    -processor "ARM:LE:32:Cortex" ^
    -loader BinaryLoader -loader-baseAddr 0x08000000

# 2. 建符号
ghidra_12.2_PUBLIC\support\analyzeHeadless.bat ^
    <projdir> max102 ^
    -process max102_stock_trimmed.bin ^
    -scriptPath ghidra_scripts -postScript Max102Post.java -noanalysis

# 3. 导出 C 伪代码
ghidra_12.2_PUBLIC\support\analyzeHeadless.bat ^
    <projdir> max102 ^
    -process max102_stock_trimmed.bin ^
    -scriptPath ghidra_scripts -postScript ExportDecomp.java -noanalysis
```

### 8.3 输出产物

| 文件 | 大小 | 内容 |
|---|---|---|
| `ghidra_out/decompiled_all.c` | 458 KB | **520 个函数的 C 伪代码** |
| `ghidra_out/functions.asm` | 516 KB | 520 个函数的分组反汇编 |
| `ghidra_out/functions.txt` | 38 KB | 函数索引（地址 / 名字 / 大小 / 调用数） |

---

## 9. 下一步可做的事

### 9.1 短期（不需要硬件）

| 任务 | 方法 | 价值 |
|---|---|---|
| 重命名 520 个函数 | 按 `decompiled_all.c` 逻辑 + QMK 源码比对 | 极高 |
| 找到矩阵扫描函数 | 搜索 GPIO 读操作 + 位运算循环 | 高 |
| 找 RGB 驱动函数 | 搜索 104 次循环 + 颜色运算 | 高 |
| 逆向私有命令 22–45 | 逐个分析 `FUN_08009xxx` | 中 |
| 确认 `0x40014000` 外设 | 查 WB32 数据手册 | **高**（决定无线路线） |

### 9.2 中期（需要硬件）

| 任务 | 需要 | 难度 |
|---|---|---|
| 抓无线模块 UART | 逻辑分析仪 + 拆屏蔽罩 | 🔴 高 |
| 测矩阵引脚 | 万用表 | 🟡 中 |
| 确认 RGB LED 协议 | 示波器或直接试 WS2812 | 🟡 中 |

### 9.3 与 QMK 源码对齐

因为确认了用的是 QMK + `wb32-dfu`，可以**直接对照 QMK 源码**来识别函数：

| 固件函数 | 疑似 QMK 对应 |
|---|---|
| `FUN_08008D84` | `dynamic_keymap_get_layer_count()` |
| `FUN_08008D90` | `dynamic_keymap_get_buffer()` |
| `FUN_0800942C` | `dynamic_keymap_get_keycode()` |
| `FUN_080094B0` | `dynamic_keymap_set_keycode()` |
| `FUN_0800BCB4` | `enter_bootloader_mode_if_requested()` ✅ **已确认** |
| `FUN_08009868` | `raw_hid_receive()` 的命令分发 |
| `FUN_0800B662` | 私有：无线设备查询 |

**方法**：把 QMK 源码用**相同的编译器选项**（`-O2 -mcpu=cortex-m3 -mthumb`）编译，然后做二进制比对（BSim / Diaphora / BinDiff），就能自动匹配大量函数。

---

## 10. 已知限制

1. **Ghidra 对间接调用识别不佳** —— 反编译结果里大量 `(*(code *)(...))(args)` 是被 Ghidra 误判的，实际是普通函数调用。原因是没有完整的函数指针类型信息。
2. **没有符号表** —— 所有函数名都是 `FUN_0800xxxx`，需要人工命名。
3. **浮点/长整型运算混在内联代码里** —— `FUN_08000244` 是 64 位除法，不是业务逻辑。
4. **数据区未完全分离** —— Ghidra 线性扫描把部分数据当成了代码（capstone 覆盖了 100% 字节，但 Ghidra 只认出 520 个函数）。

---

## 11. 附录：文件清单

```
ghidra_out/
├── decompiled_all.c    520 个 C 伪代码（458 KB）
├── functions.asm       分组反汇编（516 KB）
└── functions.txt       函数索引（38 KB）

ghidra_scripts/
├── Max102Post.java     建向量表符号 + 全段反汇编
└── ExportDecomp.java   导出 C 伪代码

disasm_max102.py        Capstone 独立反汇编器（输出 .asm + .md）
max102_disasm.asm       完整线性反汇编（含字符串/外设注释）
max102_analysis.md      Capstone 分析报告
```
