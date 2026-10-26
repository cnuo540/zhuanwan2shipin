# -*- coding: utf-8 -*-
"""提取 DXF 图纸元素（车道边界、文字、轨迹线），补充进 _traj.json 供渲染使用"""
import sys, json, os
import math
import ezdxf

def parse_mtext(raw):
    """MTEXT：保留纯文字 + 段内颜色码 \\Cn（渲染端用段颜色绘制）"""
    out = []
    i = 0
    color = None
    cur = ''
    while i < len(raw):
        if raw.startswith('\\C', i):
            # 颜色码变更：先 flush 当前段，再解析新颜色
            if cur:
                out.append((color, cur)); cur = ''
            j = raw.find(';', i + 2)
            j = i + 2 if j < 0 else j
            code = raw[i + 2:j]
            try:
                color = int(code)
            except ValueError:
                color = None
            i = j + 1
        elif raw[0 + i] == '{' or raw[i] == '}':
            i += 1
        elif raw[i] == '\\':
            # 未知格式串（字体、高度等）：跳到该串结束的分号
            j = raw.find(';', i)
            i = j + 1 if j >= 0 else i + 1
        else:
            cur += raw[i]
            i += 1
    if cur:
        out.append((color, cur))
    return out

def extract(dxf_path, out_path):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    data = {}
    for e in msp:
        t = e.dxftype()
        if t == 'LINE':
            c = e.dxf.get('color', 256)
            if c == 256:
                c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
            data.setdefault('lines', []).append([
                [float(e.dxf.start.x), float(e.dxf.start.y)],
                [float(e.dxf.end.x), float(e.dxf.end.y)], int(c)])
        elif t in ('ARC', 'CIRCLE'):
            c = e.dxf.get('color', 256)
            if c == 256:
                c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
            # 用 ezdxf 原生 flattening：正确处理 OCS/挤出方向，且弦高误差 ≤0.05m
            pts = [[float(p[0]), float(p[1])] for p in e.flattening(0.05)]
            data.setdefault('arcs', []).append([pts, int(c)])
        elif t == 'LWPOLYLINE':
            c = e.dxf.get('color', 256)
            if c == 256:
                c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
            # 带 bulge 的先展平成折线，普通折线直接取点
            try:
                pts = [[float(p[0]), float(p[1])] for p in e.flattening(0.05)]
            except Exception:
                pts = [[float(x), float(y)] for x, y in e.get_points('xy')]
            if e.closed and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            if len(pts) >= 2:
                data.setdefault('arcs', []).append([pts, int(c)])
        elif t == 'MTEXT':
            c = e.dxf.get('color', 256)
            if c == 256:
                c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
            x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
            segs = parse_mtext(e.text)
            data.setdefault('texts', []).append({'x': x, 'y': y,
                                                 'color': int(c), 'segs': segs})
    # 合并进已有 _traj.json（cab/trailer）
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    traj_path = os.path.join(base, '_traj.json')
    if os.path.exists(traj_path):
        with open(traj_path, encoding='utf-8') as f:
            d = json.load(f)
    else:
        d = {}
    d.update(data)
    with open(traj_path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False)
    n_l = len(data.get('lines', [])); n_a = len(data.get('arcs', [])); n_t = len(data.get('texts', []))
    print('图纸元素: LINE=%d ARC=%d MTEXT=%d -> %s' % (n_l, n_a, n_t, os.path.basename(traj_path)))
    for t_ in data.get('texts', []):
        print('  MTEXT (%.0f, %.0f): %s' % (t_['x'], t_['y'], t_['segs']))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('用法: python extract_drawing.py <dxf路径>')
        sys.exit(1)
    extract(sys.argv[1], None)
