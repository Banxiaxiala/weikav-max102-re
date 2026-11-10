# -*- coding: utf-8 -*-
"""把 temp/max102_info.json 的 raw keymap 解码成可读的 QMK 键名。

输入：temp/max102_info.json（probe_max102.py 的输出）
输出：tools/keymap_readable.txt
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # tools/
TEMP = HERE.parent / "temp"

INFO = TEMP / "max102_info.json"
VIA = HERE / "max102_via.json"
OUT = HERE / "keymap_readable.txt"

if not INFO.exists():
    sys.exit("找不到 %s，先跑 python tools/probe_max102.py" % INFO)

d = json.load(open(INFO, encoding='utf-8'))
via = json.load(open(VIA, encoding='utf-8'))
km = d['keymap']

BASE = {
0:'----',1:'▽TRNS',4:'A',5:'B',6:'C',7:'D',8:'E',9:'F',10:'G',11:'H',12:'I',13:'J',14:'K',15:'L',16:'M',
17:'N',18:'O',19:'P',20:'Q',21:'R',22:'S',23:'T',24:'U',25:'V',26:'W',27:'X',28:'Y',29:'Z',
30:'1',31:'2',32:'3',33:'4',34:'5',35:'6',36:'7',37:'8',38:'9',39:'0',
40:'ENT',41:'ESC',42:'BSPC',43:'TAB',44:'SPC',45:'MINS',46:'EQL',47:'LBRC',48:'RBRC',49:'BSLS',50:'NUHS',
51:'SCLN',52:'QUOT',53:'GRV',54:'COMM',55:'DOT',56:'SLSH',57:'CAPS',
58:'F1',59:'F2',60:'F3',61:'F4',62:'F5',63:'F6',64:'F7',65:'F8',66:'F9',67:'F10',68:'F11',69:'F12',
70:'PSCR',71:'SCRL',72:'PAUS',73:'INS',74:'HOME',75:'PGUP',76:'DEL',77:'END',78:'PGDN',
79:'RGHT',80:'LEFT',81:'DOWN',82:'UP',
83:'NUM',84:'PSLS',85:'PAST',86:'PMNS',87:'PPLS',88:'PENT',89:'P1',90:'P2',91:'P3',92:'P4',93:'P5',
94:'P6',95:'P7',96:'P8',97:'P9',98:'P0',99:'PDOT',100:'NUBS',101:'APP',102:'PWR',103:'PEQL',
116:'EXEC',117:'HELP',118:'MENU',119:'SLCT',120:'STOP',121:'AGIN',122:'UNDO',123:'CUT',124:'COPY',
125:'PSTE',126:'FIND',127:'MUTE',128:'VOLU',129:'VOLD',130:'LOCK',131:'NUTG',
0x00A8:'MUTE',0x00A9:'VOLU',0x00AA:'VOLD',0x00AB:'MNXT',0x00AC:'MPRV',0x00AD:'MSTP',
0x00AE:'MPLY',0x00AF:'MSEL',0x00B0:'EJCT',0x00B1:'MAIL',0x00B2:'CALC',0x00B3:'MYCM',
0x00B4:'WSCH',0x00B5:'WHOM',0x00BD:'BRIU',0x00BE:'BRID',0x00C1:'MCTL',0x00C2:'LPAD',
0x00E0:'LCTL',0x00E1:'LSFT',0x00E2:'LALT',0x00E3:'LGUI',0x00E4:'RCTL',0x00E5:'RSFT',
0x00E6:'RALT',0x00E7:'RGUI',
}

# QK_KB (0x7E00-0x7E3F) —— 厂家自定义，对应 via.json 的 customKeycodes
QKKB = {
0x7E00:'BT1',        # DEV BT1
0x7E01:'BT2',        # DEV BT2
0x7E02:'BT3',        # DEV BT3
0x7E03:'2.4G',       # DEV 2.4G
0x7E04:'USB',        # DEV USB
0x7E05:'WHITE',      # display test white
0x7E06:'BATQ',       # HS_BATQ
0x7E07:'NOSEC',      # Bluetooth no secret pairing channel
0x7E08:'RECLT',      # Recording lighting effects
}

# QK_LIGHTING (0x7800-0x78FF)
QKLIGHT = {
0x7800:'BL_ON',0x7801:'BL_OFF',0x7802:'BL_TOGG',0x7803:'BL_DEC',0x7804:'BL_INC',0x7805:'BL_STEP',
0x7806:'BL_BRTG',0x7810:'LM_ON',0x7811:'LM_OFF',0x7812:'LM_TOGG',0x7813:'LM_NEXT',0x7814:'LM_PREV',
0x7815:'LM_BRIU',0x7816:'LM_BRID',0x7817:'LM_SPDU',0x7818:'LM_SPDD',0x7819:'LM_FLGN',0x781A:'LM_FLGP',
0x7820:'UG_TOGG',0x7821:'UG_NEXT',0x7822:'UG_PREV',0x7823:'UG_HUEU',0x7824:'UG_HUED',
0x7825:'UG_SATU',0x7826:'UG_SATD',0x7827:'UG_VALU',0x7828:'UG_VALD',0x7829:'UG_SPDU',0x782A:'UG_SPDD',
0x7830:'RM_ON',0x7831:'RM_OFF',0x7832:'RM_TOGG',0x7833:'RM_NEXT',0x7834:'RM_PREV',
0x7835:'RM_HUEU',0x7836:'RM_HUED',0x7837:'RM_SATU',0x7838:'RM_SATD',0x7839:'RM_VALU',0x783A:'RM_VALD',
0x783B:'RM_SPDU',0x783C:'RM_SPDD',
}

# QK_QUANTUM (0x7C00-0x7DFF)
QKQUANT = {
0x7C00:'QK_BOOT',0x7C01:'QK_REBOOT',0x7C02:'QK_DEBUG',0x7C03:'QK_CLR_EE',0x7C04:'QK_MAKE',
0x7C16:'QK_GESC',0x7C17:'QK_VELOCI',
}

def name(c):
    if c in QKKB: return QKKB[c]
    if c in QKLIGHT: return QKLIGHT[c]
    if c in QKQUANT: return QKQUANT[c]
    if c in BASE: return BASE[c]
    # 修饰键 (0x0100-0x1FFF)
    if 0x0100 <= c < 0x2000:
        mods = []
        if c & 0x0100: mods.append('C')
        if c & 0x0200: mods.append('S')
        if c & 0x0400: mods.append('A')
        if c & 0x0800: mods.append('G')
        base = c & 0x00FF
        bn = BASE.get(base, '%02X' % base)
        return '+'.join(mods) + '(' + bn + ')'
    # 层相关
    if 0x5200 <= c <= 0x521F: return 'TO(%d)' % (c & 0x1F)
    if 0x5220 <= c <= 0x523F: return 'MO(%d)' % (c & 0x1F)
    if 0x5240 <= c <= 0x525F: return 'DF(%d)' % (c & 0x1F)
    if 0x5260 <= c <= 0x527F: return 'TG(%d)' % (c & 0x1F)
    if 0x5280 <= c <= 0x529F: return 'OSL(%d)' % (c & 0x1F)
    if 0x52A0 <= c <= 0x52BF: return 'TT(%d)' % (c & 0x1F)
    # 宏
    if 0x7700 <= c <= 0x777F: return 'M%d' % (c & 0x7F)
    # 其余 QK_KB / QK_USER
    if 0x7E00 <= c <= 0x7E3F: return 'KB%02X' % (c - 0x7E00)
    if 0x7800 <= c <= 0x78FF: return 'LG%02X' % (c - 0x7800)
    if 0x7C00 <= c <= 0x7DFF: return 'QT%02X' % (c - 0x7C00)
    if 0x7E40 <= c <= 0x7FFF: return 'US%02X' % (c - 0x7E40)
    return '%04X' % c

rows = via['layouts']['keymap']
out = []
out.append('# MAX102 键位表（从键盘 EEPROM 实读，非猜测）')
out.append('# PROTOCOL_VERSION=%s  FIRMWARE_VERSION=%s  LAYER_COUNT=%s'
           % (d.get('protocol_version'), d.get('firmware_version'), d.get('layer_count')))
out.append('')
for L in range(d['layer_count']):
    buf = km['layer_%d' % L]
    out.append('=' * 100)
    out.append('LAYER %d' % L)
    out.append('=' * 100)
    for row in rows:
        cells = []
        for cell in row:
            if isinstance(cell, str):
                r, c = map(int, cell.split(','))
                cells.append('%-8s' % name(buf[r * 19 + c]))
        out.append(' '.join(cells))
    out.append('')

txt = '\n'.join(out)
OUT.write_text(txt, encoding='utf-8')
print('已写入: %s' % OUT, file=sys.stdout)
sys.stdout.buffer.write(txt.encode('utf-8'))
