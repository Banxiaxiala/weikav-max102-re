#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAX102 EEPROM 配置完整备份  (READ-ONLY)

备份内容:
  - 全部层的 keymap (raw + 解码)
  - 宏 (macro) 缓冲
  - VIA 相关 keyboard value (protocol / firmware / uptime / layout)

本脚本只发送 GET 类命令，绝不写入键盘、不调用 EEPROM_RESET、不跳 bootloader。
输出到 backup_<时间戳>.json
"""

import json
import os
import sys
import time

try:
    import hid
except ImportError:
    print("[!] pip install hidapi")
    sys.exit(1)

VENDOR_ID = 0x342D
PRODUCT_ID = 0xE537
USAGE_PAGE = 65376
USAGE = 97
REPORT_SIZE = 33

CMD_GET_PROTOCOL_VERSION = 1
CMD_GET_KEYBOARD_VALUE = 2
CMD_DYNAMIC_KEYMAP_GET_KEYCODE = 4
CMD_DYNAMIC_KEYMAP_MACRO_GET_COUNT = 12
CMD_DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE = 13
CMD_DYNAMIC_KEYMAP_MACRO_GET_BUFFER = 14
CMD_DYNAMIC_KEYMAP_GET_LAYER_COUNT = 17
CMD_DYNAMIC_KEYMAP_GET_BUFFER = 18

KV_UPTIME = 1
KV_LAYOUT_OPTIONS = 2
KV_SWITCH_MATRIX_STATE = 3
KV_FIRMWARE_VERSION = 4


def u16(hi, lo):
    return (hi << 8) | lo


class VIA:
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

    def protocol_version(self):
        r = self.cmd(CMD_GET_PROTOCOL_VERSION)
        return u16(r[1], r[2]) if len(r) >= 3 else -1

    def kb_value(self, kvid, n=1):
        r = self.cmd(CMD_GET_KEYBOARD_VALUE, [kvid])
        return r[2:2 + n] if len(r) >= 2 + n else []

    def layer_count(self):
        r = self.cmd(CMD_DYNAMIC_KEYMAP_GET_LAYER_COUNT)
        return r[1] if len(r) >= 2 else -1

    def buffer(self, offset, size):
        assert size <= 28
        r = self.cmd(CMD_DYNAMIC_KEYMAP_GET_BUFFER,
                     [(offset >> 8) & 0xFF, offset & 0xFF, size])
        return r[4:4 + size] if len(r) >= 4 + size else []

    def macro_count(self):
        r = self.cmd(CMD_DYNAMIC_KEYMAP_MACRO_GET_COUNT)
        return r[1] if len(r) >= 2 else -1

    def macro_buf_size(self):
        r = self.cmd(CMD_DYNAMIC_KEYMAP_MACRO_GET_BUFFER_SIZE)
        return u16(r[1], r[2]) if len(r) >= 3 else -1

    def macro_bytes(self, total):
        out = []
        off = 0
        while off < total:
            n = min(28, total - off)
            r = self.cmd(CMD_DYNAMIC_KEYMAP_MACRO_GET_BUFFER,
                         [(off >> 8) & 0xFF, off & 0xFF, n])
            if len(r) < 4:
                break
            out.extend(r[4:4 + n])
            off += n
        return out


def find_device():
    for d in hid.enumerate():
        if (d.get("vendor_id") == VENDOR_ID
                and d.get("product_id") == PRODUCT_ID
                and d.get("usage_page") == USAGE_PAGE):
            return d
    return None


def main():
    dev = find_device()
    if not dev:
        print("[!] 未找到 MAX102。请插 USB 线并切到有线模式 (FN+T)")
        return 1

    kb = VIA(dev["path"])
    data = {"_meta": {
        "device": "Weikav MAX102",
        "vid": "0x%04X" % VENDOR_ID,
        "pid": "0x%04X" % PRODUCT_ID,
        "usage_page": USAGE_PAGE,
        "usage": USAGE,
        "path": dev["path"].decode("utf-8", "replace") if isinstance(dev["path"], bytes) else str(dev["path"]),
        "product_string": dev.get("product_string"),
        "backup_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tool": "probe_max102 backup (read-only)",
    }}

    try:
        proto = kb.protocol_version()
        data["protocol_version"] = proto
        print("PROTOCOL_VERSION : %s" % proto)

        fw = kb.kb_value(KV_FIRMWARE_VERSION, 4)
        data["firmware_version_raw"] = " ".join("%02X" % b for b in fw)
        if len(fw) == 4:
            data["firmware_version"] = "%d.%d.%d" % (fw[1], fw[2], fw[3])
            print("FIRMWARE_VERSION : %s" % data["firmware_version"])

        lo = kb.kb_value(KV_LAYOUT_OPTIONS, 4)
        data["layout_options"] = " ".join("%02X" % b for b in lo)

        layers = kb.layer_count()
        data["layer_count"] = layers
        print("LAYER_COUNT      : %s" % layers)

        ROWS, COLS = 6, 19
        total = ROWS * COLS * 2
        print("备份 keymap: %d 层 x %d x %d" % (layers, ROWS, COLS))
        data["matrix"] = {"rows": ROWS, "cols": COLS}

        raw_layers = {}
        for L in range(layers):
            buf = []
            off = 0
            while off < total:
                n = min(28, total - off)
                chunk = kb.buffer(L * total + off, n)
                if not chunk:
                    break
                buf.extend(chunk)
                off += n
            raw_layers["layer_%d" % L] = buf
            codes = [u16(buf[i], buf[i + 1]) for i in range(0, len(buf) - 1, 2)]
            print("  layer %d: %d bytes, 非零键码 %d 个"
                  % (L, len(buf), sum(1 for c in codes if c)))
        data["keymap_raw_bytes"] = {
            k: " ".join("%02X" % b for b in v) for k, v in raw_layers.items()
        }
        data["keymap"] = {
            k: [u16(v[i], v[i + 1]) for i in range(0, len(v) - 1, 2)]
            for k, v in raw_layers.items()
        }

        # 宏
        try:
            mc = kb.macro_count()
            ms = kb.macro_buf_size()
            data["macro_count"] = mc
            data["macro_buffer_size"] = ms
            print("MACRO_COUNT      : %s" % mc)
            print("MACRO_BUF_SIZE   : %s" % ms)
            if 0 < ms <= 16384:
                mb = kb.macro_bytes(ms)
                data["macro_raw_bytes"] = " ".join("%02X" % b for b in mb)
                nz = sum(1 for b in mb if b)
                print("备份宏缓冲: %d 字节 (非零 %d)" % (len(mb), nz))
        except Exception as e:
            data["macro_error"] = repr(e)
            print("[!] 宏读取失败: %r" % (e,))

    except Exception as e:
        data["error"] = repr(e)
        print("[!] 错误: %r" % (e,))
    finally:
        kb.close()

    fn = "backup_%s.json" % time.strftime("%Y%m%d_%H%M%S")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print()
    print("✅ 已保存: %s" % os.path.abspath(fn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
