# -*- coding: utf-8 -*-
"""
用一张 CAD 截图反解底图配准参数（像素级，不靠车道中心估算）。

原理：截图里轨迹线是纯色（青 0,255,255 / 绿 0,255,0），照片是同一张图等比缩放，
      于是可求 (比例 s, 锚点像素 X/Y)，使「世界坐标里的轨迹」投影后与截图里的轨迹像素重合。
输出 photo_geo.json（CAD 原始坐标，x0=西边缘, y0=南边缘）。

用法: python -X utf8 calibrate_from_shot.py <截图路径>
"""
import os, sys, json
import numpy as np
from PIL import Image
import leaf_common as L

BASE = L.BASE
DXF_PHOTO = os.path.join(BASE, 'photo.png')


def dist_map(mask, maxd=60):
    """到最近轨迹像素的近似距离场（迭代膨胀，8 邻域）"""
    import collections
    H, W = mask.shape
    D = np.full((H, W), maxd, dtype=np.float32)
    q = collections.deque()
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        D[y, x] = 0.0
        q.append((y, x))
    while q:
        y, x = q.popleft()
        d = D[y, x]
        if d >= maxd:
            continue
        for dy, dx, w in ((-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1),
                          (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W:
                nd = d + w
                if nd < D[ny, nx]:
                    D[ny, nx] = nd
                    q.append((ny, nx))
    return D


def main():
    shot = sys.argv[1] if len(sys.argv) > 1 else None
    if not shot or not os.path.exists(shot):
        print('用法: calibrate_from_shot.py <截图>'); return 1

    a = np.asarray(Image.open(shot).convert('RGB'), dtype=np.int16)
    Hs, Ws, _ = a.shape
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    cyan = (r < 60) & (g > 200) & (b > 200)
    green = (r < 60) & (g > 200) & (b < 80)
    mask = cyan | green
    print('截图 %dx%d，轨迹像素 %d' % (Ws, Hs, int(mask.sum())))
    D = dist_map(mask)

    ph = Image.open(DXF_PHOTO)
    Wp, Hp = ph.size
    k = Ws / float(Wp)                     # 截图 = 照片 × k
    print('截图/照片 比例 k = %.4f' % k)

    raw = json.load(open(os.path.join(BASE, '_traj.json'), encoding='utf-8'))
    cab = np.array(raw['cab'], float) / 1000.0
    trl = np.array(raw['trailer'], float) / 1000.0
    pts = np.vstack([cab[::4], trl[::4]])
    ns_x = float(np.median(cab[-len(cab) // 4:, 0]))
    ew_y = float(np.median(cab[:len(cab) // 5, 1]))

    def score(s, ax, ay):
        px = np.rint(ax + s * (pts[:, 0] - ns_x)).astype(int)
        py = np.rint(ay - s * (pts[:, 1] - ew_y)).astype(int)
        ok = (px >= 0) & (px < Ws) & (py >= 0) & (py < Hs)
        if ok.sum() < len(pts) * 0.6:
            return 1e9
        return float(D[py[ok], px[ok]].mean())

    # 粗搜（围绕车道检测给出的初值）
    best = (1e9, 3.37, 821 * k, 376 * k)
    for s in np.arange(2.9, 4.1, 0.05):
        for ax in np.arange(780 * k, 900 * k, 4):
            for ay in np.arange(330 * k, 440 * k, 4):
                v = score(s, ax, ay)
                if v < best[0]:
                    best = (v, s, ax, ay)
    # 细搜
    v, s, ax, ay = best
    for ds in np.arange(-0.06, 0.061, 0.01):
        for dx in np.arange(-4, 4.1, 0.5):
            for dy in np.arange(-4, 4.1, 0.5):
                vv = score(s + ds, ax + dx, ay + dy)
                if vv < v:
                    v, s, ax, ay = vv, s + ds, ax + dx, ay + dy
    print('最佳: 截图比例 %.3f px/m，锚点 (%.1f, %.1f) px，平均偏差 %.2f px'
          % (s, ax, ay, v))

    # 换算到照片像素坐标
    s_p = s / k
    ax_p, ay_p = ax / k, ay / k
    geo = dict(file='photo.png',
               x0=ns_x - ax_p / s_p,
               y0=ew_y - (Hp - ay_p) / s_p,
               w=Wp / s_p, h=Hp / s_p,
               scale_px_per_m=s_p,
               anchor_px=[ax_p, ay_p], anchor_m=[ns_x, ew_y])
    json.dump(geo, open(os.path.join(BASE, 'photo_geo.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print('照片比例 %.3f px/m，覆盖 %.1f x %.1f m，西边缘 x=%.1f 南边缘 y=%.1f'
          % (s_p, geo['w'], geo['h'], geo['x0'], geo['y0']))

    # 出图核对
    im = Image.open(DXF_PHOTO).convert('RGB')
    from PIL import ImageDraw
    d = ImageDraw.Draw(im)
    for arr, col in ((cab, (0, 220, 255)), (trl, (0, 255, 130))):
        d.line([(ax_p + s_p * (p[0] - ns_x), ay_p - s_p * (p[1] - ew_y)) for p in arr],
               fill=col, width=3)
    im.save(os.path.join(BASE, '照片配准预览.png'))
    print('已保存 照片配准预览.png')
    return 0


if __name__ == '__main__':
    sys.exit(main())
