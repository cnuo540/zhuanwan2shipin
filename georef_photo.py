# -*- coding: utf-8 -*-
"""
航拍底图地理配准：算出身位并写 photo_geo.json

思路（无需控制点、可复现）：
  1) 从照片测出「东西向道路」上下两条车行道中心行、「南北向道路」左右两条车行道中心列
  2) 车头在东西段是西行 → 走北侧（上面那条）车行道；在南北段是北行 → 走东侧（右边那条）车行道
  3) 用这两条车行道中心作为锚点，把轨迹的两个直段钉到照片上的车道中心
  4) 比例 s 由车行道宽度/标准车道宽标定，也可用 --scale 手动指定

用法:
    python -X utf8 georef_photo.py                 # 自动测车道 + 默认比例
    python -X utf8 georef_photo.py --scale 3.0     # 手动指定 px/m
"""
import os, sys, json, argparse
import numpy as np
from PIL import Image, ImageDraw

import leaf_common as L

BASE = L.BASE


def road_mask(img):
    a = np.asarray(img.convert('RGB'), dtype=np.float32) / 255.0
    mx = a.max(2); mn = a.min(2)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0)
    return ((sat < 0.10) & (mx > 0.45)).astype(np.float32)


def bands(prof, thr=0.55, minw=15):
    """一维剖面上的连续高值段 → [(start, end, center, strength)]"""
    idx = np.where(prof > thr * prof.max())[0]
    if len(idx) == 0:
        return []
    out = []
    for seg in np.split(idx, np.where(np.diff(idx) > 4)[0] + 1):
        if len(seg) >= minw:
            out.append((int(seg[0]), int(seg[-1]),
                        float((seg[0] + seg[-1]) / 2.0), float(prof[seg].mean())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scale', type=float, default=2.80, help='像素/米（默认 2.80）')
    a = ap.parse_args()

    img = Image.open(os.path.join(BASE, 'photo.png')).convert('RGB')
    W, H = img.size
    m = road_mask(img)

    # 东西向道路：用整幅行剖面（主路横贯全图，局部建筑硬地不会占满整行）
    rows = bands(m.mean(axis=1))
    # 南北向道路：用顶部横条列剖面（避开路口，两条车行道分得开）
    cols = bands(m[0:250, :].mean(axis=0))
    if len(rows) < 2 or len(cols) < 2:
        print('车道检测失败：行带 %d 个、列带 %d 个' % (len(rows), len(cols)))
        return 1
    # 主车行道 = 最宽的两条带（其余是路肩/辅道/建筑硬地）
    rows = sorted(sorted(rows, key=lambda t: t[1] - t[0])[-2:], key=lambda t: t[2])
    cols = sorted(sorted(cols, key=lambda t: t[1] - t[0])[-2:], key=lambda t: t[2])
    # 车头：由东向西（走北侧车道）→ 左转向南（走西侧车道）
    py = rows[0][2]          # 上侧/北侧车行道 ← 西行段
    px = cols[0][2]          # 左侧/西侧车行道 ← 南行段
    print('东西向车行道: %s' % ['%.0f(宽%d)' % (r[2], r[1] - r[0] + 1) for r in rows])
    print('南北向车行道: %s' % ['%.0f(宽%d)' % (c[2], c[1] - c[0] + 1) for c in cols])
    print('锚点: 东西段→行 %.0f 像素(北侧), 南北段→列 %.0f 像素(西侧)' % (py, px))

    # 车头两个直段的世界坐标（直接读原始 CAD 数据，避免受 MIRROR_Y 影响）
    raw = json.load(open(os.path.join(BASE, '_traj.json'), encoding='utf-8'))
    cab = np.array(raw['cab'], dtype=float) / 1000.0
    trl = np.array(raw['trailer'], dtype=float) / 1000.0
    ew_y = float(np.median(cab[:len(cab) // 5, 1]))          # 东西段
    ns_x = float(np.median(cab[-len(cab) // 4:, 0]))         # 南北段
    print('车头: 东西段 y=%.1f m, 南北段 x=%.1f m' % (ew_y, ns_x))

    s = a.scale
    # 像素 → 世界（CAD 原始坐标，+y = 北）：
    #   px = anchor_x + s*(x - ns_x)      东在右
    #   py = anchor_y - s*(y - ew_y)      北在上（照片行 0 = 北）
    geo = dict(file='photo.png',
               x0=ns_x - px / s,                 # 图像西边缘
               y0=ew_y - (H - py) / s,           # 图像南边缘
               w=W / s, h=H / s,
               scale_px_per_m=s,
               anchor_px=[px, py], anchor_m=[ns_x, ew_y])
    json.dump(geo, open(os.path.join(BASE, 'photo_geo.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('覆盖 %.1f x %.1f m，西边缘 x=%.1f，南边缘 y=%.1f'
          % (geo['w'], geo['h'], geo['x0'], geo['y0']))

    # 核对图（画在照片上，与 CAD 同朝向）
    prev = img.copy(); d = ImageDraw.Draw(prev)
    for pts, col in ((cab, (0, 220, 255)), (trl, (0, 255, 130))):
        d.line([(px + s * (p[0] - ns_x), py - s * (p[1] - ew_y)) for p in pts],
               fill=col, width=3)
    prev.save(os.path.join(BASE, '照片配准预览.png'))
    print('已保存 照片配准预览.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
