# -*- coding: utf-8 -*-
"""图纸还原对照图：只画 CAD 图纸元素（车道线 + 圆角弧 + 文字），不含车辆。
用于核对渲染后的图纸与 DXF 原图是否一致。"""
import os
import numpy as np
from PIL import Image, ImageDraw

import leaf_common as L

OUT = os.path.join(L.BASE, '图纸还原对照.png')

# 取路口 + 上下延伸范围
X0, X1 = 320.0, 480.0
Y0, Y1 = -170.0, -30.0
SC = 8.0                      # px/m

W = int((X1 - X0) * SC)
H = int((Y1 - Y0) * SC)
VIEW = (SC, np.array([0.0, 0.0]) - np.array([X0, Y0]) * SC)

img = Image.new('RGB', (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)

# 50m 网格
for gx in np.arange(np.ceil(X0 / 50) * 50, X1, 50):
    px = (gx - X0) * SC
    d.line([px, 0, px, H], fill=(238, 240, 244), width=1)
    d.text((px + 3, H - 16), '%dm' % gx, font=L.font(11), fill=(180, 185, 195))
for gy in np.arange(np.ceil(Y0 / 50) * 50, Y1, 50):
    py = (gy - Y0) * SC
    d.line([0, py, W, py], fill=(238, 240, 244), width=1)
    d.text((4, py - 14), '%dm' % gy, font=L.font(11), fill=(180, 185, 195))

# 道路边线
for a, b, c in L._lines:
    pa, pb = L.vpx(VIEW, [a, b])
    d.line([pa[0], pa[1], pb[0], pb[1]], fill=(70, 78, 92), width=2)

# 圆角弧（关键核对项）
for pts, c in L._arcs:
    pv = L.vpx(VIEW, np.array(pts, dtype=float))
    poly = [(float(p[0]), float(p[1])) for p in pv]
    d.line(poly, fill=(196, 74, 60), width=3)
    # 端点标记，确认与直线首尾相接
    for q in (poly[0], poly[-1]):
        d.ellipse([q[0] - 5, q[1] - 5, q[0] + 5, q[1] + 5], outline=(196, 74, 60), width=2)

# 文字
for x, y, col, segs in L._texts:
    s = ''.join(t for _c, t in segs)
    px, py = L.vpx(VIEW, [(x, y)])[0]
    f = L.font(16)
    tw = int(d.textlength(s, font=f))
    d.text((px - tw / 2, py - 8), s, font=f, fill=(40, 44, 52))

# 轨迹（浅色参考）
for p, col in ((L.cab, (0, 162, 208)), (L.trl, (34, 172, 92))):
    pv = L.vpx(VIEW, p)
    d.line([(float(q[0]), float(q[1])) for q in pv], fill=col + (255,) if False else col, width=2)

d.rectangle([0, 0, W - 1, H - 1], outline=(210, 214, 222), width=2)
d.rectangle([8, 8, 300, 40], fill=(255, 255, 255))
d.text((14, 14), 'CAD 图纸元素还原核对（弧线=红）', font=L.font(15, True), fill=(30, 34, 40))

img.save(OUT)
print('已保存:', OUT, '%dx%d  缩放 %.1f px/m' % (W, H, SC))
