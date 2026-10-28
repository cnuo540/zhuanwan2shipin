# -*- coding: utf-8 -*-
"""
从 DXF 的 OLE2FRAME 中提取嵌入式图片（EMF）到文件，并解析其物理尺寸。

DXF 不能存 OLE 对象本体，但 AutoCAD 会把 EMF 预览以 310 二进制块写进 OLE2FRAME 记录里。
OLE2FRAME 的 XDATA(ACAD) 里还有插入点和尺寸：
    1000 OLEBEGIN
    1070 41 / 1040 <x>      插入点 X
    1070 42 / 1040 <y>      插入点 Y
    1070 43 / 1040 <w>      宽
    1070 44 / 1040 <h>      高
    1000 OLEEND
"""
import os, re, struct, sys

BASE = os.path.dirname(os.path.abspath(__file__))


def find_ole_record(path):
    data = open(path, 'rb').read()
    i = data.find(b'OLE2FRAME')
    if i < 0:
        return None
    # 记录从实体名开始，到下一个 "  0\r\n" 为止
    j = data.find(b'\r\n  0\r\n', i + 10)
    while j > 0:
        nxt = data[j + 7:j + 40].split(b'\r\n')[0].strip()
        # 跳过 xdata 内部的 1070/1000 之类（它们不以 "  0" 开头）
        if nxt and re.match(rb'^[A-Z]', nxt):
            break
        j = data.find(b'\r\n  0\r\n', j + 5)
    return data[i:j if j > 0 else len(data)]


def parse_pairs(rec):
    lines = [l.strip() for l in rec.split(b'\r\n')]
    pairs = []
    k = 0
    while k + 1 < len(lines):
        code = lines[k]
        if re.match(rb'^-?\d+$', code):
            pairs.append((int(code), lines[k + 1]))
            k += 2
        else:
            k += 1
    return pairs


def extract_emf(dxf_path):
    rec = find_ole_record(dxf_path)
    if rec is None:
        # 本图纸没有 OLE：清掉上一张残留的 EMF，否则 make_photo 会拿旧图转出 photo.png，
        # 导致"无底图的图纸"贴上别的图纸的航拍图（出片应以 CAD 图纸为准）
        _emf = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_ole_image.emf')
        if os.path.exists(_emf):
            os.remove(_emf)
            print('未找到 OLE2FRAME；已删除残留 _ole_image.emf（不沿用上一张图纸的底图）')
        else:
            print('未找到 OLE2FRAME')
        return None
    pairs = parse_pairs(rec)
    blob = b''
    xdata = {}
    pending = None
    for code, val in pairs:
        if code == 310:
            try:
                blob += bytes.fromhex(val.decode('ascii'))
            except ValueError:
                pass
        elif code == 1070:
            pending = int(val)
        elif code in (1040, 1071) and pending is not None:
            try:
                xdata[pending] = float(val)
            except ValueError:
                pass
            pending = None
    print('310 二进制块合计 %d 字节（%.1f KB）' % (len(blob), len(blob) / 1024))
    print('xdata: 41(x)=%s 42(y)=%s 43(w)=%s 44(h)=%s' % (
        xdata.get(41), xdata.get(42), xdata.get(43), xdata.get(44)))
    if not blob:
        print('没有二进制数据（该 DXF 未保存 OLE 预览）')
        return None

    # 找 EMF 头（iType=1, 签名 " EMF"）
    pos = blob.find(b' EMF')
    start = pos - 40 if pos >= 40 else 0
    if pos < 0:
        print('未找到 " EMF" 签名，按原始数据保存')
        out = os.path.join(BASE, '_ole_payload.bin')
        open(out, 'wb').write(blob)
        print('已保存原始数据:', out)
        return out, xdata

    emf = blob[start:]
    hdr = emf[:88]
    iType, nSize = struct.unpack_from('<II', hdr, 0)
    bounds = struct.unpack_from('<4l', hdr, 8)     # 设备单位(像素)
    frame = struct.unpack_from('<4l', hdr, 24)     # 0.01 mm
    sig = hdr[40:44]
    version, nBytes, nRecords = struct.unpack_from('<III', hdr, 44)
    print('EMF: type=%d size=%d 签名=%r 版本=%d 记录数=%d' % (iType, nSize, sig, version, nRecords))
    print('     设备bounds %s  → 像素 %dx%d' % (bounds, bounds[2] - bounds[0], bounds[3] - bounds[1]))
    print('     物理frame %s  → %.1f x %.1f mm' % (frame, (frame[2] - frame[0]) / 100.0, (frame[3] - frame[1]) / 100.0))

    out = os.path.join(BASE, '_ole_image.emf')
    open(out, 'wb').write(emf)
    print('已保存 EMF:', out)
    return out, xdata


if __name__ == '__main__':
    dxf = sys.argv[1] if len(sys.argv) > 1 else r'D:\电脑桌面勿删\CAD文件夹\转翠竹路.dxf'
    extract_emf(dxf)
