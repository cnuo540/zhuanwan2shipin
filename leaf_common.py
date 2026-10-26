# -*- coding: utf-8 -*-
"""
叶片车模拟 · 公共模块
- 读 _traj.json（由 extract_cad_traj.py 从 DXF 生成）
- 车辆几何 / 位姿求解 / 工程指标
- 与版式无关的绘图基元（支持任意视口）

供 leaf_truck_sim.py（竖版）与 leaf_truck_wide.py（横版）共用。
"""
import os, json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))


def _find_ffmpeg():
    """按优先级找 ffmpeg：环境变量 → PATH → 常见安装位置"""
    import shutil, glob
    env = os.environ.get('FFMPEG')
    if env and os.path.exists(env):
        return env
    which = shutil.which('ffmpeg')
    if which:
        return which
    pats = [
        os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin\ffmpeg.exe'),
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
    ]
    for pat in pats:
        hits = glob.glob(pat, recursive=True)
        if hits:
            return hits[0]
    return 'ffmpeg'          # 交给系统 PATH，找不到会在合成时报错


FFMPEG = _find_ffmpeg()

FPS, DUR = 30, 16
NFR = FPS * DUR

# ---- 车辆参数(米) ----
CAB_L, CAB_W = 8.0, 2.6
HITCH_OFF = 1.2
TRL_W = 3.6
BLADE_L = 108.0
BLADE_ROOT, BLADE_TIP = 2.8, 0.9

# ---- 动力学参数 ----
SPEED = 4.0                  # 车头沿青线行驶速度 m/s
COUPLE_L = 58.0             # 挂车梁长（刚性约束：挂接点→车尾 = 58 m，挂车尾部被车头牵引沿绿线前进）

# ---- 跟随皮卡（黄色，走在青色路线上，保持在挂车尾部后方 40 m） ----
ESCORT_L, ESCORT_W = 5.4, 2.05   # 皮卡外形尺寸(m)
ESCORT_GAP = 40.0                # 距挂车尾部（绿线端点）的沿路距离(m)

# ---- 颜色（车头=青色线, 挂车尾部=绿色线） ----
C_CAB_TRAJ = (0, 162, 208)      # 青色：车头（牵引车）轨迹
C_TRL_TRAJ = (34, 172, 92)      # 绿色：挂车尾部轨迹
C_CAB_TRAJ_DONE = (0, 108, 144)
C_TRL_TRAJ_DONE = (16, 118, 58)
C_CAB = (236, 132, 46)
C_CAB_EDGE = (72, 36, 0)
C_TRL = (132, 100, 210)
C_TRL_EDGE = (40, 24, 96)
C_BLADE = (252, 198, 74)
C_BLADE_EDGE = (152, 106, 12)
# 跟随皮卡：黄色车身（比叶片更深更饱和，避免和货物混色）
C_ESC = (245, 196, 26)
C_ESC_EDGE = (128, 96, 0)
C_ESC_GLASS = (206, 226, 240)
C_HITCH = (214, 52, 52)
C_DARK = (24, 27, 33)
# 图纸背景元素：道路边线 / 弧线（浅灰）、文字
C_ROAD = (168, 176, 188)
C_ROAD_TXT = (110, 118, 132)

# ACI 颜色号 → 渲染色（256=ByLayer，按图层 0 取浅灰）
def aci2rgb(n, default=(168, 176, 188)):
    m = {256: default, 7: default, 8: (205, 70, 60), 3: (34, 172, 92), 4: (0, 162, 208),
         5: (235, 205, 40), 1: (220, 80, 60), 2: (240, 150, 60), 6: (150, 60, 160)}
    return m.get(int(n), default)

# ---------------- 轨迹 ----------------
_TRAJ = os.path.join(BASE, '_traj.json')
if not os.path.exists(_TRAJ):
    raise SystemExit(
        '未找到 _traj.json。请先运行一次提取：\n'
        '    python -X utf8 make_videos.py --no-render\n'
        '或直接跑全流程：\n'
        '    python -X utf8 make_videos.py')
_raw = json.load(open(_TRAJ, encoding='utf-8'))
# CAD 单位为毫米 → 米
cab = np.array(_raw['cab'], dtype=float) / 1000.0
trl = np.array(_raw['trailer'], dtype=float) / 1000.0

# 图纸其他元素（extract_drawing.py 生成；旧 _traj.json 没有则跳过）
_lines = [((l[0][0] / 1000.0, l[0][1] / 1000.0),
           (l[1][0] / 1000.0, l[1][1] / 1000.0), l[2]) for l in _raw.get('lines', [])]
_arcs = [([ (p[0] / 1000.0, p[1] / 1000.0) for p in pts ], c)
         for pts, c in _raw.get('arcs', [])]
_texts = [(tx['x'] / 1000.0, tx['y'] / 1000.0, tx.get('color', 7),
           tx.get('segs', [tx.get('text', '')]) if False else tx.get('segs', [[None, tx.get('text', '')]]))
          for tx in _raw.get('texts', [])]

# ---- 航拍底图（extract_ole_image.py + photo_geo.json 生成；没有则跳过） ----
PHOTO_PNG = os.path.join(BASE, 'photo.png')
PHOTO_GEO = os.path.join(BASE, 'photo_geo.json')
_photo = None
_photo_geo = None
try:
    _photo = Image.open(PHOTO_PNG).convert('RGB')
    _photo_geo = json.load(open(PHOTO_GEO, encoding='utf-8'))
except Exception:
    _photo, _photo_geo = None, None
HAS_PHOTO = _photo is not None and _photo_geo is not None

# 镜像开关（关键）：
#   渲染器 screen_y = world_y * scale + org（y 向下），而 CAD 的 +y 是北方（向上）。
#   因此必须令 world_y = -raw_y（MIRROR_Y=True），两者相抵后画面才与 CAD 的朝向一致
#   （北在上、东在右、左转仍是左转）。底图按同一变换处理 → 航拍图也正立。
#   曾误设为 "有底图时 False"，导致轨迹与底图上下颠倒、左右转反了。
MIRROR_Y = True
if MIRROR_Y:
    cab[:, 1] = -cab[:, 1]
    trl[:, 1] = -trl[:, 1]
    _lines = [((a[0], -a[1]), (b[0], -b[1]), c) for a, b, c in _lines]
    _arcs = [([(p[0], -p[1]) for p in pts], c) for pts, c in _arcs]

    _texts = [(x, -y, col, segs) for x, y, col, segs in _texts]
    # photo_geo.json 存的是 CAD 原始坐标（y0 = 图像南边缘），这里同步镜像
    if _photo_geo is not None:
        _photo_geo = dict(_photo_geo)
        _photo_geo['y0'] = -(_photo_geo['y0'] + _photo_geo['h'])

# 镜像后 geo['y0'] 指向图像「北」边缘（世界 y 最小）→ 屏幕上方即照片上边缘，无需翻转。
# 若 MIRROR_Y 被关掉，geo['y0'] 回到南边缘，则需垂直翻转。
PHOTO_TOP_IS_NORTH = bool(MIRROR_Y)

def arc(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])

CS, TS = arc(cab), arc(trl)
CL, TL = float(CS[-1]), float(TS[-1])

def sample(pts, s, s_total, u):
    """按归一化进度 u 取点 / 切线方向 / 最近点索引"""
    fl = float(np.interp(u * s_total, s, np.arange(len(pts))))
    i0 = int(np.clip(fl, 0, len(pts) - 1))
    i1 = min(i0 + 1, len(pts) - 1)
    t = fl - i0
    p = (1 - t) * pts[i0] + t * pts[i1]
    a, b = max(0, i0 - 5), min(len(pts) - 1, i1 + 5)
    ang = float(np.arctan2(pts[b][1] - pts[a][1], pts[b][0] - pts[a][0]))
    return p, ang, i0

# ---------------- 时间轴（车头 4 m/s 恒定沿青线行驶） ----------------
T_DRIVEN = CL / SPEED          # 行驶完青线所需时间
P1, P2, P3 = 0.0, 0.16, 0.96
PARK_U = 0.2167                # 装货位：车头在青线上的位置（挂接点→绿线起点 = 49.9 m）
PHASES = ['① 空车就位', '② 装载叶片', '③ 满载行驶', '④ 到达卸货']
# 转弯轨迹（车头/挂车线已互换，车头=ACI4 421点 204.5m）：
#   ①② 空车就位 + 装载叶片：车头缓入到 33%（u=0.33，挂接点→绿线起点 ≈ 49.6m ≈ 梁长，
#      挂车尾部挂在绿线起点，50m 刚性成立）
#   ③ 满载行驶：车头 33%→100% 牵引挂车沿绿线前进（含转弯段）
#   ④ 到达卸货：车头到终点卸货
# 画面上下镜像由 MIRROR_Y 完成（世界 y 取反），故此处进度逻辑无需改。

def cab_progress(t):
    """车头沿青线的位置：从 0% 缓入到 PARK_U（装货位），满载后匀速走完到 100%"""
    if t < P2:
        return PARK_U * (t / P2)          # ① 缓入到装货位
    if t < P3:
        a = (t - P2) / (P3 - P2)
        return PARK_U + (1.0 - PARK_U) * a * a * (3 - 2 * a)   # ③ 满载行驶
    return 1.0

def blade_alpha(f, ph):
    """叶片可见度。①装载阶段由 0 渐显到 1；此后全程满载，不再淡出
    （早期 ④ 阶段做了卸货淡出，导致视频最后 1 秒货物消失）。"""
    if ph == 1:
        return float(np.clip((f / (NFR - 1)) / P2, 0, 1))
    return 1.0

def blade_color(a):
    return (int(C_BLADE[0] * a + 247 * (1 - a)),
            int(C_BLADE[1] * a + 248 * (1 - a)),
            int(C_BLADE[2] * a + 251 * (1 - a)))

# ---------------- 挂车尾部：绿线上、车头-车尾距离恒定的约束求解 ----------------
# 物理模型：
#   - 车头沿青线行驶（SPEED m/s），车头中心→挂接点距离 = CAB_L/2-1+HITCH_OFF（常数）
#   - 挂车尾部始终位于绿线上，且 |挂接点 - 车尾| = COUPLE_L（常数）
#   - 挂车尾索引单调不减（沿绿线向前滑动）
# 若 COUPLE_L 在当前几何下不可达，车尾保持静止等待（见 solve_tail_positions 注释）。

def seg_roots(h, kk):
    """挂接点 h 到绿线段 kk 的三次样条，求 |h-P(x)|=L 的根 x∈[0,1]（数值）"""
    Nt = len(trl)
    L = COUPLE_L
    c0 = trl[max(0, kk - 1)]
    c1 = trl[kk]
    c2 = trl[min(Nt - 1, kk + 1)]
    c3 = trl[min(Nt - 1, kk + 2)]
    A = 0.5 * (c3 - c0 - 3.0 * c1 + 3.0 * c2)
    B = 1.5 * (c1 - c2)
    Cv = 0.5 * (c2 - c0)
    e = c1 - h
    # g(x)=|A x³+B x²+C x+e|²-L² 是 6 次多项式，系数：
    aa = float(A @ A)
    ab = float(A @ B)
    ac = float(A @ Cv)
    ae = float(A @ e)
    bb = float(B @ B)
    bc = float(B @ Cv)
    be = float(B @ e)
    cc = float(Cv @ Cv)
    ce = float(Cv @ e)
    ee = float(e @ e)
    coef = np.array([
        aa,
        2.0 * ab,
        2.0 * ac + bb,
        2.0 * ae + 2.0 * bc,
        2.0 * be + cc,
        2.0 * ce,
        ee - L * L,
    ])
    roots = np.roots(coef)
    out = []
    for r in roots:
        if abs(r.imag) < 1e-7 and 0.0 <= r.real <= 1.0:
            out.append(float(r.real))
    return sorted(out)

def _seg_spline(kk):
    """绿线点列的线性段 P(x)=c1+x*(c2-c1)（_traj.json 已含 Catmull-Rom 插值点，
    相邻点距离 ~0.46m，线性化误差 <1%）"""
    c1 = trl[min(kk, len(trl) - 1)]
    c2 = trl[min(len(trl) - 1, kk + 1)]
    return 0.0, np.zeros(2), c2 - c1, c1

def _dist2_to_seg(h, kk, x):
    A, B, Cv, Dv = _seg_spline(kk)
    P = A * x ** 3 + B * x ** 2 + Cv * x + Dv
    return float((h - P) @ (h - P))

def _closest_x(h, kk, x0):
    """在 [0,1] 上数值求解使 |h-P(x)|² 最接近 L² 的 x（牛顿+二分）"""
    L2 = COUPLE_L * COUPLE_L
    best_x, best_d = x0, abs(_dist2_to_seg(h, kk, x0) - L2)
    # 扫描
    for i in range(51):
        x = i / 50.0
        d = abs(_dist2_to_seg(h, kk, x) - L2)
        if d < best_d:
            best_d, best_x = d, x
    if best_d < 0.5:
        return best_x
    # 二分细化 best_x 附近
    lo = max(0.0, best_x - 0.02)
    hi = min(1.0, best_x + 0.02)
    for _ in range(40):
        m = (lo + hi) / 2.0
        if abs(_dist2_to_seg(h, kk, m) - L2) < abs(_dist2_to_seg(h, kk, hi) - L2):
            hi = m
        else:
            lo = m
    return (lo + hi) / 2.0

def _hitch_at(k):
    """绿线点列的线性段 P(x)=c1+x*(c2-c1)（_traj.json 已含 Catmull-Rom 插值点，
    相邻点距离 ~0.46m，线性化误差 <1%）对应的挂接点计算"""
    cpk = cab[k]
    Nc = len(cab)
    ank = math.atan2(cab[min(Nc - 1, k + 5)][1] - cab[max(0, k - 5)][1],
                     cab[min(Nc - 1, k + 5)][0] - cab[max(0, k - 5)][0])
    fwd = np.array([math.cos(ank), math.sin(ank)])
    return cpk - fwd * (CAB_L * 0.5 - 1.0) + fwd * HITCH_OFF

def _auto_park_u():
    """自动求装货位：使「挂接点→绿线起点」最接近梁长的车头位置（图纸更新后无需手改）"""
    Nc = len(cab)
    k_best, err_best = 0, 1e18
    for k in range(Nc):
        d = float(np.linalg.norm(_hitch_at(k) - trl[0]))
        e = abs(d - COUPLE_L)
        if e < err_best:
            err_best, k_best = e, k
    return k_best / float(Nc - 1), k_best, err_best

PARK_U, PARK_K, PARK_ERR = _auto_park_u()

def solve_tail_positions(window=120, max_step=4.0):
    """刚性挂车梁长：|挂接点 - 车尾| = COUPLE_L，车尾在绿线上，车头牵引下连续前进

    物理模型（车头牵引挂车，刚性梁长，车尾从绿线起点开始）：
      1. 车头从青线 25.3% 装货位起步（挂接点→绿线起点 = 50.3m ≈ 梁长），
         挂车尾部挂在绿线起点，50m 刚性成立
      2. 每帧在 prev_pos 附近 ±window 个绿线段内找所有 COUPLE_L 交点，
         取"前方且离当前位置最近"的把车尾拉过去（牵引语义）
      3. 限幅 max_step 个绿线点/帧（平滑防跳变）
      4. 若 50m 交点全在后方或窗口外：保持原位，梁长暂时拉伸
    返回 (idx, frac)：idx[k]=绿线线段索引，frac[k]=线段内分数位置
    """
    Nc = len(cab)
    Nt = len(trl)
    L = COUPLE_L

    # 装货位由 _auto_park_u() 自动求得（挂接点→绿线起点 ≈ 梁长），车尾从绿线起点开始
    # 车头到达装货位之前（①②），挂车尾部停在绿线起点不动，避免过早锁定到远端分支
    k_park = PARK_K
    prev_pos = 0.0
    idx = [int(min(prev_pos, Nt - 1))]
    frac = [max(0.0, prev_pos - int(min(prev_pos, Nt - 1)))]

    for k in range(1, Nc):
        if k < k_park:
            # 装货位之前：车尾保持不动
            idx.append(int(min(prev_pos, Nt - 1)))
            frac.append(max(0.0, prev_pos - int(min(prev_pos, Nt - 1))))
            continue
        hk = _hitch_at(k)
        # 在 prev_pos 附近 ±window 个绿线段内找所有 COUPLE_L 交点
        lo = max(0, int(math.floor(prev_pos)) - window)
        hi = min(Nt - 1, int(math.floor(prev_pos)) + window)
        cand = []
        for kk in range(lo, hi + 1):
            for x in seg_roots(hk, kk):
                cand.append(kk + x)
        if cand:
            # 取"前方且离当前位置最近"的交点（牵引语义：挂车只能往前被拖，不能后退）
            ahead = [c for c in cand if c >= prev_pos - 1e-9]
            if ahead:
                best = min(ahead, key=lambda c: abs(c - prev_pos))   # 前方最近
            else:
                # 前方无交点（50m 圆在装货位前够不到绿线）：暂不移动，
                # 等车头走到装货位后 50m 交点出现再牵引
                best = prev_pos
            # 限幅：单帧最多前进 max_step 个绿线点
            if best - prev_pos > max_step:
                best = prev_pos + max_step
            prev_pos = best
        # else: 窗口内无交点 → 保持原位（梁长暂时拉伸）
        idx.append(int(min(prev_pos, Nt - 1)))
        frac.append(max(0.0, prev_pos - int(min(prev_pos, Nt - 1))))
    return np.array(idx, dtype=int), np.array(frac, dtype=float)

_TAIL_IDX, _TAIL_FRAC = solve_tail_positions()
TAIL_IDX_MAX = int(_TAIL_IDX.max())

def arc_of_closest(pts, s, p):
    """点 p 在折线 pts 上的最近点对应的弧长（线段垂足投影，输出平滑无抖动）"""
    p = np.asarray(p, dtype=float)
    d2 = np.einsum('ij,ij->i', pts - p, pts - p)
    i = int(np.argmin(d2))
    best_s, best_d2 = float(s[i]), float(d2[i])
    for a, b in ((max(0, i - 1), i), (i, min(len(pts) - 1, i + 1))):
        if a == b:
            continue
        seg = pts[b] - pts[a]
        L2 = float(seg @ seg)
        if L2 <= 1e-12:
            continue
        t = float(np.clip((p - pts[a]) @ seg / L2, 0.0, 1.0))
        foot = pts[a] + t * seg
        dd = float((p - foot) @ (p - foot))
        if dd < best_d2:
            best_d2 = dd
            best_s = float(s[a] + t * (s[b] - s[a]))
    return best_s


def state(f):
    """求解该帧的车辆位姿与工程指标"""
    t_norm = f / (NFR - 1)
    u = cab_progress(t_norm)
    ph = int(np.searchsorted([P1, P2, P3, 1.0001], t_norm))
    cp, ch, ci = sample(cab, CS, CL, u)

    fwd = np.array([math.cos(ch), math.sin(ch)])
    rear = cp - fwd * (CAB_L * 0.5 - 1.0)
    hitch = rear + fwd * HITCH_OFF

    # 挂车尾部：绿线上、与挂接点距离 = COUPLE_L
    ti = int(_TAIL_IDX[ci])
    x = float(_TAIL_FRAC[ci])
    p_a, p_b = trl[ti], trl[min(ti + 1, len(trl) - 1)]
    p_t = (1.0 - x) * p_a + x * p_b

    vec = hitch - p_t
    tlen = float(np.linalg.norm(vec))
    tang = float(math.atan2(vec[1], vec[0])) if tlen > 0.3 else ch

    tdir = np.array([math.cos(tang), math.sin(tang)])
    cargo_c = hitch - tdir * (BLADE_L / 2.0 - 2.0)

    fold = (tang - ch + math.pi) % (2.0 * math.pi) - math.pi

    # 跟随皮卡：走在青色路线上，位置 = 挂车尾部投影到青线的弧长 − 30 m
    # 若青线前段不够长（弧长为负），沿起点切线向后外推，保证始终是"尾部后方 30 m"
    s_tail_on_cab = arc_of_closest(cab, CS, p_t)
    s_esc = s_tail_on_cab - ESCORT_GAP
    # 不允许超过主车车尾（避免与牵引车重叠）
    s_esc = min(s_esc, u * CL - CAB_L * 0.5 - 3.0)
    if s_esc >= 0.0:
        pk_p, pk_ch, pk_ci = sample(cab, CS, CL, s_esc / CL)
    else:
        # 起点外推：沿起点前进方向的反方向延伸
        t0 = cab[1] - cab[0]
        t0 = t0 / max(1e-9, float(np.linalg.norm(t0)))
        pk_p = np.asarray(cab[0], dtype=float) + t0 * s_esc
        pk_ch = float(math.atan2(t0[1], t0[0]))
        pk_ci = 0

    return dict(cp=cp, ch=ch, ci=ci, tp=p_t, ti=ti, hitch=hitch,
                cab_c=cp, tang=tang, tlen=tlen, trl_c=(hitch + p_t) / 2.0,
                cargo_c=cargo_c, u=u, ph=ph, fold_deg=float(math.degrees(fold)),
                cab_deg=float(math.degrees(ch)), trl_deg=float(math.degrees(tang)),
                dist=u * CL, tail_arc=TS[ti],
                pk=pk_p, pk_deg=float(math.degrees(pk_ch)), pk_ci=pk_ci,
                pk_dist=s_esc, gap=u * CL - s_esc,
                pk_tail=float(np.linalg.norm(pk_p - p_t)),
                tail_on_cab=s_tail_on_cab,
                span=float(np.linalg.norm(np.asarray(cp) - np.asarray(pk_p))),
                span_tail=float(np.linalg.norm(np.asarray(p_t) - np.asarray(pk_p))),
                span_truck=float(np.linalg.norm(np.asarray(cp) - np.asarray(p_t))),
                inset_truck_c=(np.asarray(cp) + np.asarray(p_t)) / 2.0,
                inset_c=(np.asarray(cp) + np.asarray(pk_p)) / 2.0,
                inset_tail_c=(np.asarray(p_t) + np.asarray(pk_p)) / 2.0)

# 全程统计（只统计成片实际用到的区间：片头 ①② 已剪掉）
STAT_F0 = int(round(P2 * (NFR - 1)))
_ALL = [state(f) for f in range(STAT_F0, NFR, 2)]
FOLD_MAX = max(abs(s['fold_deg']) for s in _ALL)
TLEN_MIN = min(s['tlen'] for s in _ALL)
TLEN_MAX = max(s['tlen'] for s in _ALL)
TAIL_LEN_TARGET = COUPLE_L
SPAN_MAX = max(s['span'] for s in _ALL)      # 车头↔皮卡 最大间距（放大窗口取景用）
SPAN_TAIL_MAX = max(s['span_tail'] for s in _ALL)   # 尾部↔皮卡 最大间距
SPAN_TRUCK_MAX = max(s['span_truck'] for s in _ALL)  # 车头↔尾部（车辆自身）最大间距

# ---------------- 视口 / 绘图 ----------------
def make_view(scale, size, world_center, origin_px=(0, 0)):
    """返回 (scale, org)，org 使 world_center 落在 origin_px + size/2"""
    org = np.array(origin_px, dtype=float) + np.array(size, dtype=float) / 2.0 \
          - np.asarray(world_center, dtype=float) * scale
    return (float(scale), org)

def vpx(view, p):
    sc, org = view
    p = np.atleast_2d(np.asarray(p, dtype=float))
    return p * sc + org

_font_cache = {}

def font(sz, bold=False):
    key = (sz, bold)
    if key in _font_cache:
        return _font_cache[key]
    names = ("msyhbd.ttc", "msyh.ttc", "simhei.ttf") if bold else ("msyh.ttc", "simhei.ttf", "arial.ttf")
    for n in names:
        pth = os.path.join(r'C:\Windows\Fonts', n)
        if os.path.exists(pth):
            try:
                _font_cache[key] = ImageFont.truetype(pth, sz)
                return _font_cache[key]
            except Exception:
                pass
    _font_cache[key] = ImageFont.load_default()
    return _font_cache[key]

def rot_rect(center, ang, L, Wd):
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s], [s, c]])
    cs = np.array([[-L / 2, -Wd / 2], [L / 2, -Wd / 2], [L / 2, Wd / 2], [-L / 2, Wd / 2]])
    return cs @ R.T + np.asarray(center, dtype=float)

def draw_rect(dr, view, center, ang, L, Wd, fill, outline, ow=2, shadow=None):
    pp = vpx(view, rot_rect(center, ang, L, Wd))
    # Pillow 10.4 的 polygon 不接受 numpy 数组（静默不绘制），必须转成 list[tuple]
    pts = [(float(x), float(y)) for x, y in pp]
    if shadow:
        dr.polygon([(x + 5.0, y + 7.0) for x, y in pts], fill=shadow)
    dr.polygon(pts, fill=fill, outline=outline, width=ow)

def draw_outline(dr, view, center, ang, L, Wd, outline, ow=3):
    pp = vpx(view, rot_rect(center, ang, L, Wd))
    pts = [(float(x), float(y)) for x, y in pp] + [(float(pp[0][0]), float(pp[0][1]))]
    dr.line(pts, fill=outline, width=ow, joint='curve')

def draw_blade(dr, view, center, ang, L, w_root, w_tip, fill, outline, ow=2):
    c, s = np.cos(ang), np.sin(ang)
    R = np.array([[c, -s], [s, c]])
    cs = np.array([[-L / 2, -w_tip / 2], [L / 2, -w_root / 2],
                   [L / 2, w_root / 2], [-L / 2, w_tip / 2]])
    pp = vpx(view, cs @ R.T + np.asarray(center, dtype=float))
    dr.polygon([(float(x), float(y)) for x, y in pp], fill=fill, outline=outline, width=ow)

def draw_bolsters(dr, view, center, ang, tlen, span, col):
    c, s = np.cos(ang), np.sin(ang)
    w = max(2, int(view[0] * 0.5))
    for along in (-tlen * 0.42, tlen * 0.42):
        cx = center[0] + along * c
        cy = center[1] + along * s
        p0 = vpx(view, [[cx + span / 2 * s, cy - span / 2 * c]])[0]
        p1 = vpx(view, [[cx - span / 2 * s, cy + span / 2 * c]])[0]
        dr.line([p0[0], p0[1], p1[0], p1[1]], fill=col, width=w)

def draw_wheels(dr, view, center, ang, L, Wd, r=0.6, fill=(42, 44, 50)):
    c, s = np.cos(ang), np.sin(ang)
    rr = max(2.5, r * view[0])
    for sg in (-1, 1):
        for al in (-L * 0.38, L * 0.38):
            p = (center[0] + al * c - sg * Wd * 0.52 * s,
                 center[1] + al * s + sg * Wd * 0.52 * c)
            q = vpx(view, [p])[0]
            dr.ellipse([q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr],
                       fill=fill, outline=(22, 24, 28))

def draw_vehicle(dr, view, st, alpha, show_blade=True):
    """按状态绘制整套车辆：挂车梁 + 托架 + 轮组 + 叶片 + 牵引车 + 挂接点"""
    draw_rect(dr, view, st['trl_c'], st['tang'], st['tlen'], TRL_W, C_TRL, C_TRL_EDGE, ow=2)
    draw_bolsters(dr, view, st['trl_c'], st['tang'], st['tlen'], TRL_W * 1.55, (72, 48, 140))
    draw_wheels(dr, view, st['tp'], st['tang'], 3.6, TRL_W, r=0.65)
    draw_wheels(dr, view, st['hitch'], st['tang'], 0.8, TRL_W, r=0.5, fill=(60, 62, 70))
    if show_blade and st['ph'] >= 1 and alpha > 0.02:
        draw_blade(dr, view, st['cargo_c'], st['tang'], BLADE_L, BLADE_ROOT, BLADE_TIP,
                   blade_color(alpha), C_BLADE_EDGE, ow=2)
        draw_outline(dr, view, st['trl_c'], st['tang'], st['tlen'], TRL_W, (60, 34, 120), ow=2)
    draw_rect(dr, view, st['cab_c'], st['ch'], CAB_L, CAB_W, C_CAB, C_CAB_EDGE, ow=2,
              shadow=(213, 216, 223))
    draw_wheels(dr, view, st['cab_c'], st['ch'], CAB_L, CAB_W, r=0.58)

def paste_photo(img, view, clip=None):
    """把航拍底图按地理配准贴到 img 上（在 clip 像素区域内裁剪）。

    photo_geo.json（经 MIRROR_Y 变换后）给出：x0 左边缘、y0 下边缘（世界坐标）、w/h。
    渲染器 screen_y = world_y*sc + org（y 向下）：
      · 世界 y 越大 → 屏幕越靠下
      · 图像 row 0（照片上边缘）对应世界的哪一端，取决于 MIRROR_Y，
        由 _photo_north_is_low() 判定
    """
    if not HAS_PHOTO:
        return
    sc, org = view
    gx0, gy0 = float(_photo_geo['x0']), float(_photo_geo['y0'])
    gw, gh = float(_photo_geo['w']), float(_photo_geo['h'])
    Wp, Hp = _photo.size

    sx0 = gx0 * sc + org[0]
    sx1 = (gx0 + gw) * sc + org[0]
    sy_lo = gy0 * sc + org[1]             # world y=y0 → 屏幕 y 较小
    sy_hi = (gy0 + gh) * sc + org[1]      # world y=y0+h → 屏幕 y 较大
    if sx1 - sx0 < 1 or sy_hi - sy_lo < 1:
        return

    cx0, cy0, cx1, cy1 = clip if clip else (0, 0, img.width, img.height)
    vx0, vy0 = max(sx0, cx0), max(sy_lo, cy0)
    vx1, vy1 = min(sx1, cx1), min(sy_hi, cy1)
    if vx1 - vx0 < 1 or vy1 - vy0 < 1:
        return

    u0, u1 = (vx0 - sx0) / (sx1 - sx0), (vx1 - sx0) / (sx1 - sx0)
    v0, v1 = (vy0 - sy_lo) / (sy_hi - sy_lo), (vy1 - sy_lo) / (sy_hi - sy_lo)
    if PHOTO_TOP_IS_NORTH:
        # 屏幕上方 = 世界 y 小 = 照片北侧 = 图像 row 0 → 不翻转
        ya, yb = v0, v1
    else:
        # 屏幕上方 = 照片南侧 = 图像 row H → 垂直翻转
        ya, yb = 1.0 - v1, 1.0 - v0
    src = (int(u0 * Wp), int(ya * Hp), int(u1 * Wp), int(yb * Hp))
    if src[2] - src[0] < 1 or src[3] - src[1] < 1:
        return
    crop = _photo.crop(src)
    dest = crop.resize((max(1, int(vx1 - vx0)), max(1, int(vy1 - vy0))), Image.BILINEAR)
    img.paste(dest, (int(vx0), int(vy0)))


def draw_hitch(dr, view, p, r=5, color=C_HITCH):
    q = vpx(view, [p])[0]
    dr.ellipse([q[0] - r, q[1] - r, q[0] + r, q[1] + r], fill=color, outline=(255, 255, 255))

def draw_pickup(dr, view, p, ang, label=None, label_font=None):
    """黄色跟随皮卡：车身 + 驾驶室玻璃 + 货箱 + 四轮（世界尺度，随视口缩放）"""
    sc = view[0]
    c, s = math.cos(ang), math.sin(ang)

    def rr(along, across, L, Wd):
        """以车体为轴的矩形四角（along=纵向偏移, across=横向偏移）"""
        pts = []
        for dl, dw in ((-L / 2, -Wd / 2), (L / 2, -Wd / 2), (L / 2, Wd / 2), (-L / 2, Wd / 2)):
            x = along + dl
            y = across + dw
            pts.append((x * c - y * s + p[0], x * s + y * c + p[1]))
        return [(float(q[0]), float(q[1])) for q in vpx(view, pts)]

    # 车轮（先画，压在车身下）
    wheel_r = max(1.6, 0.38 * sc)
    for al in (ESCORT_L * 0.30, -ESCORT_L * 0.30):
        for sg in (-1, 1):
            wp = (p[0] + al * c - sg * ESCORT_W * 0.5 * s,
                  p[1] + al * s + sg * ESCORT_W * 0.5 * c)
            q = vpx(view, [wp])[0]
            dr.ellipse([q[0] - wheel_r, q[1] - wheel_r, q[0] + wheel_r, q[1] + wheel_r],
                       fill=(46, 48, 54), outline=(26, 28, 32))

    # 车身
    dr.polygon(rr(0, 0, ESCORT_L, ESCORT_W), fill=C_ESC, outline=C_ESC_EDGE,
               width=2 if sc > 3 else 1)
    # 驾驶室（车头方向前 40%）+ 玻璃
    dr.polygon(rr(ESCORT_L * 0.18, 0, ESCORT_L * 0.34, ESCORT_W * 0.96),
               fill=(252, 224, 120), outline=C_ESC_EDGE, width=1)
    if sc > 2.2:
        dr.polygon(rr(ESCORT_L * 0.26, 0, ESCORT_L * 0.14, ESCORT_W * 0.72),
                   fill=C_ESC_GLASS, outline=C_ESC_EDGE, width=1)
    # 货箱边栏
    if sc > 2.2:
        dr.polygon(rr(-ESCORT_L * 0.26, 0, ESCORT_L * 0.34, ESCORT_W * 0.80),
                   outline=(150, 112, 0), width=1)
    # 车头前灯
    if sc > 3.5:
        for sg in (-1, 1):
            lx = ESCORT_L * 0.48
            ly = sg * ESCORT_W * 0.30
            q = vpx(view, [(p[0] + lx * c - ly * s, p[1] + lx * s + ly * c)])[0]
            dr.ellipse([q[0] - 1.8, q[1] - 1.8, q[0] + 1.8, q[1] + 1.8], fill=(255, 246, 190))

    if label:
        q = vpx(view, [p])[0]
        dr.text((q[0] + 7, q[1] - 16), label, font=label_font or font(10),
                fill=(150, 112, 0))


def draw_drawing_elements(dr, view, show_roads=True, show_texts=True,
                          text_font=12, text_pad=6, inset=None):
    """绘制图纸背景元素：道路边线 / 弧线（浅灰）+ 道路文字（镜像后方向正确）
    与车辆渲染同坐标系统（world→screen），按 view 缩放平移。
    inset=(x0,y0,x1,y1) 像素区（放大视图用）：只画落在该区内的文字。"""
    if show_roads:
        for a, b, c in _lines:
            col = aci2rgb(c, C_ROAD)
            pa, pb = vpx(view, [a, b])
            dr.line([pa[0], pa[1], pb[0], pb[1]], fill=col, width=2)
        for pts, c in _arcs:
            col = aci2rgb(c, C_ROAD)
            pv = vpx(view, np.array(pts, dtype=float))
            # 注意：pv 是 (N,2)，必须转成 [(x,y), ...] 逐点折线；
            # 用 np.column_stack(pv) 会得到 (2,N)，坐标串位成锯齿状。
            dr.line([(float(p[0]), float(p[1])) for p in pv], fill=col, width=2)
    if show_texts:
        f = font(text_font)
        for x, y, col, segs in _texts:
            s = ''.join(txt for _cc, txt in segs)
            if not s:
                continue
            px, py = vpx(view, [(x, y)])[0]
            if inset is not None:
                x0, y0, x1, y1 = inset
                if not (x0 <= px <= x1 and y0 <= py <= y1 + 10):
                    continue
            tw = int(dr.textlength(s, font=f)) if hasattr(dr, 'textlength') else len(s) * 7
            dr.text((px - tw // 2, py - text_pad), s, font=f, fill=C_ROAD_TXT)

def draw_angle_gauge(dr, cx, cy, r, ang_deg, max_deg=90.0, safe_deg=30.0):
    """车挂夹角半圆仪表盘：左负右正，绿色安全区 ±safe_deg"""
    import math
    # 底色半圆
    dr.arc([cx - r, cy - r, cx + r, cy + r], start=180, end=360, fill=(58, 64, 74), width=10)
    # 安全区（左右各一段）
    span = 180.0 * (safe_deg / max_deg)
    dr.arc([cx - r, cy - r, cx + r, cy + r], start=270 - span / 2, end=270 + span / 2,
           fill=(60, 150, 105), width=10)
    # 刻度
    for t in (-90, -60, -30, 0, 30, 60, 90):
        if abs(t) > max_deg:
            continue
        a = math.radians(270 + t * (90.0 / max_deg))
        x0 = cx + (r - 12) * math.cos(a)
        y0 = cy + (r - 12) * math.sin(a)
        x1 = cx + (r - 1) * math.cos(a)
        y1 = cy + (r - 1) * math.sin(a)
        dr.line([x0, y0, x1, y1], fill=(120, 126, 138), width=1)
    # 指针
    a = math.radians(270 + max(-max_deg, min(max_deg, ang_deg)) * (90.0 / max_deg))
    ex = cx + (r - 8) * math.cos(a)
    ey = cy + (r - 8) * math.sin(a)
    col = (230, 90, 70) if abs(ang_deg) > safe_deg else (90, 210, 150)
    dr.line([cx, cy, ex, ey], fill=col, width=4)
    dr.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=col, outline=(255, 255, 255))
    # 数值
    f24 = font(24, True)
    dr.text((cx - 38, cy + 12), '%+.0f°' % ang_deg, font=f24, fill=(232, 238, 246))


def draw_metric_rows(dr, bx, by, bw, rows, spacing=30):
    """rows: [(标签, 值文本, 0~1 比例)]，返回下一行 y"""
    f11, f12 = font(11), font(12)
    y = by
    for label, val, frac in rows:
        dr.text((bx, y), label, font=f11, fill=(126, 132, 144))
        vw = dr.textlength(val, font=f12)
        dr.text((bx + bw - vw, y), val, font=f12, fill=(226, 232, 240))
        dr.rectangle([bx, y + 15, bx + bw, y + 20], fill=(52, 57, 66))
        w = int(bw * float(np.clip(frac, 0, 1)))
        if w > 0:
            dr.rectangle([bx, y + 15, bx + w, y + 20], fill=(72, 150, 210))
        y += spacing
    return y
