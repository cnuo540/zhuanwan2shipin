# -*- coding: utf-8 -*-
"""
叶片车行走轨迹模拟 · 横版 16:9（1920×1080，适合汇报/PPT）
轨迹: CAD 青色 SPLINE=车头, 绿色 SPLINE=挂车尾部（挂车尾部配合车头按路线前进）
布局: 左=全局轨迹俯瞰  右上=车辆局部放大  右中=工程指标  右下=阶段/图例
输出: 叶片车行走模拟_横版.mp4
"""
import os, sys, subprocess
import numpy as np
from PIL import Image, ImageDraw

import leaf_common as L

OUT_MP4 = os.path.join(L.BASE, '叶片车行走模拟_横版.mp4')
FRAMES_DIR = os.path.join(L.BASE, 'frames_wide')

W, H = 1920, 1080
HEAD_H = 76
FOOT_H = 0

allp = np.vstack([L.cab, L.trl])
# 把道路边线/弧线端点也纳入视野，保证图纸元素不超出画布
for a, b, c in L._lines:
    allp = np.vstack([allp, [a, b]])
for pts, c in L._arcs:
    arr = np.array(pts, dtype=float)
    allp = np.vstack([allp, arr.min(axis=0), arr.max(axis=0)])
# 叶片（BLADE_L 很长）扫过的范围也纳入视野，避免被画布裁掉
for _f in range(0, L.NFR, 12):
    _st = L.state(_f)
    _td = np.array([np.cos(_st['tang']), np.sin(_st['tang'])])
    allp = np.vstack([allp,
                      _st['cargo_c'] - _td * (L.BLADE_L / 2.0),
                      _st['cargo_c'] + _td * (L.BLADE_L / 2.0)])
# 航拍底图范围也纳入视野
if L.HAS_PHOTO:
    g = L._photo_geo
    allp = np.vstack([allp, [[g['x0'], g['y0']],
                             [g['x0'] + g['w'], g['y0'] + g['h']]]])
pad = 14.0
xmin, ymin = allp.min(axis=0) - pad
xmax, ymax = allp.max(axis=0) + pad
# ---- 区域划分（按内容宽高比排版，主图与放大窗紧凑居中）----
if L.HAS_PHOTO:
    MH = H - HEAD_H - 250                     # 主图可用高度（底部留 250 给信息条）
    ISZ = 560                                 # 放大窗边长（装下整车队：车头→尾部→小机工→皮卡）
    MSCALE = min((W - ISZ - 60.0) / (xmax - xmin), MH / (ymax - ymin))
    MW = MSCALE * (xmax - xmin)               # 主图实际使用宽度
    GAP = 28
    OX = max(0.0, (W - (MW + GAP + ISZ)) / 2.0)
    MX0, MY0 = int(OX), HEAD_H
    IX0, IY0 = int(OX + MW + GAP), int(HEAD_H + (MH - ISZ) / 2.0)
    GX0, GY0, GW, GH = 0, 0, 0, 0             # 数据面板已移除
    BX0, BY0, BW, BH = 0, H - 250, W, 250
else:
    MX0, MY0, MW, MH = 0, HEAD_H, 860, H - HEAD_H
    IX0, IY0, ISZ = 880, 96, 640
    GX0, GY0, GW, GH = 1544, 96, 356, 640
    BX0, BY0, BW, BH = 880, 760, 1020, 280
    MSCALE = min(MW / (xmax - xmin), MH / (ymax - ymin))

MWORLD = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)
MAIN_V = L.make_view(MSCALE, (MW, MH), MWORLD, origin_px=(MX0, MY0))

# 放大视图：视野需容纳 车头↔皮卡 整列车队（按全程最大间距定档）
ISCALE = min(MSCALE * 2.2, ISZ / (L.SPAN_MAX * 1.16))

f11, f12, f13, f15, f17, f26 = (L.font(11), L.font(12), L.font(13),
                                L.font(15), L.font(17, True), L.font(26, True))
f20 = L.font(20, True)

# ---------------- 静态背景 ----------------
bg = Image.new('RGB', (W, H), (247, 248, 251))
d = ImageDraw.Draw(bg)

# 主图网格
for m in np.arange(np.ceil(xmin / 50) * 50, xmax, 50):
    p = L.vpx(MAIN_V, [[m, ymin]])[0]
    if MX0 <= p[0] <= MX0 + MW:
        d.line([p[0], MY0, p[0], MY0 + MH], fill=(233, 235, 240), width=1)
        d.text((p[0] + 3, MY0 + MH - 16), '%dm' % m, font=f11, fill=(170, 175, 185))
for m in np.arange(np.ceil(ymin / 50) * 50, ymax, 50):
    p = L.vpx(MAIN_V, [[xmin, m]])[0]
    d.line([MX0, p[1], MX0 + MW, p[1]], fill=(233, 235, 240), width=1)
    d.text((MX0 + 4, p[1] - 14), '%dm' % m, font=f11, fill=(170, 175, 185))

# 航拍底图（有则铺在主图最底层；网格已画，底图会覆盖，故先网格后底图再叠加线）
if L.HAS_PHOTO:
    L.paste_photo(bg, MAIN_V, clip=(MX0, MY0, MX0 + MW, MY0 + MH))
    d = ImageDraw.Draw(bg)
    # 底图上重画网格刻度文字，保持可读
    for m in np.arange(np.ceil(xmin / 50) * 50, xmax, 50):
        p = L.vpx(MAIN_V, [[m, ymin]])[0]
        if MX0 <= p[0] <= MX0 + MW:
            d.text((p[0] + 3, MY0 + MH - 16), '%dm' % m, font=f11, fill=(90, 96, 108))

# 主图道路背景（图纸元素：车道线 / 弧线）
L.draw_drawing_elements(d, MAIN_V, show_roads=True, show_texts=False)

# 主图两条轨迹
d.line(list(L.vpx(MAIN_V, L.cab).ravel()), fill=L.C_CAB_TRAJ, width=3)
d.line(list(L.vpx(MAIN_V, L.trl).ravel()), fill=L.C_TRL_TRAJ, width=3)

# 主图道路文字标注
L.draw_drawing_elements(d, MAIN_V, show_roads=False, show_texts=True, text_font=13)

for pts, col, nm in ((L.cab, L.C_CAB_TRAJ, '车头'), (L.trl, L.C_TRL_TRAJ, '挂车')):
    for p, tag in ((pts[0], '起'), (pts[-1], '终')):
        q = L.vpx(MAIN_V, [p])[0]
        d.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], fill=col, outline=(255, 255, 255))
        d.text((q[0] + 9, q[1] - 8), '%s%s' % (nm, tag), font=f11, fill=col)

# 竖分隔线
d.line([MW - 1, HEAD_H, MW - 1, H], fill=(214, 218, 226), width=1)

# ---------------- 渲染 ----------------
os.makedirs(FRAMES_DIR, exist_ok=True)
print('横版 %dx%d  主图 %.2f px/m  主图世界 %.0fx%.0fm'
      % (W, H, MSCALE, xmax - xmin, ymax - ymin))

TEST_N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
LOOP, STEP = L.NFR, (max(1, L.NFR // TEST_N) if TEST_N else 1)

# 剪掉片头：前 ~2.5s（就位 + 装载）不需要，直接从满载行驶阶段开始
START_F = int(round(L.P2 * (L.NFR - 1)))
print('片头裁剪 %d 帧（%.2fs）→ 成片 %.1f s'
      % (START_F, START_F / L.FPS, (LOOP - START_F) / L.FPS))
if not TEST_N:
    import shutil
    if os.path.isdir(FRAMES_DIR):
        shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)

for f in range(START_F, LOOP, STEP):
    st = L.state(f)
    ph, u = st['ph'], st['u']
    alpha = L.blade_alpha(f, ph)

    img = bg.copy()
    dr = ImageDraw.Draw(img)

    # ---- 主图：已走轨迹 + 车辆 ----
    if st['ci'] > 0:
        dr.line(list(L.vpx(MAIN_V, L.cab[:st['ci'] + 1]).ravel()),
                fill=L.C_CAB_TRAJ_DONE, width=4)
    if st['ti'] > 0:
        dr.line(list(L.vpx(MAIN_V, L.trl[:st['ti'] + 1]).ravel()),
                fill=L.C_TRL_TRAJ_DONE, width=4)
    L.draw_vehicle(dr, MAIN_V, st, alpha)
    L.draw_hitch(dr, MAIN_V, st['hitch'])
    # 跟随皮卡：同一青线，落后主车 ESCORT_GAP 米
    L.draw_pickup(dr, MAIN_V, st['pk'], np.radians(st['pk_deg']),
                  label='皮卡', label_font=f11)
    L.draw_worker(dr, MAIN_V, st['wk'], label='小机工', label_font=f11)

    # 主图上标注放大区域
    rc = ISZ / ISCALE / 2.0
    z0 = L.vpx(MAIN_V, [[st['inset_c'][0] - rc, st['inset_c'][1] - rc]])[0]
    z1 = L.vpx(MAIN_V, [[st['inset_c'][0] + rc, st['inset_c'][1] + rc]])[0]
    dr.rectangle([z0[0], z0[1], z1[0], z1[1]], outline=(96, 166, 224), width=1)

    # ---- 局部放大视图 ----
    panel = Image.new('RGB', (ISZ, ISZ), (255, 255, 255))
    if L.HAS_PHOTO:
        L.paste_photo(panel, L.make_view(ISCALE, (ISZ, ISZ), st['inset_c']),
                      clip=(0, 0, ISZ, ISZ))
    pdr = ImageDraw.Draw(panel)
    IV = L.make_view(ISCALE, (ISZ, ISZ), st['inset_c'])
    # 放大视图内也画道路背景，保持局部上下文
    L.draw_drawing_elements(pdr, IV, show_roads=True, show_texts=True,
                            text_font=10, inset=(0, 0, ISZ, ISZ))
    a0, b0 = max(0, st['ci'] - 55), min(len(L.cab), st['ci'] + 56)
    pdr.line(list(L.vpx(IV, L.cab[a0:b0]).ravel()), fill=L.C_CAB_TRAJ, width=3)
    a1, b1 = max(0, st['ti'] - 55), min(len(L.trl), st['ti'] + 56)
    pdr.line(list(L.vpx(IV, L.trl[a1:b1]).ravel()), fill=L.C_TRL_TRAJ, width=3)
    L.draw_vehicle(pdr, IV, st, alpha)
    L.draw_hitch(pdr, IV, st['hitch'], r=8)
    L.draw_pickup(pdr, IV, st['pk'], np.radians(st['pk_deg']))
    L.draw_worker(pdr, IV, st['wk'])
    img.paste(panel, (IX0, IY0))
    dr.rectangle([IX0 - 1, IY0 - 1, IX0 + ISZ, IY0 + ISZ], outline=(150, 156, 168), width=2)
    dr.rectangle([IX0, IY0, IX0 + 250, IY0 + 28], fill=(38, 42, 50))
    dr.text((IX0 + 10, IY0 + 6), '局部放大  %.1f×' % (ISCALE / MSCALE), font=f12, fill=(226, 232, 240))

    # ---- 底部：阶段 + 图例 ----
    dr.rectangle([BX0, BY0, BX0 + BW, BY0 + BH], fill=(255, 255, 255), outline=(214, 218, 226))
    dr.text((BX0 + 16, BY0 + 12), '施工阶段', font=f12, fill=(120, 126, 138))
    sx = BX0 + 16
    sw = (BW - 32) // 4
    for i, nm in enumerate(L.PHASES):
        on = (i == ph)
        dr.rectangle([sx, BY0 + 36, sx + sw - 10, BY0 + 72],
                     fill=(38, 104, 84) if on else (240, 242, 246),
                     outline=(38, 104, 84) if on else (216, 220, 228))
        dr.text((sx + 12, BY0 + 46), nm, font=f12,
                fill=(232, 255, 245) if on else (140, 146, 158))
        sx += sw

    # 图例
    ly = BY0 + 98
    lx = BX0 + 16
    items = [('line', L.C_CAB_TRAJ, '车头轨迹（CAD 青线）'),
             ('line', L.C_TRL_TRAJ, '挂车尾部轨迹（CAD 绿线）'),
             ('box', L.C_CAB, '牵引车'),
             ('box', L.C_TRL, '挂车梁'),
             ('box', L.C_BLADE, '叶片货物'),
             ('box', L.C_ESC, '跟随皮卡'),
             ('box', L.C_WORKER, '小机工')]
    for kind, col, txt in items:
        if kind == 'line':
            dr.line([lx, ly + 7, lx + 22, ly + 7], fill=col, width=4)
        else:
            dr.rectangle([lx, ly, lx + 22, ly + 14], fill=col, outline=(70, 70, 70))
        dr.text((lx + 29, ly - 1), txt, font=f12, fill=(52, 56, 64))
        lx += 32 + len(txt) * 12 + 30

    # 挂车梁长是刚性定值，显示常量而非逐帧求解值
    info = ('牵引车 %.0fm · 挂车梁 %.1fm · 叶片 %.0fm · 车头轨迹(青) %.0fm · 挂车轨迹(绿) %.0fm'
            % (L.CAB_L, L.COUPLE_L, L.BLADE_L, L.CL, L.TL))
    dr.text((BX0 + 16, BY0 + 140), info, font=f11, fill=(110, 116, 128))
    note = ('约束：车头速度 %.1f m/s · 挂接点→车尾距离 = %.0f m（绿线上滑动求解，'
            '单帧步长受限）' % (L.SPEED, L.COUPLE_L))
    dr.text((BX0 + 16, BY0 + 162), note, font=f11, fill=(150, 156, 168))

    tag = {0: ('空载行驶', (60, 120, 190)), 1: ('装载中 %d%%' % int(alpha * 100), (150, 105, 10)),
           2: ('满载运输', (40, 150, 100)), 3: ('抵达终点', (150, 105, 10))}[ph]
    dr.text((BX0 + 16, BY0 + 196), tag[0], font=f15, fill=tag[1])

    # ---- 顶部标题条 ----
    dr.rectangle([0, 0, W, HEAD_H], fill=L.C_DARK)
    dr.text((24, 10), '叶片车行走轨迹模拟', font=f20, fill=(240, 244, 250))
    dr.text((24, 40), '车头走青线 · 挂车尾部走绿线 · 货物装载于挂车', font=f11, fill=(138, 145, 158))
    dr.text((W - 520, 12), 't = %5.1f s' % ((f - START_F) / L.FPS), font=f17, fill=(226, 232, 240))
    dr.text((W - 520, 42), '进度 %3.0f%%' % (u * 100), font=f12, fill=(150, 200, 170))
    pbx, pby, pbw = W - 360, 44, 300
    dr.rectangle([pbx, pby, pbx + pbw, pby + 8], fill=(52, 57, 66))
    dr.rectangle([pbx, pby, pbx + int(pbw * u), pby + 8], fill=(56, 168, 118))
    dr.text((W - 360, 14), '行程 %.1f / %.1f m' % (st['dist'], L.CL), font=f12, fill=(180, 186, 198))

    img.save(os.path.join(FRAMES_DIR, 'f_%04d.png' % (f - START_F)))
    if f % 60 == 0:
        print('  frame %d / %d' % (f, L.NFR))

if TEST_N:
    print('抽样自检完成')
    raise SystemExit(0)

print('合成视频 ...')
subprocess.run([L.FFMPEG, '-y', '-framerate', str(L.FPS),
                '-i', os.path.join(FRAMES_DIR, 'f_%04d.png'),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18',
                '-movflags', '+faststart', OUT_MP4], check=True)
print('完成:', OUT_MP4)
