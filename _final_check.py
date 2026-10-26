# -*- coding: utf-8 -*-
"""物理模型验收：只统计成片实际用到的区间（片头 ①② 已剪掉）"""
import leaf_common as L, numpy as np

F0, F1 = L.STAT_F0, L.NFR
ST = [L.state(f) for f in range(F0, F1)]

tail_arc = np.array([s['tail_arc'] for s in ST])          # 车尾沿绿线弧长(m)
dt = np.diff(tail_arc)
tl = np.array([s['tlen'] for s in ST])
fold = np.array([abs(s['fold_deg']) for s in ST])
pk = np.array([s['pk_tail'] for s in ST])

print('=== 物理模型验收（成片 %.2f s，车头青线 %.1f m @%.0f m/s，挂车绿线 %.1f m） ==='
      % ((F1 - F0) / L.FPS, L.CL, L.SPEED, L.TL))
print('车尾单调前进      : %s   最大单帧 %.2f m' % (bool(np.all(dt >= -1e-9)), dt.max()))
print('车尾行程          : %.1f → %.1f / %.1f m' % (tail_arc[0], tail_arc[-1], L.TL))
print('挂车梁长          : %.1f ~ %.1f m，中位 %.1f m（目标 %.0f m）'
      % (tl.min(), tl.max(), np.median(tl), L.COUPLE_L))
print('  偏离 >5m 的帧   : %d / %d' % (int((np.abs(tl - L.COUPLE_L) > 5).sum()), len(tl)))
print('车挂夹角峰值      : %.1f°' % fold.max())
print('皮卡距尾部        : %.1f ~ %.1f m（沿路目标 %.0f m）' % (pk.min(), pk.max(), L.ESCORT_GAP))
print('装货位            : 青线 %.2f%%（k=%d，挂接点→绿线起点误差 %.2f m）'
      % (L.PARK_U * 100, L.PARK_K, L.PARK_ERR))
