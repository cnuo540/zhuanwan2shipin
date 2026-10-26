# -*- coding: utf-8 -*-
"""轨迹还原核对图：把渲染用的轨迹点列直接画出来，并标出 DXF 样条控制点，
用于确认曲线是否贴合 CAD 原图（控制点应落在曲线内侧，曲线不应外凸成波浪）。"""
import os
import numpy as np
import ezdxf
from PIL import Image, ImageDraw

import leaf_common as L

DXF = r'D:\电脑桌面勿删\CAD文件夹\叶片车转弯轨迹.dxf'
OUT = os.path.join(L.BASE, '轨迹还原核对.png')

X0, X1 = 340.0, 520.0
Y0, Y1 = -110.0, 40.0
SC = 9.0
W = int((X1 - X0) * SC)
H = int((Y1 - Y0) * SC)
VIEW = (SC, np.array([0.0, 0.0]) - np.array([X0, Y0]) * SC)

img = Image.new('RGB', (W, H), (255, 255, 255))
d = ImageDraw.Draw(img)

for gx in np.arange(np.ceil(X0 / 20) * 20, X1, 20):
    px = (gx - X0) * SC
    d.line([px, 0, px, H], fill=(242, 244, 248), width=1)
for gy in np.arange(np.ceil(Y0 / 20) * 20, Y1, 20):
    py = (gy - Y0) * SC
    d.line([0, py, W, py], fill=(242, 244, 248), width=1)

# 道路
for a, b, c in L._lines:
    pa, pb = L.vpx(VIEW, [a, b])
    d.line([pa[0], pa[1], pb[0], pb[1]], fill=(170, 178, 190), width=1)

# 渲染用轨迹
for p, col in ((L.cab, (0, 150, 200)), (L.trl, (30, 160, 85))):
    pv = L.vpx(VIEW, p)
    d.line([(float(q[0]), float(q[1])) for q in pv], fill=col, width=3)

# DXF 样条控制点（应位于曲线内侧/外侧但与曲线有距离）
doc = ezdxf.readfile(DXF)
for e in doc.modelspace():
    if e.dxftype() != 'SPLINE':
        continue
    c = e.dxf.get('color', 256)
    cp = np.array([[p[0] / 1000.0, -p[1] / 1000.0] for p in e.control_points])
    col = (0, 150, 200) if c == 4 else (30, 160, 85)
    for q in L.vpx(VIEW, cp):
        d.ellipse([q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4],
                  outline=col, width=2)

d.rectangle([0, 0, W - 1, H - 1], outline=(208, 212, 220), width=2)
d.rectangle([8, 8, 430, 62], fill=(255, 255, 255))
d.text((14, 14), '轨迹还原核对：曲线=渲染轨迹，圆圈=DXF样条控制点', font=L.font(14, True), fill=(30, 34, 40))
d.text((14, 36), 'B样条控制点不在曲线上（曲线在其内侧），若轨迹外凸即为插值错误',
       font=L.font(11), fill=(110, 116, 128))

img.save(OUT)
print('已保存:', OUT, '%dx%d' % (W, H))
