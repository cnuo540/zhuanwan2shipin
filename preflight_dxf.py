# -*- coding: utf-8 -*-
"""新图纸预检：跑流水线前先确认 DXF 里轨迹/图片/其它图元是否齐全。

用法:
    python -X utf8 preflight_dxf.py <dxf路径> [--colors 车头色 车尾色]

默认按 车头=ACI 4(青) / 车尾=ACI 3(绿) 检查，与 make_videos.py 的
CAB_ACI, TRL_ACI 保持一致。返回码 0=可直接跑，1=缺轨迹。
"""
import sys, math
import ezdxf

RECOGNIZED = {'LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'MTEXT', 'SPLINE'}


def main():
    argv = [a for a in sys.argv[1:] if a != '--colors']
    if not argv:
        print(__doc__)
        return 2
    dxf = argv[0]
    cab_aci, trl_aci = ('4', '3')
    if '--colors' in sys.argv:
        i = sys.argv.index('--colors')
        cab_aci, trl_aci = sys.argv[i + 1], sys.argv[i + 2]

    try:
        doc = ezdxf.readfile(dxf)
    except Exception as e:
        print('读取失败:', e)
        return 1
    msp = doc.modelspace()

    from collections import Counter
    kinds, colors = Counter(), Counter()
    splines = []
    has_ole = ole_bytes = 0
    unknown = Counter()

    for e in msp:
        t = e.dxftype()
        c = e.dxf.get('color', 256)
        if c == 256:
            c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
        kinds[t] += 1
        colors[(t, c)] += 1
        if t not in RECOGNIZED and t != 'OLE2FRAME':
            unknown[t] += 1
        if t == 'SPLINE':
            splines.append((c, len(e.control_points), e.dxf.degree))
        if t == 'OLE2FRAME':
            pass  # 图片预览统一在循环后按原始字节解析

    # OLE 图片预览（ezdxf 不暴露 310 块，直接读原始字节）
    has_ole, ole_bytes, ole_emf = _ole_info(dxf)

    print('图纸: %s' % dxf)
    print('DXF 版本: %s' % doc.dxfversion)
    print('实体统计: %s' % dict(kinds))

    ok = True

    # --- 1. 两条轨迹 ---
    print()
    print('[1] 轨迹样条（必须有两条，颜色 %s 青 / %s 绿）' % (cab_aci, trl_aci))
    if len(splines) != 2:
        print('    ! 找到 %d 条 SPLINE，预期 2 条' % len(splines))
        ok = False
    for c, n, deg in splines:
        role = '车头(ACI %s)' % cab_aci if str(c) == cab_aci else (
            '车尾(ACI %s)' % trl_aci if str(c) == trl_aci else '颜色不匹配!')
        print('    ACI %-3s 控制点 %-4d %d 次样条 -> %s' % (c, n, deg, role))
        if str(c) not in (cab_aci, trl_aci):
            ok = False
    have_cab = any(str(c) == cab_aci for c, _, _ in splines)
    have_trl = any(str(c) == trl_aci for c, _, _ in splines)
    if not (have_cab and have_trl):
        print('    ! 缺少 %s 色轨迹；颜色对调时用 --colors %s %s'
              % ((cab_aci if not have_cab else trl_aci), trl_aci, cab_aci))
        ok = False
    else:
        print('    OK：两条轨迹齐备')

    # --- 2. 图片 ---
    print()
    print('[2] 航拍图片（OLE2FRAME 嵌入，非必需）')
    if has_ole and ole_bytes > 0 and ole_emf:
        print('    OK：发现 %d 个 OLE 对象，内含 EMF 预览 %.1f KB -> 会提取为 photo.png'
              % (has_ole, ole_bytes / 1024))
    elif has_ole and ole_bytes > 0:
        print('    OLE 对象 %d 个、%.1f KB，但未见 EMF 签名 -> 可能切不出图片'
              % (has_ole, ole_bytes / 1024))
    elif has_ole:
        print('    ! 有 OLE2FRAME 但没读到 310 数据 -> 出片将没有航拍底图（可用外部 photo.png）')
    else:
        print('    无：本图纸没有图片 -> 出片只有轨迹/图元，没有航拍底图')

    # --- 3. 其它图元 ---
    print()
    print('[3] 其它图元（会被还原进画面）')
    for t in ('LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'MTEXT'):
        if kinds.get(t):
            print('    %-12s x %d' % (t, kinds[t]))
    if unknown:
        print('    未识别（会被忽略，需要时再加）: %s' % dict(unknown))
    if not any(kinds.get(t) for t in ('LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'MTEXT')):
        print('    无（画面只有轨迹与车辆）')

    # --- 4. 轨迹几何概览 ---
    print()
    print('[4] 轨迹几何')
    for c, n, deg in splines:
        print('    ACI %-3s 控制点 %d -> 提取后按弧长等距重采样' % (c, n))

    print()
    print('=' * 56)
    print('结论：%s' % ('可以运行 make_videos.py' if ok else '不满足条件，先补轨迹/颜色'))
    print('=' * 56)
    return 0 if ok else 1


def _ole_info(path):
    """从原始 DXF 字节里读 OLE2FRAME：返回 (对象数, 310二进制总字节, 是否含EMF)

    ezdxf 把 OLE2FRAME 当代理实体，custom_tags 拿不到 310 块，只能自己解析文本对。
    """
    data = open(path, 'rb').read()
    i = data.find(b'OLE2FRAME')
    if i < 0:
        return 0, 0, False
    # 记录 = 从实体名到下一个实体（组码 0 开头的行）
    j = len(data)
    for sep in (b'\r\n  0\r\n', b'\n  0\n'):
        k = data.find(sep, i + 10)
        if k >= 0:
            j = min(j, k)
    rec = data[i:j]
    # 扫描该记录：组码 310 行的下一行是十六进制块（图层名也可能恰好是 "0"，
    # 所以不能按值 0 断，只能靠行相等判断 310）
    lines = rec.splitlines()
    total, blob = 0, bytearray()
    k = 0
    while k + 1 < len(lines):
        if lines[k].strip() == b'310':
            try:
                b = bytes.fromhex(lines[k + 1].strip().decode('ascii'))
            except Exception:
                b = b''
            total += len(b)
            blob += b              # 全量解码，EMF 签名可能不在最前面
            k += 2
            continue
        k += 1
    # 预览是 EMF：解码后的头 40 字节附近会有 " EMF" 签名
    emf = b' EMF' in blob or b'EMF' in blob
    return data.count(b'OLE2FRAME'), total, emf


if __name__ == '__main__':
    sys.exit(main())
