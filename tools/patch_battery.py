#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAX102 电量上报补丁生成器
=========================

在原厂固件里接管未使用的 VIA 命令 cmd 0x06，让它返回电量信息。
原 cmd 0x06 的实现（FUN_08008E34，按位掩码批量设 LED 颜色）在官方
VIA 定义和网页驱动里都没有被使用。

改动（共 38 字节）：
  1. tbh 表 cmd 0x06 项：0x08009958  2 字节  0x0050 -> 0x39F4
  2. handler 代码：      0x08010D34 34 字节  空白 -> ARM Thumb
  3. 对齐 + 字面量池：   0x08010D56  2 + 8 字节

用法：
    py -3.13 patch_battery.py                      # 生成补丁文件
    py -3.13 patch_battery.py --verify             # 只做安全检查
    py -3.13 patch_battery.py -o my_patched.bin

安全保证：
  - 所有前置条件都断言检查，任何一项不符立即中止
  - 不修改除上述区域外的任何字节
  - 生成的文件名带 patched 标记，绝不覆盖原厂备份
"""

import argparse
import struct
import sys
from pathlib import Path

# ---------------------------------------------------------------- 常量

ROOT = Path(__file__).resolve().parent.parent

SRC_DEFAULT = ROOT / "firmware/max102_stock_trimmed.bin"
DST_DEFAULT = ROOT / "firmware/max102_patched_battery.bin"
BASE = 0x08000000

# tbh 表（cmd 0x06 项）
TBH_TABLE = 0x0800994C
CMD_SLOT = 0x06
SLOT_ENTRY = TBH_TABLE + CMD_SLOT * 2          # 0x08009958
SLOT_EXPECT = 0x0050                           # 原值（指向 0x080099EC）

# 新 handler
HANDLER = 0x0800FD82
POOL = 0x0800FDA8

# 要读的 RAM
RESP_PTR_LITERAL = 0x08009AAC                  # 该处存 0x20000F60
MD_INFO = 0x20000C7D                           # {state, indicator, version, bat}

# 期望的空闲区大小（含池）
REGION_END = 0x0800FE6E


# ---------------------------------------------------------------- 工具

def read_word(buf, addr):
    off = addr - BASE
    return struct.unpack("<I", buf[off:off + 4])[0]


def read_half(buf, addr):
    off = addr - BASE
    return struct.unpack("<H", buf[off:off + 2])[0]


def die(msg):
    print()
    print("=" * 60)
    print("中止：" + msg)
    print("=" * 60)
    sys.exit(1)


def check(cond, what, detail=""):
    mark = "OK  " if cond else "FAIL"
    print(f"  [{mark}] {what}" + (f"  ({detail})" if detail else ""))
    return cond


# ---------------------------------------------------------------- 安全检查

def preflight(buf):
    print("=" * 60)
    print("前置安全检查")
    print("=" * 60)
    ok = True

    # 1. 文件长度
    ok &= check(len(buf) == 69632,
                "固件长度 = 69632 (0x11000)",
                f"实际 {len(buf)}")

    # 2. tbh 表 cmd 0x06 项
    cur = read_half(buf, SLOT_ENTRY)
    ok &= check(cur == SLOT_EXPECT,
                f"tbh[{CMD_SLOT:#04x}] 原值 = {SLOT_EXPECT:#06x}",
                f"实际 {cur:#06x}")
    tgt = TBH_TABLE + cur * 2
    ok &= check(tgt == 0x080099EC,
                "该项当前指向 FUN_08008E34 (0x080099EC)",
                f"实际 {tgt:#x}")

    # 3. 响应缓冲区指针字面量
    rp = read_word(buf, RESP_PTR_LITERAL)
    ok &= check(rp == 0x20000F60,
                f"响应缓冲区指针 @{RESP_PTR_LITERAL:#x} = 0x20000F60",
                f"实际 {rp:#x}")

    # 4. handler 目标区必须全零
    off = HANDLER - BASE
    region = buf[off:off + (REGION_END - HANDLER)]
    ok &= check(all(b == 0 for b in region),
                f"代码区 {HANDLER:#x}..{REGION_END:#x} 全零空白",
                f"{len(region)} 字节")

    # 5. 整段区域内不允许被任何 32/16 位值指向（防字面量池/表项误伤）
    import struct as _s
    refs = []
    for i in range(0, len(buf) - 3):
        v = _s.unpack("<I", buf[i:i + 4])[0]
        if HANDLER <= v < REGION_END:
            refs.append((BASE + i, v))
    for i in range(0, len(buf) - 1):
        v = _s.unpack("<H", buf[i:i + 2])[0]
        if HANDLER <= v < REGION_END:
            refs.append((BASE + i, v))
    ok &= check(not refs,
                f"{HANDLER:#x}..{REGION_END:#x} 无任何指针引用",
                f"{len(refs)} 处: {[(hex(a), hex(v)) for a, v in refs[:5]]}" if refs else "0 处")

    if not ok:
        die("前置检查未通过，未生成任何文件。")

    # 计算新表项
    new_entry = (HANDLER - TBH_TABLE) // 2
    check(new_entry <= 0xFFFF,
          f"新表项 {new_entry:#06x} 在 halfword 范围内")
    check(TBH_TABLE + new_entry * 2 == HANDLER,
          f"反算校验：{TBH_TABLE:#x} + {new_entry:#x}*2 = {HANDLER:#x}")
    return new_entry


# ---------------------------------------------------------------- 生成代码

def build_handler():
    """返回 (代码字节, 池字节)

    ⚠️ 关键：handler 结尾必须 `b 0x080099C8`（跳公共尾部），
    不能 `bx lr`。

    因为本 handler 由命令分发表直接跳入（tbh 目标），不在 `bl` 调用上下文里。
    用 bx lr 会直接返回到 FUN_08009868 的调用者，跳过：
      - add sp,#0x34      （栈未恢复 → 错位）
      - pop {r4-r11,lr}   （寄存器未恢复）
      - bl 0x08008B80     （响应从未发送）
    后果是必崩。

    正确做法与 cmd 1..0x2D 完全一致：
      0x08009BDE: bl raw_hid_send
      0x08009BE2..0x08009BEA: 弹栈返回
    """
    try:
        from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB
    except ImportError:
        die("缺少 keystone-engine。请先：py -3.13 -m pip install keystone-engine")

    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)

    # 两处 PC 相对 ldr 的立即数
    #   ldr @ HANDLER+0 : PC = (HANDLER+4) & ~3
    #   ldr @ HANDLER+4 : PC = (HANDLER+8) & ~3
    imm0 = POOL - ((HANDLER + 0 + 4) & ~3)
    imm1 = (POOL + 4) - ((HANDLER + 4 + 4) & ~3)

    asm = f"""
        ldr      r1, [pc, #{imm0}]
        ldr      r1, [r1]
        ldr      r2, [pc, #{imm1}]
        ldr      r2, [r2]
        ubfx     r3, r2, #24, #8
        strb     r3, [r1, #4]
        uxtb     r3, r2
        strb     r3, [r1, #5]
        ubfx     r3, r2, #16, #8
        strb     r3, [r1, #6]
        ubfx     r3, r2, #8, #8
        strb     r3, [r1, #7]
        movs     r0, #0
        b        #0x080099C8
    """
    code, count = ks.asm(asm, HANDLER)
    code = bytes(code)

    if HANDLER + len(code) > POOL:
        die(f"代码 {len(code)} 字节超出池起点 {POOL:#x}")

    pool = struct.pack("<II", RESP_PTR_LITERAL, MD_INFO)
    return code, pool


# ---------------------------------------------------------------- 校验反汇编

def verify_disasm(code):
    try:
        import capstone
    except ImportError:
        print("  (跳过反汇编校验: 未安装 capstone)")
        return True

    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
    print()
    print("=" * 60)
    print("handler 反汇编校验")
    print("=" * 60)

    import re
    bad = False
    expected_targets = {POOL, POOL + 4}
    seen = set()
    for ins in md.disasm(code, HANDLER):
        extra = ""
        if ins.mnemonic == "ldr" and "pc" in ins.op_str:
            m = re.search(r"#(0x[0-9a-f]+|\d+)", ins.op_str)
            if m:
                tgt = ((ins.address + 4) & ~3) + int(m.group(1), 0)
                extra = f"   -> {tgt:#x}"
                seen.add(tgt)
                if tgt not in expected_targets:
                    extra += "  <<< 错误目标"
                    bad = True
        print(f"  {ins.address:08x}  {ins.mnemonic:<8}{ins.op_str}{extra}")

    if seen != expected_targets:
        print(f"  [FAIL] ldr 目标 {[hex(x) for x in seen]} != {[hex(x) for x in expected_targets]}")
        bad = True
    else:
        print(f"  [OK  ] 两处 ldr 均指向字面量池")

    return not bad


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(
        description="为 MAX102 生成带电量上报的固件补丁",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--src", default=SRC_DEFAULT, help="原厂固件")
    ap.add_argument("-o", "--out", default=DST_DEFAULT, help="输出文件")
    ap.add_argument("--verify", action="store_true", help="只检查，不写文件")
    ap.add_argument("--force", action="store_true", help="允许覆盖已存在的输出文件")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        die(f"找不到 {src}")

    buf = bytearray(src.read_bytes())
    print(f"源文件: {src}  ({len(buf)} 字节)")
    print()

    new_entry = preflight(buf)

    code, pool = build_handler()
    if not verify_disasm(code):
        die("反汇编校验失败")

    print()
    print("=" * 60)
    print("补丁内容")
    print("=" * 60)
    print(f"  tbh[{CMD_SLOT:#04x}] @ {SLOT_ENTRY:#010x}: "
          f"{SLOT_EXPECT:#06x} -> {new_entry:#06x}")
    print(f"  handler   @ {HANDLER:#010x}: {len(code)} 字节")
    print(f"  padding   @ {HANDLER + len(code):#010x}: "
          f"{POOL - HANDLER - len(code)} 字节")
    print(f"  pool      @ {POOL:#010x}: {len(pool)} 字节")
    print(f"  合计改动  : {2 + len(code) + (POOL - HANDLER - len(code)) + len(pool)} 字节")

    if args.verify:
        print()
        print("--verify 模式：未写入任何文件。")
        return 0

    # 应用补丁
    # 1) tbh 表项
    off = SLOT_ENTRY - BASE
    buf[off:off + 2] = struct.pack("<H", new_entry)
    # 2) handler 代码
    off = HANDLER - BASE
    buf[off:off + len(code)] = code
    # 3) 对齐填充（保持 0，显式写一遍）
    off = HANDLER - BASE + len(code)
    buf[off:POOL - BASE] = b"\x00" * (POOL - HANDLER - len(code))
    # 4) 字面量池
    off = POOL - BASE
    buf[off:off + len(pool)] = pool

    dst = Path(args.out)
    if dst.exists() and not args.force:
        die(f"{dst} 已存在。加 --force 覆盖，或换 -o 文件名。")
    dst.write_bytes(bytes(buf))

    print()
    print("=" * 60)
    print(f"已生成: {dst}  ({len(buf)} 字节)")
    print("=" * 60)
    print()
    print("下一步：")
    print("  1. 进 DFU: 按住 FN -> 按住右 Shift -> 点 ESC")
    print(f"  2. wb32-dfu-updater_cli.exe -D {dst.name} -s 0x08000000")
    print("  3. wb32-dfu-updater_cli.exe -R")
    print("  4. py -3.13 read_battery.py")
    print()
    print("回退：")
    print("  wb32-dfu-updater_cli.exe -D max102_stock_trimmed.bin -s 0x08000000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
