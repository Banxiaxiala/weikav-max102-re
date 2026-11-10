#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAX102 只读探测器  (READ-ONLY, 绝不写入键盘)

作用:
  1. 按 VID 0x342D / usage_page 65376 找到键盘
  2. 读 PROTOCOL_VERSION / FIRMWARE_VERSION / LAYER_COUNT
  3. dump 当前 keymap (6x19 矩阵, 全部层) 到 JSON
  4. 同时列出所有 HID 设备, 辅助判断 MCU 通道

本脚本只发送 VIA 的 "GET" 类命令 (1, 2, 17, 18), 不发送任何 SET/SAVE/BOOTLOADER 命令。
"""

import json
import sys
import os

try:
    import hid
except ImportError:
    print("[!] 缺少 hidapi:  pip install hidapi")
    sys.exit(1)

VENDOR_ID = 0x342D
PRODUCT_ID = 0xE537
USAGE_PAGE = 65376
USAGE = 97

REPORT_SIZE = 33

# VIA 命令码 (只使用只读的)
CMD_GET_PROTOCOL_VERSION = 1
CMD_GET_KEYBOARD_VALUE = 2
CMD_DYNAMIC_KEYMAP_GET_KEYCODE = 4
CMD_DYNAMIC_KEYMAP_GET_LAYER_COUNT = 17
CMD_DYNAMIC_KEYMAP_GET_BUFFER = 18

# keyboard value id
KV_UPTIME = 1
KV_LAYOUT_OPTIONS = 2
KV_SWITCH_MATRIX_STATE = 3
KV_FIRMWARE_VERSION = 4
KV_DEVICE_INDICATION = 5


def u16(hi, lo):
    return (hi << 8) | lo


def hexs(s):
    return " ".join("%02X" % b for b in s)


# --------------------------------------------------------------------------
# 1. 设备枚举
# --------------------------------------------------------------------------
def list_all_devices():
    print("=" * 62)
    print("所有 HID 设备:")
    print("=" * 62)
    devs = hid.enumerate()
    target = None
    for d in devs:
        vid = d.get("vendor_id")
        pid = d.get("product_id")
        up = d.get("usage_page")
        us = d.get("usage")
        name = d.get("product_string") or ""
        hit = ""
        if vid == VENDOR_ID and pid == PRODUCT_ID and up == USAGE_PAGE:
            hit = "   <== MAX102 主通道"
            target = d
        elif vid == VENDOR_ID:
            hit = "   <== MAX102 其它接口"
        print("  VID=%04X PID=%04X usage_page=%-6s usage=%-4s iface=%-2s %s%s"
              % (vid, pid, up, us, d.get("interface_number"), name, hit))
    return target


# --------------------------------------------------------------------------
# 2. 命令收发
# --------------------------------------------------------------------------
class Max102VIA:
    def __init__(self, path):
        self.dev = hid.device()
        self.dev.open_path(path)
        self.dev.set_nonblocking(0)

    def close(self):
        try:
            self.dev.close()
        except Exception:
            pass

    def cmd(self, code, payload=None, resp_len=32):
        """发送 VIA 命令, 返回响应字节 (去掉 report id)"""
        payload = payload or []
        buf = [0, code] + list(payload)
        if len(buf) > REPORT_SIZE:
            raise ValueError("report too long: %d" % len(buf))
        buf += [0] * (REPORT_SIZE - len(buf))
        self.dev.write(buf)
        resp = self.dev.read(REPORT_SIZE, 2000)
        return list(resp) if resp else []

    # --- 只读查询 ---
    def get_protocol_version(self):
        r = self.cmd(CMD_GET_PROTOCOL_VERSION)
        if len(r) < 3:
            return -1
        return u16(r[1], r[2])

    def get_keyboard_value(self, kv_id, nbytes=1):
        r = self.cmd(CMD_GET_KEYBOARD_VALUE, [kv_id], resp_len=nbytes)
        if len(r) < 2 + nbytes:
            return []
        return r[2:2 + nbytes]

    def get_layer_count(self):
        r = self.cmd(CMD_DYNAMIC_KEYMAP_GET_LAYER_COUNT)
        if len(r) < 2:
            return -1
        return r[1]

    def get_keycode(self, layer, row, col):
        r = self.cmd(CMD_DYNAMIC_KEYMAP_GET_KEYCODE, [layer, row, col])
        if len(r) < 6:
            return None
        return u16(r[4], r[5])

    def get_buffer(self, offset, size):
        if size > 28:
            raise ValueError("max 28")
        r = self.cmd(CMD_DYNAMIC_KEYMAP_GET_BUFFER,
                     [(offset >> 8) & 0xFF, offset & 0xFF, size])
        if len(r) < 4 + size:
            return []
        return r[4:4 + size]


# --------------------------------------------------------------------------
# 3. 主流程
# --------------------------------------------------------------------------
def main():
    outdir = os.environ.get("MAX102_OUT", os.getcwd())
    os.makedirs(outdir, exist_ok=True)

    target = list_all_devices()
    if not target:
        print()
        print("[!] 没找到 MAX102 (VID=0x342D PID=0xE537 usage_page=65376)")
        print("    请确认: 键盘用 USB 线连接, 并切到有线模式 (FN+T)")
        return 1

    print()
    print("=" * 62)
    print("连接 MAX102 ...")
    print("=" * 62)
    kb = Max102VIA(target["path"])
    info = {}

    try:
        proto = kb.get_protocol_version()
        info["protocol_version"] = proto
        print("  PROTOCOL_VERSION      : %s" % proto)

        fw = kb.get_keyboard_value(KV_FIRMWARE_VERSION, 4)
        if len(fw) == 4:
            ver = "%d.%d.%d" % (fw[1], fw[2], fw[3])
            info["firmware_version"] = ver
            info["firmware_version_raw"] = hexs(fw)
            print("  FIRMWARE_VERSION      : %s   (raw %s)" % (ver, hexs(fw)))

        up = kb.get_keyboard_value(KV_UPTIME, 4)
        if len(up) == 4:
            ms = (up[0] << 24) | (up[1] << 16) | (up[2] << 8) | up[3]
            info["uptime_ms"] = ms
            print("  UPTIME                : %d ms (%.1f h)" % (ms, ms / 3600000.0))

        lo = kb.get_keyboard_value(KV_LAYOUT_OPTIONS, 4)
        if lo:
            info["layout_options"] = hexs(lo)
            print("  LAYOUT_OPTIONS        : %s" % hexs(lo))

        layers = kb.get_layer_count()
        info["layer_count"] = layers
        print("  LAYER_COUNT           : %s" % layers)

        rows, cols = 6, 19
        print()
        print("  读取 keymap: %d 层 x %d x %d ..." % (layers, rows, cols))

        buffers = {}
        for L in range(max(layers, 0)):
            flat = []
            total = rows * cols
            off = 0
            base = L * total * 2
            while off < total * 2:
                n = min(28, total * 2 - off)
                chunk = kb.get_buffer(base + off, n)
                if not chunk:
                    break
                flat.extend(chunk)
                off += n
            codes = [u16(flat[i], flat[i + 1]) for i in range(0, len(flat) - 1, 2)]
            buffers["layer_%d" % L] = codes
            nz = sum(1 for c in codes if c)
            print("    layer %d: %d 字节, %d 个非零键码" % (L, len(flat), nz))

        info["keymap"] = buffers

    except Exception as e:
        print("[!] 读取出错: %r" % (e,))
        info["error"] = repr(e)
    finally:
        kb.close()

    fn = os.path.join(outdir, "max102_info.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print()
    print("已保存: %s" % fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
