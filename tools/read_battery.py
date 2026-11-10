#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAX102 电量读取器
=================

读取打了 patch_battery.py 补丁的固件里新增的电量命令（VIA cmd 0x06）。

用法：
    py -3.13 read_battery.py             # 单次读取
    py -3.13 read_battery.py -w 2        # 每 2 秒刷新
    py -3.13 read_battery.py --json      # JSON 输出

注意：
    刷了补丁后，VIA 的 cmd 0x06 被接管。原 cmd 6 是厂家私有命令，
    官方 VIA 定义和网页驱动都没有使用，所以不影响正常改键。

回退：
    刷回 firmware/max102_stock_trimmed.bin 即可恢复原始 cmd 6。
"""

import argparse
import json
import sys
import time

try:
    import hid
except ImportError:
    print("[!] 缺少 hidapi:  py -3.13 -m pip install hidapi")
    sys.exit(1)

VENDOR_ID = 0x342D
PRODUCT_ID = 0xE537
USAGE_PAGE = 65376
USAGE = 97
REPORT_SIZE = 33

CMD_GET_BATTERY = 0x06      # 补丁接管的命令号

STATE_NAMES = {
    0: "NONE（未初始化）",
    1: "PAIRING（配对中）",
    2: "CONNECTED（已连接）",
    3: "DISCONNECTED（已断开）",
    4: "REJECT（被拒绝）",
}

LED_BITS = [
    (0x01, "CapsLock"),
    (0x02, "NumLock"),
    (0x04, "ScrollLock"),
]


def find_device():
    """按 usage_page 找 VIA 通道"""
    for d in hid.enumerate():
        if (d.get("vendor_id") == VENDOR_ID
                and d.get("product_id") == PRODUCT_ID
                and d.get("usage_page") == USAGE_PAGE):
            return d
    return None


class Max102:
    def __init__(self, path):
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(0)

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass

    def cmd(self, code, payload=None):
        payload = payload or []
        buf = [0, code] + list(payload)
        buf += [0] * (REPORT_SIZE - len(buf))
        self.dev.write(buf)
        r = self.dev.read(REPORT_SIZE, 2000)
        return list(r) if r else []

    def get_battery(self):
        r = self.cmd(CMD_GET_BATTERY)
        if len(r) < 8:
            return None
        return {
            "battery": r[4],
            "state": r[5],
            "module_version": r[6],
            "indicator": r[7],
        }


def describe(info):
    bat = info["battery"]
    state = info["state"]

    if bat > 100:
        level = "??"
        bar = "?" * 20
    else:
        level = f"{bat:3d}%"
        filled = round(bat / 5)
        bar = "#" * filled + "." * (20 - filled)

    leds = [name for bit, name in LED_BITS if info["indicator"] & bit]
    led_s = ", ".join(leds) if leds else "无"

    lines = [
        f"  电量       : {level}  [{bar}]",
        f"  连接状态   : {STATE_NAMES.get(state, f'未知({state})')}",
        f"  模块版本   : {info['module_version']}",
        f"  指示灯     : {led_s}",
    ]
    return "\n".join(lines)


def render_once(kb, as_json, quiet=False):
    info = kb.get_battery()
    if info is None:
        if not quiet:
            print("  [!] 读取失败：键盘没有响应 cmd 0x06")
            print("      可能原因：")
            print("        1. 还没刷补丁固件")
            print("        2. 键盘不在有线模式（试 FN+T）")
            print("        3. 选了错误的 HID 接口")
        return False

    if as_json:
        print(json.dumps(info, ensure_ascii=False))
    else:
        if not quiet:
            print(describe(info))
    return True


def main():
    ap = argparse.ArgumentParser(description="读取 MAX102 电量")
    ap.add_argument("-w", "--watch", type=float, metavar="SEC",
                    help="循环刷新，间隔秒数")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    dev = find_device()
    if not dev:
        print("[!] 没找到 MAX102 的 VIA 通道")
        print(f"    期望 VID={VENDOR_ID:#06x} PID={PRODUCT_ID:#06x} "
              f"usage_page={USAGE_PAGE}")
        print("    请确认：USB 线连接 + 电源开关 ON + 按 FN+T 切有线模式")
        print()
        print("    当前枚举到的 HID 设备：")
        for d in hid.enumerate():
            if d.get("vendor_id") == VENDOR_ID:
                print(f"      VID={d['vendor_id']:#06x} PID={d['product_id']:#06x} "
                      f"usage_page={d.get('usage_page')} usage={d.get('usage')} "
                      f"iface={d.get('interface_number')}")
        return 1

    kb = Max102(dev["path"])
    try:
        if not args.watch:
            print(f"设备: {dev.get('product_string', 'MAX102')}")
            return 0 if render_once(kb, args.json) else 1

        try:
            while True:
                ts = time.strftime("%H:%M:%S")
                info = kb.get_battery()
                if args.json:
                    print(json.dumps(info, ensure_ascii=False))
                elif info:
                    print(f"[{ts}] 电量 {info['battery']:3d}%  "
                          f"状态 {STATE_NAMES.get(info['state'], info['state'])}  "
                          f"版本 {info['module_version']}")
                else:
                    print(f"[{ts}] 读取失败")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print()
            print("已停止。")
    finally:
        kb.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
