# -*- coding: utf-8 -*-
"""
从 DXF 的 OLE2FRAME 提取嵌入图片（航空照片）→ photo.png

DXF 不能存 OLE 对象本体，但 AutoCAD 会把 EMF 预览以 310 二进制块写进 OLE2FRAME 记录。
本脚本：切出 EMF → 用 Windows GDI+（System.Drawing）渲染成 PNG → 存 photo.png

用法: python -X utf8 make_photo.py ["dxf路径"]
"""
import os, sys, subprocess, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DXF = r'D:\电脑桌面勿删\CAD文件夹\转翠竹路.dxf'


def main():
    dxf = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DXF
    if not os.path.exists(dxf):
        print('找不到图纸:', dxf); return 1

    # 1) 切出 EMF
    r = subprocess.run([sys.executable, '-X', 'utf8',
                        os.path.join(BASE, 'extract_ole_image.py'), dxf], cwd=BASE)
    emf = os.path.join(BASE, '_ole_image.emf')
    if not os.path.exists(emf) or os.path.getsize(emf) < 1024:
        # 本图纸没有图片：清掉上一张残留，否则新图会贴上旧底图（出片以 CAD 图纸为准）
        _stale = os.path.join(BASE, 'photo.png')
        if os.path.exists(_stale):
            os.remove(_stale)
            print('已删除上一张图纸残留的 photo.png')
        print('该图纸没有可提取的嵌入图片 -> 出片以 CAD 图纸自身图元为底图')
        return 0

    # 2) EMF → PNG（Windows GDI+）
    png = os.path.join(BASE, 'photo.png')
    ps1 = os.path.join(BASE, '_emf2png.ps1')
    # 必须带 BOM：PowerShell 5.1 默认按 ANSI 读取无 BOM 的 .ps1，中文路径会乱码
    with open(ps1, 'w', encoding='utf-8-sig') as f:
        f.write('''Add-Type -AssemblyName System.Drawing
$emf = "%s"
$png = "%s"
$mf = New-Object System.Drawing.Imaging.Metafile($emf)
$scale = [Math]::Max(1, [Math]::Min(4, 1600 / $mf.Width))
$w = [int]($mf.Width * $scale); $h = [int]($mf.Height * $scale)
$bmp = New-Object System.Drawing.Bitmap($w, $h)
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.Clear([System.Drawing.Color]::White)
$g.DrawImage($mf, 0, 0, $w, $h)
$g.Dispose()
$bmp.Save($png, [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose(); $mf.Dispose()
Write-Output "$w x $h"
''' % (emf, png))
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1])
    if r.returncode != 0 or not os.path.exists(png):
        # 转换失败同样清掉残留，避免拿旧底图贴新图
        _stale = os.path.join(BASE, 'photo.png')
        if os.path.exists(_stale):
            os.remove(_stale)
        print('!! EMF 转换失败：已清理过期 photo.png，视频不带航拍底图（以 CAD 图纸为准）')
        return 1
    print('底图已生成:', png)
    return 0


if __name__ == '__main__':
    sys.exit(main())
