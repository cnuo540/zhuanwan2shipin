# -*- coding: utf-8 -*-
"""
叶片车转弯模拟 · 一键流水线

用法:
    python -X utf8 make_videos.py                # 提取 + 验收 + 渲染竖版/横版
    python -X utf8 make_videos.py --no-render    # 只提取 + 验收（约 30 秒）
    python -X utf8 make_videos.py --dxf "其他.dxf"
"""
import os, sys, subprocess, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DXF = r'D:\电脑桌面勿删\CAD文件夹\转翠竹路.dxf'
CAB_ACI, TRL_ACI = '4', '3'   # 青=车头, 绿=挂车尾部

# 本工程默认行驶方向：False=正向(东→西,左转向南)  True=反向(南→北,右转向东)
DEFAULT_REVERSE = False


def run(title, args):
    print()
    print('=' * 62)
    print('▶ ' + title)
    print('=' * 62, flush=True)
    r = subprocess.run([sys.executable, '-X', 'utf8'] + args, cwd=BASE)
    if r.returncode != 0:
        print('\n*** 步骤失败：%s（退出码 %d）' % (title, r.returncode))
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dxf', default=DEFAULT_DXF, help='DXF 图纸路径')
    ap.add_argument('--no-render', action='store_true', help='只提取+验收，不渲染视频')
    ap.add_argument('--reverse', action='store_true', help='行驶方向反转（起终点互换）')
    ap.add_argument('--forward', action='store_true', help='强制正向（覆盖 DEFAULT_REVERSE）')
    a = ap.parse_args()

    if not os.path.exists(a.dxf):
        print('找不到图纸:', a.dxf)
        sys.exit(2)
    print('图纸:', a.dxf)

    traj_args = ['extract_cad_traj.py', a.dxf, CAB_ACI, TRL_ACI]
    rev = True if a.reverse else (False if a.forward else DEFAULT_REVERSE)
    if rev:
        traj_args.append('--reverse')
    run('1/6 提取车头/尾部轨迹' + ('（反向：南→北）' if rev else '（正向：东→西）'), traj_args)
    run('2/6 提取图纸其它元素', ['extract_drawing.py', a.dxf])
    # 3/6 嵌入图片（航拍底图）：没有图片也不影响后续
    print()
    print('=' * 62)
    print('▶ 3/6 提取嵌入图片（航拍底图）')
    print('=' * 62, flush=True)
    subprocess.run([sys.executable, '-X', 'utf8', 'make_photo.py', a.dxf], cwd=BASE)
    run('4/6 物理模型验收', ['_final_check.py'])

    if a.no_render:
        print('\n（--no-render：跳过渲染）')
        return

    run('5/6 渲染竖版', ['leaf_truck_sim.py'])
    run('6/6 渲染横版', ['leaf_truck_wide.py'])

    print()
    print('=' * 62)
    print('完成：')
    for f in ('叶片车行走模拟.mp4', '叶片车行走模拟_横版.mp4'):
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            print('  %-26s %5.2f MB' % (f, os.path.getsize(p) / 1048576.0))
    print('=' * 62)


if __name__ == '__main__':
    main()
