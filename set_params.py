# -*- coding: utf-8 -*-
"""按采集到的参数修改项目配置（改完即可直接渲染）。

用法:
  python -X utf8 set_params.py --dxf "D:\\图纸\\新图纸.dxf" ^
         --beam 58 --blade 108 --worker 50 --escort 60 --dir forward

参数:
  --dxf      CAD 图纸路径        -> make_videos.py  DEFAULT_DXF
  --beam     挂车梁长 m          -> leaf_common.py  COUPLE_L
  --blade    叶片长度 m          -> leaf_common.py  BLADE_L
  --worker   小机工距尾部 m      -> leaf_common.py  WORKER_GAP
  --escort   皮卡距尾部 m        -> leaf_common.py  ESCORT_GAP
  --dir      forward | reverse   -> make_videos.py  DEFAULT_REVERSE
             forward=正向(东→西,左转向南)  reverse=反向(南→北,右转向东)

只传需要改的项，未传的保持原值。
- 读写都用 newline=''，不做换行转换，保证改不到的字节逐字节不变
- 行尾注释（# ...）原样保留
- 找不到目标行会明确报错，不会静默失败
"""
import argparse
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
LC = os.path.join(BASE, 'leaf_common.py')
MV = os.path.join(BASE, 'make_videos.py')


def _read(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def _write(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def _patch(path, pattern, value, label):
    """pattern 三个捕获组: (前缀, 旧值, 行尾注释)；只把"旧值"换成 value，
    前缀与注释原样保留，换行符不动，因此等值调用是逐字节不变的。"""
    src = _read(path)
    m = re.search(pattern, src, re.M)
    if not m:
        raise SystemExit('[失败] %s 中找不到 %s' % (os.path.basename(path), label))
    new = '%s%s%s' % (m.group(1), value, m.group(3) or '')
    _write(path, src[:m.start()] + new + src[m.end():])
    print('  %-16s %s' % (label, new.strip()))
    return m.group(0)


def set_number(path, var, value):
    _patch(path,
           r'^(%s\s*=\s*)([^\r\n#]*?)([ \t]*#[^\r\n]*)?(?=\r?$)' % re.escape(var),
           '%.1f' % value, var)


def set_bool(path, var, value):
    _patch(path,
           r'^(%s\s*=\s*)(True|False)([ \t]*#[^\r\n]*)?(?=\r?$)' % re.escape(var),
           'True' if value else 'False', var)


def set_default_dxf(dxf):
    src = _read(MV)
    m = re.search(r'^(DEFAULT_DXF\s*=\s*)([^\r\n]*?)([ \t]*#[^\r\n]*)?(?=\r?$)', src, re.M)
    if not m:
        raise SystemExit('[失败] make_videos.py 中找不到 DEFAULT_DXF')
    if os.path.dirname(os.path.abspath(dxf)) == os.path.abspath(BASE):
        # 图纸放在项目内：写成相对(__file__)形式，保持可移植
        value = 'os.path.join(os.path.dirname(os.path.abspath(__file__)), %s)' % (
            json.dumps(os.path.basename(dxf), ensure_ascii=False),)
    else:
        value = json.dumps(os.path.abspath(dxf), ensure_ascii=False)
    new = '%s%s%s' % (m.group(1), value, m.group(3) or '')
    _write(MV, src[:m.start()] + new + src[m.end():])
    print('  %-16s %s' % ('DEFAULT_DXF', new.strip()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dxf', help='CAD 图纸路径')
    ap.add_argument('--beam', type=float, help='挂车梁长 m')
    ap.add_argument('--blade', type=float, help='叶片长度 m')
    ap.add_argument('--worker', type=float, help='小机工距尾部 m')
    ap.add_argument('--escort', type=float, help='皮卡距尾部 m')
    ap.add_argument('--dir', choices=['forward', 'reverse'], dest='direction',
                    help='起始方向 forward=正向(东→西) / reverse=反向(南→北)')
    a = ap.parse_args()

    if not any([a.dxf, a.beam, a.blade, a.worker, a.escort, a.direction]):
        ap.print_help()
        print('\n提示: 至少给一项要改的参数。')
        return 2

    # 先校验再写盘，避免落非法值
    for name, v in (('COUPLE_L', a.beam), ('BLADE_L', a.blade),
                    ('WORKER_GAP', a.worker), ('ESCORT_GAP', a.escort)):
        if v is not None and v <= 0:
            raise SystemExit('[失败] %s 必须为正数: %s' % (name, v))

    print('写入 %s' % BASE)
    if a.beam is not None:
        set_number(LC, 'COUPLE_L', a.beam)
    if a.blade is not None:
        set_number(LC, 'BLADE_L', a.blade)
    if a.worker is not None:
        set_number(LC, 'WORKER_GAP', a.worker)
    if a.escort is not None:
        set_number(LC, 'ESCORT_GAP', a.escort)
    if a.direction is not None:
        # DEFAULT_REVERSE=True 表示反向，故 forward 对应 False
        set_bool(MV, 'DEFAULT_REVERSE', a.direction == 'reverse')
    if a.dxf:
        set_default_dxf(a.dxf)

    print('完成。下一步:')
    print('  python -X utf8 make_videos.py --no-render   # 验收参数')
    print('  python -X utf8 make_videos.py               # 渲染出片')
    return 0


if __name__ == '__main__':
    sys.exit(main())
