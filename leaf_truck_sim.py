# -*- coding: utf-8 -*-
"""
叶片车行走轨迹 · 装载运输模拟视频
轨迹取自 CAD: D:\\电脑桌面勿删\\CAD文件夹\\叶片车行走轨迹.dxf
  青色 SPLINE = 车头(牵引车)轨迹   绿色 SPLINE = 挂车尾部轨迹
  挂车尾部配合车头按路线前进，保持 挂接点→车尾距离 = 30m
过程: 空车进场 -> 装载叶片 -> 满载行驶(车头走青线、挂车尾部走绿线，配合前进) -> 到达卸货
输出: 叶片车行走模拟.mp4
"""
import os, sys, json, subprocess, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_MP4 = os.path.join(BASE, '叶片车行走模拟.mp4')
FRAMES_DIR = os.path.join(BASE, 'frames3')
FFMPEG = (r'C:\Users\86136\AppData\Local\Microsoft\WinGet\Packages'
          r'\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe'
          r'\ffmpeg-8.1.1-full_build\bin\ffmpeg.exe')

FPS, DUR = 30, 16
NFR = FPS * DUR
MARGIN = 92
HEAD_H = 92                     # 顶部两行
FOOT_H = 42                     # 底部信息条
LEG_H = 40                      # 底部图例条

# ---- 车辆参数(米) ----
CAB_L, CAB_W = 8.0, 2.6
HITCH_OFF = 1.2
TRL_W = 3.6                  # 挂车梁宽度（比叶片宽，能露出车体边缘）
BLADE_L = 81.0               # 叶片长度
BLADE_ROOT, BLADE_TIP = 2.8, 0.9   # 叶片根部/尖端宽度

# ---------------- 轨迹与车辆模型（统一使用 leaf_common） ----------------
import leaf_common as LC
cab, trl = LC.cab, LC.trl
CL, TL = LC.CL, LC.TL

# ---------------- 画布 ----------------
allp = np.vstack([cab, trl])
# 道路背景端点也纳入视野
for a, b, c in LC._lines:
    allp = np.vstack([allp, [a, b]])
for pts, c in LC._arcs:
    arr = np.array(pts, dtype=float)
    allp = np.vstack([allp, arr.min(axis=0), arr.max(axis=0)])
# 叶片（BLADE_L 很长）扫过的范围也纳入视野，避免被画布裁掉
for _f in range(0, LC.NFR, 12):
    _st = LC.state(_f)
    _td = np.array([math.cos(_st['tang']), math.sin(_st['tang'])])
    allp = np.vstack([allp,
                      _st['cargo_c'] - _td * (LC.BLADE_L / 2.0),
                      _st['cargo_c'] + _td * (LC.BLADE_L / 2.0)])
# 航拍底图范围
if LC.HAS_PHOTO:
    g = LC._photo_geo
    allp = np.vstack([allp, [[g['x0'], g['y0']], [g['x0'] + g['w'], g['y0'] + g['h']]]])
pad = 14.0
xmin, ymin = allp.min(axis=0) - pad
xmax, ymax = allp.max(axis=0) + pad
SCALE = min(1400.0 / (xmax - xmin), 1200.0 / (ymax - ymin))
W = int((xmax - xmin) * SCALE) + 2 * MARGIN
H = int((ymax - ymin) * SCALE) + 2 * MARGIN + HEAD_H + FOOT_H + LEG_H
W -= W % 2
H -= H % 2

PLOT_BOT = H - FOOT_H - LEG_H - MARGIN     # 主图区域下边界

MAIN = (SCALE, np.array([MARGIN, HEAD_H + MARGIN]) - np.array([xmin, ymin]) * SCALE)

def vpx(view, p):
    sc, org = view
    p = np.atleast_2d(np.asarray(p, dtype=float))
    return p * sc + org

def font(sz, bold=False):
    names = ("msyhbd.ttc", "msyh.ttc", "simhei.ttf") if bold else ("msyh.ttc", "simhei.ttf", "arial.ttf")
    for n in names:
        pth = os.path.join(r'C:\Windows\Fonts', n)
        if os.path.exists(pth):
            try:
                return ImageFont.truetype(pth, sz)
            except Exception:
                pass
    return ImageFont.load_default()

F11, F12, F13, F15, F17 = font(11), font(12), font(13), font(15), font(17, True)

# ---------------- 图形基元（支持任意视口） ----------------
def rot_rect(center, ang, L, Wd):
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s], [s, c]])
    cs = np.array([[-L / 2, -Wd / 2], [L / 2, -Wd / 2], [L / 2, Wd / 2], [-L / 2, Wd / 2]])
    return cs @ R.T + np.asarray(center, dtype=float)

def draw_rect(dr, view, center, ang, L, Wd, fill, outline, ow=2, shadow=None):
    pp = vpx(view, rot_rect(center, ang, L, Wd))
    # 注意: Pillow 10.4 的 polygon 不接受 numpy 数组(静默不绘制)，必须转成 list[tuple]
    pts = [(float(x), float(y)) for x, y in pp]
    if shadow:
        dr.polygon([(x + 5.0, y + 7.0) for x, y in pts], fill=shadow)
    dr.polygon(pts, fill=fill, outline=outline, width=ow)

def draw_outline(dr, view, center, ang, L, Wd, outline, ow=3):
    """只描边不填充，用于把被货物遮住的挂车梁轮廓画回来"""
    pp = vpx(view, rot_rect(center, ang, L, Wd))
    pts = [(float(x), float(y)) for x, y in pp] + [(float(pp[0][0]), float(pp[0][1]))]
    dr.line(pts, fill=outline, width=ow, joint='curve')

def draw_blade(dr, view, center, ang, L, w_root, w_tip, fill, outline, ow=2):
    """锥形风力叶片：根部(靠车头)宽、尖端(靠挂车尾)窄"""
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s], [s, c]])
    cs = np.array([[-L / 2, -w_tip / 2], [L / 2, -w_root / 2],
                   [L / 2, w_root / 2], [-L / 2, w_tip / 2]])
    pp = vpx(view, cs @ R.T + np.asarray(center, dtype=float))
    pts = [(float(x), float(y)) for x, y in pp]
    dr.polygon(pts, fill=fill, outline=outline, width=ow)

def draw_bolsters(dr, view, center, ang, tlen, span, col, ow=3):
    """挂车两端托架（横杆），跨度大于货物宽度"""
    c, s = np.cos(ang), np.sin(ang)
    sc = view[0]
    for along in (-tlen * 0.42, tlen * 0.42):
        cx = center[0] + along * c
        cy = center[1] + along * s
        p0 = vpx(view, [[cx + span / 2 * s, cy - span / 2 * c]])[0]
        p1 = vpx(view, [[cx - span / 2 * s, cy + span / 2 * c]])[0]
        dr.line([p0[0], p0[1], p1[0], p1[1]], fill=col, width=max(2, int(sc * 0.5)))

def draw_wheels(dr, view, center, ang, L, Wd, r=0.6, fill=(42, 44, 50)):
    c, s = np.cos(ang), np.sin(ang)
    sc = view[0]
    rr = max(2.5, r * sc)
    for sg in (-1, 1):
        for al in (-L * 0.38, L * 0.38):
            p = (center[0] + al * c - sg * Wd * 0.52 * s,
                 center[1] + al * s + sg * Wd * 0.52 * c)
            q = vpx(view, [p])[0]
            dr.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr],
                       fill=fill, outline=(22, 24, 28))

# ---------------- 状态（位姿模型统一在 leaf_common：车头 4m/s 沿青线，
# 挂接点→车尾距离 = COUPLE_L，车尾沿绿线滑动，配合车头按路线前进） ----------------
P1, P2, P3 = LC.P1, LC.P2, LC.P3
PHASES = LC.PHASES

def state(f):
    return LC.state(f)

# ---------------- 静态背景 ----------------
bg = Image.new('RGB', (W, H), (247, 248, 251))
d = ImageDraw.Draw(bg)

for m in np.arange(np.ceil(xmin / 50) * 50, xmax, 50):
    p = vpx(MAIN, [[m, ymin]])[0]
    d.line([p[0], HEAD_H + MARGIN, p[0], PLOT_BOT], fill=(233, 235, 240), width=1)
    d.text((p[0] + 3, PLOT_BOT + 4), '%dm' % m, font=F11, fill=(168, 173, 183))
for m in np.arange(np.ceil(ymin / 50) * 50, ymax, 50):
    p = vpx(MAIN, [[xmin, m]])[0]
    d.line([MARGIN, p[1], W - MARGIN, p[1]], fill=(233, 235, 240), width=1)
    d.text((MARGIN - 42, p[1] - 6), '%dm' % m, font=F11, fill=(168, 173, 183))

d.line(list(vpx(MAIN, cab).ravel()), fill=(0, 162, 208), width=3)
d.line(list(vpx(MAIN, trl).ravel()), fill=(34, 172, 92), width=3)

# 航拍底图：铺在主图区域（覆盖网格线）
if LC.HAS_PHOTO:
    LC.paste_photo(bg, MAIN, clip=(MARGIN, HEAD_H + MARGIN, W - MARGIN, PLOT_BOT))
    d = ImageDraw.Draw(bg)
    for m in np.arange(np.ceil(ymin / 50) * 50, ymax, 50):
        p = vpx(MAIN, [[xmin, m]])[0]
        d.text((MARGIN - 42, p[1] - 6), '%dm' % m, font=F11, fill=(70, 78, 92))
    for m in np.arange(np.ceil(xmin / 50) * 50, xmax, 50):
        p = vpx(MAIN, [[m, ymin]])[0]
        d.text((p[0] + 3, PLOT_BOT + 4), '%dm' % m, font=F11, fill=(70, 78, 92))

# 图纸背景元素：道路边线 / 弧线（浅灰）+ 道路文字标注（镜像后文字位置与 CAD 一致）
LC.draw_drawing_elements(d, MAIN, show_roads=True, show_texts=True, text_font=12)

for pts, col, nm in ((cab, (0, 162, 208), '车头'), (trl, (34, 172, 92), '挂车')):
    for p, tag in ((pts[0], '起'), (pts[-1], '终')):
        q = vpx(MAIN, [p])[0]
        d.ellipse([q[0] - 6, q[1] - 6, q[0] + 6, q[1] + 6], fill=col, outline=(255, 255, 255))
        d.text((q[0] + 9, q[1] - 8), '%s%s' % (nm, tag), font=F11, fill=col)

# 图例：底部独立条带，横排一行，不遮挡任何轨迹
LEG_Y = H - FOOT_H - LEG_H
d.rectangle([0, LEG_Y, W, LEG_Y + LEG_H], fill=(240, 242, 246))
d.line([0, LEG_Y, W, LEG_Y], fill=(214, 218, 226), width=1)
lx, ly = MARGIN, LEG_Y + 12
items = [('line', (0, 162, 208), '车头轨迹（CAD 青线）'),
         ('line', (34, 172, 92), '挂车尾部轨迹（CAD 绿线）'),
         ('box', (234, 130, 44), '牵引车'),
         ('box', (132, 100, 210), '挂车梁'),
         ('box', (252, 198, 74), '叶片货物'),
         ('box', (245, 196, 26), '跟随皮卡（距尾部 40m）')]
for kind, col, txt in items:
    if kind == 'line':
        d.line([lx, ly + 6, lx + 22, ly + 6], fill=col, width=4)
    else:
        d.rectangle([lx, ly - 1, lx + 22, ly + 13], fill=col, outline=(70, 70, 70))
    d.text((lx + 29, ly - 2), txt, font=F12, fill=(52, 56, 64))
    lx += 32 + len(txt) * 12 + 26

# ---------------- 渲染 ----------------
os.makedirs(FRAMES_DIR, exist_ok=True)
print('渲染 %d 帧  画布 %dx%d  缩放 %.2f px/m' % (NFR, W, H, SCALE))

TEST_N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
LOOP, STEP = NFR, (max(1, NFR // TEST_N) if TEST_N else 1)

# 剪掉片头：前 ~2.5s（就位 + 装载）不需要，直接从满载行驶阶段开始
START_F = int(round(LC.P2 * (NFR - 1)))
print('片头裁剪 %d 帧（%.2fs）→ 成片 %.1f s' % (START_F, START_F / FPS, (LOOP - START_F) / FPS))
if not TEST_N:
    import shutil
    if os.path.isdir(FRAMES_DIR):
        shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)

INSET = 340
# 放大窗口聚焦"挂车尾部 ↔ 跟随皮卡"的跟车段（整列车队 93m 太长，全塞进去会失去放大意义）
ISH0 = min(SCALE * 1.9, INSET / (LC.SPAN_TAIL_MAX * 1.30))

for f in range(START_F, LOOP, STEP):
    st = state(f)
    ph, u = st['ph'], st['u']
    img = bg.copy()
    dr = ImageDraw.Draw(img)

    # 已走过轨迹高亮
    if st['ci'] > 0:
        dr.line(list(vpx(MAIN, cab[:st['ci'] + 1]).ravel()), fill=(0, 108, 144), width=4)
    if st['ti'] > 0:
        dr.line(list(vpx(MAIN, trl[:st['ti'] + 1]).ravel()), fill=(16, 118, 58), width=4)

    # 挂车梁
    draw_rect(dr, MAIN, st['trl_c'], st['tang'], st['tlen'], TRL_W,
              (132, 100, 210), (40, 24, 96), ow=2)
    draw_bolsters(dr, MAIN, st['trl_c'], st['tang'], st['tlen'], TRL_W * 1.55, (72, 48, 140))
    draw_wheels(dr, MAIN, st['tp'], st['tang'], 3.6, TRL_W, r=0.65)
    draw_wheels(dr, MAIN, st['hitch'], st['tang'], 0.8, TRL_W, r=0.5, fill=(60, 62, 70))

    # 叶片
    alpha = LC.blade_alpha(f, ph)
    if ph >= 1 and alpha > 0.02:
        fl = LC.blade_color(alpha)
        draw_blade(dr, MAIN, st['cargo_c'], st['tang'], BLADE_L, BLADE_ROOT, BLADE_TIP,
                   fl, (152, 106, 12), ow=2)
        # 把被货物盖住的挂车梁轮廓描回来，保证能看出挂车走向
        draw_outline(dr, MAIN, st['trl_c'], st['tang'], st['tlen'], TRL_W, (60, 34, 120), ow=2)

    # 牵引车
    draw_rect(dr, MAIN, st['cab_c'], st['ch'], CAB_L, CAB_W,
              (236, 132, 46), (72, 36, 0), ow=2, shadow=(213, 216, 223))
    draw_wheels(dr, MAIN, st['cab_c'], st['ch'], CAB_L, CAB_W, r=0.58)

    # 挂接点
    hp = vpx(MAIN, [st['hitch']])[0]
    dr.ellipse([hp[0] - 5, hp[1] - 5, hp[0] + 5, hp[1] + 5], fill=(214, 52, 52), outline=(255, 255, 255))

    # 跟随皮卡（黄色，同一青线，落后主车 ESCORT_GAP 米）
    LC.draw_pickup(dr, MAIN, st['pk'], math.radians(st['pk_deg']),
                   label='皮卡', label_font=F11)

    # ---------- 局部放大窗口 ----------
    ix, iy = W - MARGIN - INSET, PLOT_BOT - INSET - 8
    panel = Image.new('RGB', (INSET, INSET), (255, 255, 255))
    IVIEW = (ISH0, np.array([INSET / 2.0, INSET / 2.0]) - np.asarray(st['inset_tail_c']) * ISH0)
    if LC.HAS_PHOTO:
        LC.paste_photo(panel, IVIEW, clip=(0, 0, INSET, INSET))
    pdr = ImageDraw.Draw(panel)
    # 窗口内图纸背景（道路线 / 文字），让局部放大保留上下文体
    LC.draw_drawing_elements(pdr, IVIEW, show_roads=True, show_texts=True,
                             text_font=9, inset=(0, 0, INSET, INSET))
    # 窗口内轨迹：皮卡所在的青线段 + 尾部所在的绿线段
    a0, b0 = max(0, st['pk_ci'] - 45), min(len(cab), st['pk_ci'] + 46)
    pdr.line(list(vpx(IVIEW, cab[a0:b0]).ravel()), fill=(0, 162, 208), width=3)
    a1, b1 = max(0, st['ti'] - 45), min(len(trl), st['ti'] + 46)
    pdr.line(list(vpx(IVIEW, trl[a1:b1]).ravel()), fill=(34, 172, 92), width=3)
    draw_rect(pdr, IVIEW, st['trl_c'], st['tang'], st['tlen'], TRL_W,
              (132, 100, 210), (40, 24, 96), ow=3)
    draw_bolsters(pdr, IVIEW, st['trl_c'], st['tang'], st['tlen'], TRL_W * 1.55, (72, 48, 140))
    draw_wheels(pdr, IVIEW, st['tp'], st['tang'], 3.6, TRL_W, r=0.9)
    draw_wheels(pdr, IVIEW, st['hitch'], st['tang'], 0.8, TRL_W, r=0.7, fill=(60, 62, 70))
    if ph >= 1 and alpha > 0.02:
        fl = LC.blade_color(alpha)
        draw_blade(pdr, IVIEW, st['cargo_c'], st['tang'], BLADE_L, BLADE_ROOT, BLADE_TIP,
                   fl, (152, 106, 12), ow=3)
        draw_outline(pdr, IVIEW, st['trl_c'], st['tang'], st['tlen'], TRL_W, (60, 34, 120), ow=3)
    draw_rect(pdr, IVIEW, st['cab_c'], st['ch'], CAB_L, CAB_W,
              (236, 132, 46), (72, 36, 0), ow=3)
    draw_wheels(pdr, IVIEW, st['cab_c'], st['ch'], CAB_L, CAB_W, r=0.85)
    hq = vpx(IVIEW, [st['hitch']])[0]
    pdr.ellipse([hq[0] - 7, hq[1] - 7, hq[0] + 7, hq[1] + 7], fill=(214, 52, 52), outline=(255, 255, 255))
    # 放大窗口内也画跟随皮卡（超出视野时 PIL 自动裁掉）
    LC.draw_pickup(pdr, IVIEW, st['pk'], math.radians(st['pk_deg']))
    # 窗口边框 + 标注
    img.paste(panel, (ix, iy))
    dr.rectangle([ix, iy, ix + INSET - 1, iy + INSET - 1], outline=(150, 156, 168), width=2)
    dr.rectangle([ix + 8, iy + INSET - 26, ix + 152, iy + INSET - 6], fill=(255, 255, 255))
    dr.text((ix + 12, iy + INSET - 23), '局部放大 1.7×', font=F11, fill=(64, 68, 78))

    # ---------- 顶部两行 ----------
    dr.rectangle([0, 0, W, HEAD_H], fill=(24, 27, 33))
    dr.text((MARGIN - 4, 12), '叶片车行走轨迹模拟', font=F17, fill=(240, 244, 250))
    dr.text((MARGIN - 4, 34), '车头走青线 · 挂车尾走绿线 · 满载叶片运输',
            font=F11, fill=(138, 145, 158))
    dr.text((W - MARGIN - 206, 14), 't = %5.1f s' % ((f - START_F) / FPS), font=F15, fill=(226, 232, 240))
    dr.text((W - MARGIN - 206, 40), '进度 %3.0f%%' % (u * 100), font=F12, fill=(150, 200, 170))
    # 进度条
    pbx0, pby = MARGIN - 4, 68
    pbw = W - 2 * MARGIN - 320
    dr.rectangle([pbx0, pby, pbx0 + pbw, pby + 8], fill=(52, 57, 66))
    dr.rectangle([pbx0, pby, pbx0 + int(pbw * u), pby + 8], fill=(56, 168, 118))
    # 阶段标签（右侧）
    sx = W - MARGIN - 300
    for i, nm in enumerate(PHASES):
        col = (232, 255, 245) if i == ph else (124, 130, 142)
        if i == ph:
            dr.rectangle([sx - 6, 62, sx + 70, 82], fill=(38, 104, 84))
        dr.text((sx, 64), nm, font=F11, fill=col)
        sx += 76

    # ---------- 底部 ----------
    dr.rectangle([0, H - FOOT_H, W, H], fill=(238, 240, 245))
    # 挂车梁长是刚性定值，显示常量而非逐帧求解值
    info = ('牵引车 %.0fm · 挂车梁 %.1fm · 叶片 %.0fm · 车头 %.1fm/s · 车头轨迹 %.0fm · 挂车轨迹 %.0fm'
            % (CAB_L, LC.COUPLE_L, BLADE_L, LC.SPEED, CL, TL))
    dr.text((MARGIN - 4, H - FOOT_H + 13), info, font=F11, fill=(98, 104, 116))
    tag = ''
    if ph == 1:
        tag = '装载中 %d%%' % int(alpha * 100)
    elif ph == 3:
        tag = '抵达终点'
    elif ph == 0:
        tag = '空载行驶'
    else:
        tag = '满载运输'
    dr.text((W - MARGIN - 96, H - FOOT_H + 13), tag, font=F12, fill=(150, 105, 10))
    dr.text((W - MARGIN - 96, H - FOOT_H + 26), '', font=F11, fill=(150, 105, 10))

    img.save(os.path.join(FRAMES_DIR, 'f_%04d.png' % (f - START_F)))
    if f % 60 == 0:
        print('  frame %d / %d' % (f, NFR))

if TEST_N:
    print('抽样自检完成')
    raise SystemExit(0)

print('合成视频 ...')
subprocess.run([LC.FFMPEG, '-y', '-framerate', str(FPS),
                '-i', os.path.join(FRAMES_DIR, 'f_%04d.png'),
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18',
                '-movflags', '+faststart', OUT_MP4], check=True)
print('完成:', OUT_MP4)
