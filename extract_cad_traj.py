# -*- coding: utf-8 -*-
"""
CAD 轨迹提取器：从 DXF 里按图元颜色抓出「车头轨迹」「挂车轨迹」两条 SPLINE，
插值成密集点列，保存为 _traj.json 供渲染脚本使用。

用法:
    python extract_cad_traj.py <dxf路径> [车头颜色ACI] [挂车颜色ACI]
默认: 绿色=3(车头)  青色=4(挂车)
"""
import sys, json, os
import numpy as np
import ezdxf


def resample_uniform(pts, step=0.40):
    """按弧长等距重采样（点间距≈step 米），保证求解器 max_step 的物理含义稳定"""
    p = np.asarray(pts, dtype=float)
    if len(p) < 2:
        return p
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(s[-1])
    if total <= 1e-9:
        return p
    n = max(2, int(round(total / step)) + 1)
    su = np.linspace(0.0, total, n)
    out = np.column_stack([np.interp(su, s, p[:, 0]), np.interp(su, s, p[:, 1])])
    return out


def ent_color(e, doc):
    c = e.dxf.get('color', 256)
    if c == 256:
        c = doc.layers.get(e.dxf.layer).dxf.get('color', 7)
    return c


def extract(dxf_path, cab_aci=3, trl_aci=4, reverse=False):
    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()
    res = {}
    for e in msp:
        if e.dxftype() != 'SPLINE':
            continue
        c = ent_color(e, doc)
        if c not in (cab_aci, trl_aci):
            continue
        # 关键：不能拿 B 样条的控制点去插值——控制点不在曲线上，会外凸成波浪。
        # 用 ezdxf 的 flattening 直接取曲线上的点（弦高误差 ≤0.02m），再按弧长等距重采样。
        # 注意：DXF 单位为毫米，故重采样步长取 400（=0.40 m，下游统一 /1000 转米）
        on_curve = [(p[0], p[1]) for p in e.flattening(0.02)]
        dense = resample_uniform(on_curve, step=400.0)
        if reverse:                      # 反向：起点/终点互换（行驶方向反转）
            dense = dense[::-1]
        key = 'cab' if c == cab_aci else 'trailer'
        if key in res:
            print('  警告: 颜色 %d 有多条 SPLINE，取第一条' % c)
            continue
        res[key] = dense.tolist()
        raw_len = float(np.sum(np.linalg.norm(np.diff(np.asarray(on_curve, float), axis=0), axis=1)))
        print('  %s (ACI %d): 控制点 %d -> 曲线上 %d 点 (%.1f m) -> 等距 %d 点'
              % (key, c, len(e.control_points), len(on_curve), raw_len, len(dense)))
    return res


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    dxf = sys.argv[1]
    rev = ('--reverse' in sys.argv) or ('-r' in sys.argv)
    argv = [a for a in sys.argv if not a.startswith('-')]
    cab_c = int(argv[2]) if len(argv) > 2 else 3
    trl_c = int(argv[3]) if len(argv) > 3 else 4
    print('读取:', dxf)
    if rev:
        print('  >> 反向模式：行驶方向反转（起终点互换）')
    data = extract(dxf, cab_c, trl_c, reverse=rev)
    if 'cab' not in data or 'trailer' not in data:
        print('错误: 未找齐两条轨迹，请确认颜色号')
        sys.exit(2)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_traj.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print('已保存:', out)
