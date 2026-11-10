#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAX102 2.4G 通道探测与电量读取
==============================

目的
----
验证「2.4G 模式下，主机能不能通过 HID 端口读到键盘电量」。

原理（已从固件反汇编确认）
--------------------------
    VIA vendor HID 收包  →  FUN_08009xxx 分发  →  cmd 0x06 (补丁)
                                                   ↓ 填 0x20000F60+4
                                            FUN_080031C2 统一出口
                                                   ↓ 按当前模式分流
                   mode==1(BT)  →  队列 2
                   否则(2.4G/USB) →  FUN_080039B4  md_send_raw
                                            ↓ UART3 115200
                                        FR8003A 无线模块
                                            ↓ 2.4G 空口
                                        USB 接收器 → 主机

关键未知项
----------
接收器（dongle）是否把 vendor-defined HID 接口原样透传给主机。
这属于 dongle 固件（FR8003A 侧），本地固件里查不到，只能实测。

本脚本做四件事
--------------
  1. 列出所有 HID 设备，高亮 VID 0x342D（键盘本体）与疑似接收器
  2. 对每个候选接口，用无害的 VIA cmd 1（GET_PROTOCOL_VERSION）探活
  3. 探活成功的接口上读电量（补丁的 cmd 0x06）
  4. 汇总判定：2.4G 是否可用 / 卡在哪一步

安全说明
--------
只发送 VIA 的 GET 类命令（cmd 1 / cmd 6）。不发送任何 SET / SAVE /
BOOTLOADER 命令，不会修改键位、灯效或固件。

用法
----
    py -3.13 tools/probe_24g.py              # 单次完整探测
    py -3.13 tools/probe_24g.py -w 2         # 每 2 秒读一次电量（探活通过后）
    py -3.13 tools/probe_24g.py --json       # 机器可读输出
    py -3.13 tools/probe_24g.py --scan-only  # 只枚举不读电量
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

# ---------------------------------------------------------------- 常量

VENDOR_ID = 0x342D          # MAX102 键盘本体（USB 有线）
PRODUCT_ID = 0xE537
DFU_PID = 0xDFA0

VIA_USAGE_PAGE = 0xFF60
VIA_USAGE = 0x61
REPORT_SIZE = 33            # 1 字节 report id + 32 字节载荷

CMD_GET_PROTOCOL_VERSION = 0x01
CMD_GET_BATTERY = 0x06      # 补丁接管的命令号

STATE_NAMES = {
    0: "NONE（未初始化）",
    1: "PAIRING（配对中）",
    2: "CONNECTED（已连接）",
    3: "DISCONNECTED（已断开）",
    4: "REJECT（被拒绝）",
}

LED_BITS = [(0x01, "CapsLock"), (0x02, "NumLock"), (0x04, "ScrollLock")]

# 接收器可能使用的 VID。MAX102 的 2.4G 名字是 "MAX102-2.4G"，
# 由固件通过 0xA9 SEND_DEVINFO 推给模块，因此接收器上报的
# product string 可能是这个名字，也可能沿用 342D。
SUSPECT_VIDS = {VENDOR_ID, 0x0C45, 0x05AC, 0x258A, 0x3151, 0x373B, 0x1EA7}


# ---------------------------------------------------------------- 枚举

def safe_str(v):
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v or ""


def enumerate_all():
    """枚举全部 HID 接口，按 VID 分组。"""
    devices = []
    for d in hid.enumerate():
        devices.append({
            "path": d.get("path"),
            "vid": d.get("vendor_id") or 0,
            "pid": d.get("product_id") or 0,
            "usage_page": d.get("usage_page") or 0,
            "usage": d.get("usage") or 0,
            "interface": d.get("interface_number", -1),
            "product": safe_str(d.get("product_string")),
            "manufacturer": safe_str(d.get("manufacturer_string")),
            "serial": safe_str(d.get("serial_number")),
        })
    return devices


def is_via_candidate(d):
    """是否可能是 VIA 通道（先按 usage 判断，宽松一点）。"""
    return (d["usage_page"] == VIA_USAGE_PAGE
            or (d["usage_page"] >= 0xFF00 and d["usage"] == VIA_USAGE))


def looks_like_receiver(d):
    """接收器的启发式判断（名字/VID）。"""
    name = (d["product"] or "").lower()
    if any(k in name for k in ("2.4g", "2.4 g", "dongle", "receiver", "max102")):
        return True
    return d["vid"] in SUSPECT_VIDS and d["vid"] == VENDOR_ID


# ---------------------------------------------------------------- 通信

def _open(path):
    dev = hid.device()
    dev.open_path(path)
    return dev


def _norm(pkt, size=32):
    """统一剥掉 report id 前缀。"""
    raw = bytes(pkt)
    if len(raw) == size + 1 and raw[:1] == b"\x00":
        return raw[1:]
    return raw


def _transact(dev, cmd, payload=b"", timeout_ms=300):
    """
    发一条 VIA 命令并等响应。

    先试 output report（write），失败退到 feature report
    （send_feature_report）—— 与官方网页驱动的两条路径一致。
    """
    frame = bytearray(REPORT_SIZE)
    frame[0] = 0x00          # report id
    frame[1] = cmd
    for i, b in enumerate(payload[:REPORT_SIZE - 2]):
        frame[2 + i] = b

    try:
        dev.set_nonblocking(True)
    except Exception:
        pass

    # 路径 A：output report
    try:
        n = dev.write(frame)
        if isinstance(n, int) and n > 0:
            deadline = time.monotonic() + timeout_ms / 1000.0
            while time.monotonic() < deadline:
                pkt = dev.read(REPORT_SIZE, 50)
                if pkt:
                    return _norm(pkt), "write"
                time.sleep(0.02)
    except Exception:
        pass

    # 路径 B：feature report
    try:
        n = dev.send_feature_report(frame)
        if isinstance(n, int) and n > 0:
            for _ in range(4):
                time.sleep(0.05)
                pkt = dev.get_feature_report(0, REPORT_SIZE)
                if pkt:
                    return _norm(pkt), "feature"
    except Exception:
        pass

    return None, None


def probe_interface(cand):
    """
    探活：发 cmd 1 GET_PROTOCOL_VERSION。
    返回 (ok, protocol_version, 通道名, 错误信息)
    """
    try:
        dev = _open(cand["path"])
    except Exception as e:
        return False, None, None, f"打开失败: {e}"

    try:
        resp, ch = _transact(dev, CMD_GET_PROTOCOL_VERSION)
        if resp is None:
            return False, None, None, "命令无响应（该接口不透传 vendor HID）"
        # 响应的第 2 字节是回显的命令号，第 3 字节是协议版本
        if len(resp) < 3:
            return False, None, ch, f"响应过短: {resp.hex(' ')}"
        if resp[1] != CMD_GET_PROTOCOL_VERSION:
            return False, None, ch, (
                f"命令号不匹配（期望 0x01，收到 0x{resp[1]:02X}），"
                f"原始: {resp[:8].hex(' ')}"
            )
        return True, resp[2], ch, None
    finally:
        try:
            dev.close()
        except Exception:
            pass


def read_battery(cand, timeout_ms=500):
    """
    读电量（补丁 cmd 0x06）。
    返回 dict 或 (None, 错误信息)
    """
    try:
        dev = _open(cand["path"])
    except Exception as e:
        return None, f"打开失败: {e}"

    try:
        resp, ch = _transact(dev, CMD_GET_BATTERY, timeout_ms=timeout_ms)
        if resp is None:
            return None, "无响应"
        if len(resp) < 8:
            return None, f"响应过短: {resp.hex(' ')}"

        # 补丁布局： resp[4]=电量 resp[5]=状态 resp[6]=模块版本 resp[7]=指示灯
        info = {
            "battery": resp[4],
            "state": resp[5],
            "module_version": resp[6],
            "indicator": resp[7],
            "raw": resp[:12].hex(" "),
            "channel": ch,
        }
        return info, None
    finally:
        try:
            dev.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 展示

def fmt_flags(bits):
    out = [name for mask, name in LED_BITS if bits & mask]
    return "+".join(out) if out else "无"


def print_enumeration(devices):
    print("=" * 78)
    print("第 1 步：HID 接口枚举")
    print("=" * 78)

    via = [d for d in devices if is_via_candidate(d)]
    max102 = [d for d in devices if d["vid"] == VENDOR_ID]
    others = [d for d in devices if looks_like_receiver(d)
              and d["vid"] != VENDOR_ID]

    print(f"\n全部 HID 接口: {len(devices)} 个")
    print(f"  VID 0x{VENDOR_ID:04X} (MAX102/USB): {len(max102)} 个")
    print(f"  usage_page 0xFF60/0xFF00+ (疑似 VIA): {len(via)} 个")
    print(f"  其它可疑接收器: {len(others)} 个")

    if not max102 and not others:
        print("\n  [!] 没有发现 VID 0x342D 设备，也没有可疑接收器。")
        print("      请确认：")
        print("        - 2.4G 接收器已插入 USB 口")
        print("        - 键盘已开机，且 FN + T 切到了 2.4G 模式")
        print("        - 接收器与键盘已配对（可用 FN + 4 重新配对）")
        return

    print("\n--- VID 0x342D 接口明细 ---")
    for d in max102:
        tag = "VIA" if is_via_candidate(d) else "   "
        print(f"  [{tag}] if={d['interface']:>2} "
              f"usage_page=0x{d['usage_page']:04X} usage=0x{d['usage']:02X} "
              f"pid=0x{d['pid']:04X}  {d['product']!r}")

    if others:
        print("\n--- 其它疑似接收器 ---")
        for d in others:
            tag = "VIA" if is_via_candidate(d) else "   "
            print(f"  [{tag}] if={d['interface']:>2} "
                  f"vid=0x{d['vid']:04X} pid=0x{d['pid']:04X} "
                  f"usage_page=0x{d['usage_page']:04X}  {d['product']!r}")

    if not via:
        print("\n  [!] 上述接口里没有 usage_page 0xFF60 的 vendor 端点。")
        print("      这意味着接收器没有暴露 VIA 控制通道 → 2.4G 读电量走不通此路。")


def print_probe(results):
    print("\n" + "=" * 78)
    print("第 2 步：候选接口探活（VIA cmd 1 = GET_PROTOCOL_VERSION）")
    print("=" * 78)

    if not results:
        print("\n  没有可探测的 VIA 候选接口。")
        return False

    any_ok = False
    for r in results:
        c = r["candidate"]
        label = (f"if={c['interface']} usage_page=0x{c['usage_page']:04X} "
                 f"usage=0x{c['usage']:02X} pid=0x{c['pid']:04X}")
        if r["ok"]:
            any_ok = True
            print(f"\n  [✓] {label}")
            print(f"      探活成功 → 协议版本 v{r['version']}，通道={r['channel']}")
        else:
            print(f"\n  [✗] {label}")
            print(f"      失败: {r['error']}")
    return any_ok


def print_battery(info, cand):
    print("\n" + "=" * 78)
    print("第 3 步：读取电量（补丁 cmd 0x06）")
    print("=" * 78)

    if info is None:
        return False

    bat = info["battery"]
    state = info["state"]
    print(f"\n  接口: if={cand['interface']} pid=0x{cand['pid']:04X} "
          f"通道={info['channel']}")
    print(f"  电量        : {bat}%")
    print(f"  连接状态    : {state} — {STATE_NAMES.get(state, '未知')}")
    print(f"  模块版本    : {info['module_version']}")
    print(f"  指示灯      : 0x{info['indicator']:02X} ({fmt_flags(info['indicator'])})")
    print(f"  原始响应    : {info['raw']}")

    if not (0 <= bat <= 100):
        print(f"\n  [!] 电量 {bat} 超出 0–100 范围，可能是残留值。")
        print("      原因：模块可能未在当前通道上报 0x5C，结构体未被刷新。")
        return False

    print(f"\n  [✓] 2.4G 通道读取成功：{bat}%")
    return True


def print_verdict(enum_ok, probe_ok, battery_ok):
    print("\n" + "=" * 78)
    print("判定")
    print("=" * 78)

    if not enum_ok:
        print("\n  ✗ 未发现设备 —— 检查接收器/配对/模式切换")
        return
    if not probe_ok:
        print("\n  ✗ 接收器不透传 vendor HID（VIA cmd 1 无响应）")
        print("    → 2.4G 下无法通过 VIA 端口读电量")
        print("    → 备选方案：改 HID 描述符加 Battery Strength，")
        print("      让 dongle 当标准 HID 转发（见 docs/07-电量补丁方案.md 路线 A-2）")
        return
    if not battery_ok:
        print("\n  △ VIA 通了，但电量无效")
        print("    → 补丁可能未刷入（先跑有线模式确认 cmd 6 正常）")
        print("    → 或模块未在 2.4G 通道上报 0x5C（电量结构体未刷新）")
        return

    print("\n  ✓✓ 2.4G 模式可通过 HID 端口读取键盘电量")
    print("     补丁无需修改，模式分流由 FUN_080031C2 自动处理。")


# ---------------------------------------------------------------- 主流程

def discover_candidates(devices):
    """挑出值得探活的接口，去重（同接口多 collection 只留一个）。"""
    cands = []
    seen = set()
    for d in devices:
        if not is_via_candidate(d):
            continue
        key = (d["vid"], d["pid"], d["interface"], d["usage_page"], d["usage"])
        if key in seen:
            continue
        seen.add(key)
        cands.append(d)

    # 优先级：0xFF60/0x61 + 非负接口号 排前面（华奋达方案的实测经验）
    def prio(d):
        if d["usage_page"] == VIA_USAGE_PAGE and d["usage"] == VIA_USAGE:
            return (0 if d["interface"] >= 0 else 1, d["interface"])
        return (2, d["interface"])

    return sorted(cands, key=prio)


def main():
    ap = argparse.ArgumentParser(description="MAX102 2.4G 电量探测")
    ap.add_argument("-w", "--watch", type=float, metavar="SEC",
                    help="探活通过后持续读取，间隔秒数")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("--scan-only", action="store_true", help="只枚举，不读电量")
    ap.add_argument("--timeout", type=int, default=500, metavar="MS",
                    help="读电量超时毫秒（默认 500）")
    args = ap.parse_args()

    devices = enumerate_all()

    if args.json:
        result = {"devices": devices, "candidates": [], "probe": [], "battery": None}
    else:
        print_enumeration(devices)

    cands = discover_candidates(devices)
    if args.json:
        result["candidates"] = cands

    if args.scan_only:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # 探活
    probe_results = []
    for c in cands:
        ok, ver, ch, err = probe_interface(c)
        probe_results.append({
            "candidate": c, "ok": ok, "version": ver,
            "channel": ch, "error": err,
        })

    if args.json:
        result["probe"] = [
            {k: v for k, v in r.items() if k != "candidate"}
            for r in probe_results
        ]
    else:
        probe_ok = print_probe(probe_results)

    live = [r["candidate"] for r in probe_results if r["ok"]]

    # 读电量
    target = None
    for c in live:
        if c["usage_page"] == VIA_USAGE_PAGE and c["usage"] == VIA_USAGE:
            target = c
            break
    if target is None and live:
        target = live[0]

    battery_ok = False
    if target is not None:
        info, err = read_battery(target, args.timeout)
        if args.json:
            result["battery"] = info if info else {"error": err}
        else:
            if info is None:
                print("\n" + "=" * 78)
                print("第 3 步：读取电量（补丁 cmd 0x06）")
                print("=" * 78)
                print(f"\n  [✗] 失败: {err}")
            else:
                battery_ok = print_battery(info, target)

        # watch 模式
        if args.watch and info is not None:
            print(f"\n持续读取中（间隔 {args.watch}s，Ctrl+C 退出）...")
            try:
                while True:
                    time.sleep(args.watch)
                    info, err = read_battery(target, args.timeout)
                    ts = time.strftime("%H:%M:%S")
                    if info is None:
                        print(f"  [{ts}] 读取失败: {err}")
                    else:
                        print(f"  [{ts}] {info['battery']:>3}%  "
                              f"{STATE_NAMES.get(info['state'], '?')}  "
                              f"指示灯={fmt_flags(info['indicator'])}")
            except KeyboardInterrupt:
                print("\n已停止。")

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        probe_ok = any(r["ok"] for r in probe_results)
        print_verdict(bool(devices), probe_ok, battery_ok)

    return 0


if __name__ == "__main__":
    sys.exit(main())
