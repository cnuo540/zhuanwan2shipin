---
name: blade-truck-sim
description: |
  从 CAD 图纸（DXF）生成"风机叶片运输车转弯行驶"模拟视频（竖版 + 横版），
  轨迹与车辆直接叠在图纸自带的航拍底图上，含跟随皮卡与小机工。
  Use when: 用户给一个 DXF 并要求生成或更新叶片车行驶模拟视频、轨迹仿真视频、
  挂车转弯动画；或要调整行驶方向、挂车梁长、叶片长度、皮卡/小机工跟车距离、
  版式图例，或要把成果推送到 GitHub。
  Triggers: 叶片车, 叶片运输, 转弯模拟, 行驶模拟, 轨迹模拟, DXF 转视频,
  挂车梁, 刚性梁, 小机工, 皮卡跟随, 航拍底图, 地理配准, 推送 github.
license: MIT
metadata:
  version: "1.0"
  category: engineering-simulation
  engine: python3.8 + ezdxf + Pillow + numpy + ffmpeg
  source_repo: https://github.com/cnuo540/zhuanwan2shipin
  current_dxf: 转翠竹路.dxf
---

# 叶片车转弯模拟（CAD → 视频）

把 DXF 里的两条样条轨迹变成带物理约束的行驶动画，输出竖版 + 横版两个 MP4。

## 0. 先采集这 6 项（用户说「生成叶片车模拟视频」时必问）

**除图纸路径外，其余 5 项都给默认值；用户没在原话里给全的，先用 `ask_user_question` 问，
一次最多 5 个，缺 6 项就分两批。**

| # | 字段 | 问法 | 当前默认 | 写入参数 |
|---|---|---|---|---|
| 1 | **CAD 图纸 dxf 路径** | 「请提供 DXF 文件路径」（必问） | `转翠竹路.dxf` | `--dxf` |
| 2 | **挂车梁长** | 「挂车梁长多少米？」 | 58.0 | `--beam` → `COUPLE_L` |
| 3 | **叶片车长** | 「叶片长度多少米？」 | 108.0 | `--blade` → `BLADE_L` |
| 4 | **小机工距尾部** | 「小机工跟在尾部后多少米？」 | 50.0 | `--worker` → `WORKER_GAP` |
| 5 | **皮卡距尾部** | 「皮卡跟在尾部后多少米？」 | 60.0 | `--escort` → `ESCORT_GAP` |
| 6 | **起始方向** | 「正向（东→西，左转向南）还是反向（南→北，右转向东）？」 | 正向 = `forward` | `--dir` |

提问要点：

* 逐项列出带默认值（`（默认 58）`），用户答「默认」即沿用；**只问没提供的项**。
* **默认值列取自仓库版本（转翠竹路）**；用户可能在工作目录里调过参数
  （例如换图纸时改过梁长/叶片），提问前先读回实际值，别照抄本表：
  ```powershell
  Select-String -Path "工作目录\leaf_common.py" -Pattern "^COUPLE_L|^BLADE_L|^ESCORT_GAP|^WORKER_GAP"
  ```
* 图纸路径必给绝对路径；给不出就问文件名在不在 `D:\电脑桌面勿删\CAD文件夹\`。
* 答案存在多处冲突时（如同时说 60 和 70），以最后给出的为准，并复述一次确认。

**收集完后不要手改代码**，用一条命令写入（只传用户给出的项，未传的保持原值）：

```powershell
python -X utf8 set_params.py --dxf "D:\...\图纸.dxf" ^
        --beam 58 --blade 108 --worker 50 --escort 60 --dir forward
```

写入是**逐字节安全**的（不碰行尾注释与换行，等值调用完全无变化）；写错值可用同一命令改回。
随后**先验收再渲染**：

```powershell
python -X utf8 make_videos.py --no-render   # 看梁长/夹角/皮卡等是否合格
python -X utf8 make_videos.py               # 合格才渲染出片
```

> 图纸没变、上次参数仍适用时，不必重复询问，直接沿用并在回答里列出本次沿用值。
> 预检见第 5 节，验收标准见第 6 节。

## 1. 代码位置

| 位置 | 说明 |
|---|---|
| `D:\Download\叶片车转弯模拟` | **项目包**（含 DXF、README、成品，就是 GitHub 仓库内容） |
| `D:\360MoveData\Users\86136\Documents\harness-xm` | 工作源（调试、改参数在这里，改完同步到包） |
| `https://github.com/cnuo540/zhuanwan2shipin` | 若上面两个都不存在，直接 clone |

**运行环境**：Python 3.8+，`pip install -r requirements.txt`（ezdxf / numpy / Pillow）；
ffmpeg 需存在（自动按 `FFMPEG` 环境变量 → `PATH` → WinGet → `C:\ffmpeg\bin` 查找）。
EMF→PNG 走 Windows PowerShell + GDI+，**仅 Windows**。

## 2. 一键流程

```powershell
cd "D:\Download\叶片车转弯模拟"
python -X utf8 make_videos.py               # 全套：提取→图元→底图→验收→渲染
python -X utf8 make_videos.py --no-render   # 只提取+验收（约30秒，调参时用）
python -X utf8 make_videos.py --dxf "新图纸.dxf"
python -X utf8 make_videos.py --reverse     # 行驶方向反转（或 --forward 强制正向）
```

Windows 也可双击 `一键生成视频.bat`。

**输出按 DXF 名自动命名**：`转翠竹路.dxf` → `转翠竹路.mp4`（竖版）+ `转翠竹路_横版.mp4`（横版）。
名字记录在 `_traj.json` 的 `src` 字段，由 `leaf_common.DXF_NAME` 提供给两个渲染器。

六步流水线：① `extract_cad_traj.py` 提取轨迹 → ② `extract_drawing.py` 提取其它图元
→ ③ `make_photo.py`（内部 `extract_ole_image.py` 切 OLE EMF）→ ④ `_final_check.py` 验收
→ ⑤ `leaf_truck_sim.py` 竖版 → ⑥ `leaf_truck_wide.py` 横版。

## 3. 五个核心要点

### ① 车辆行驶方向
`make_videos.py` 第 17 行 `DEFAULT_REVERSE`：**False=正向（东→西，左转向南，画面右上→左下）**、
True=反向（南→北，右转向东，左下→右上）。也可命令行 `--reverse` / `--forward` 覆盖，
或在 CAD 里用 `REVERSE` 命令反转样条方向。
反向只改点序，**装货位、车尾起点、皮卡位置、起终点标注全部自动跟着变**。
配套对照图在 `参考/方向对比.png`。

### ② 车头走青色轨迹，车尾走绿色轨迹
| 对象 | ACI 色号 | 作用 |
|---|---|---|
| 牵引车（车头） | **4（青）** | 沿此线以 `SPEED` 行驶 |
| 挂车尾部 | **3（绿）** | 被牵引沿线滑动，与挂接点恒距 `COUPLE_L` |

- 两条必须是 **SPLINE**，用 `flattening()` 取点（**绝不能用 control_points 插值**，会外凸成波浪，实测最大偏差 9 m）。
- 车尾线不能由车头线偏移得到：长梁转弯有明显内轮差（本图纸车头最小半径 43.8 m、车尾 40.6 m，车尾早 40 m 转弯）。
- 颜色对调时改 `make_videos.py` 的 `CAB_ACI, TRL_ACI = '3', '4'`。

### ③ DXF 应包含什么
| 内容 | 图元 | 必需 |
|---|---|---|
| 车头/车尾轨迹 | SPLINE，ACI 4 / 3 | ✅ 必需 |
| 航拍图片 | `OLE2FRAME`（OLE 对象，EMF 预览在 310 块里） | 推荐 |
| 道路/圆角/圆/多段线/文字 | LINE / ARC / CIRCLE / LWPOLYLINE / MTEXT | 可选 |

DXF **不保存 OLE 本体**，程序是从 `OLE2FRAME` 的 `310` 二进制块切 EMF 再转 PNG。
底图缺位也不影响出片（只是没有底图）。图片与轨迹的配准存于 `photo_geo.json`：

```powershell
python -X utf8 calibrate_from_shot.py "CAD截图.png"   # 像素级标定（推荐，实测偏差 0.4px）
python -X utf8 georef_photo.py --scale 4.476          # 粗配准（自动测车道 + 比例）
```

**配准自检**：配完后轨迹必须**北在上、左转仍是左转**，且压在车道上；否则 y 方向或锚点反了。

#### 底图判定（流水线第 3 步自动二选一）

| 情况 | 识别信号 | 处理 |
|---|---|---|
| **图纸有航拍图** | `OLE2FRAME` 存在且切得出 EMF（`preflight_dxf.py` 报「内含 EMF 预览」） | **加航拍底图**：`photo.png` 贴在最下层，轨迹直接压在真实路面上 |
| **图纸没有航拍图** | 提取报告「未找到 OLE2FRAME」，或 `preflight` 报「无」 | **以 CAD 图纸为准**：按原样绘制道路线/圆角/圆/多段线/文字作为底图，画面是浅灰网格 + CAD 元素，**不是空白** |
| **换过图纸、残留旧底图** | 新图纸无 OLE，但根目录还留着上一张的 `photo.png` | `make_photo.py` 自动删除残留；否则新图会贴上**错位的旧照片**（严禁手工保留） |

* 两种情况**版式完全一致**（主图与放大窗按内容宽高比居中、底部通栏），只有最底层不同；
* 先跑 `python -X utf8 preflight_dxf.py 图纸.dxf` 就能预知走哪条分支，不必等渲染到第 3 步；
* 想给无底图的图纸补照片：CAD 里导出一张存为 `photo.png` 放到项目根目录，再
  `calibrate_from_shot.py` 或 `georef_photo.py` 标定 `photo_geo.json`；
* 无底图时不需要 `photo_geo.json`（缺了也不影响），有图而缺配准则会贴错位置。

### ④ 皮卡距尾部、小机工位置（都走青线，位置由"尾部"反推）
```python
ESCORT_GAP = 60.0   # 黄色皮卡距挂车尾部沿路距离（m）
WORKER_GAP = 50.0   # 红色小机工距尾部（m）
WORKER_H   = 4.0    # 小机工图标高度（m）
```
`leaf_common._follower(gap)`：尾部投影到青线弧长 − gap；不足时沿青线起点切线外推，**不外推就永远不满足**。
图层次序：车尾 → 叶片 → 小机工 → 皮卡（后画的在上层）。标签分别画在图标左/右，避免相撞。

### ⑤ 挂车梁长、叶片长度
```python
COUPLE_L = 58.0    # 挂车梁长（刚性：挂接点→车尾）
BLADE_L  = 108.0   # 叶片长度（尖端超出梁尾约 48 m）
```
改 `COUPLE_L` 后**装货位会自动重算**（`_auto_park_u()` 找"挂接点→绿线起点=梁长"的车头位置），
不用手改。底部信息行显示的梁长取 `COUPLE_L` 常量（刚性定值，不跳动）。

## 4. 常用参数速查（`leaf_common.py` 顶部）

| 参数 | 当前值 | 含义 |
|---|---|---|
| `SPEED` | 4.0 | 车头沿青线速度 m/s |
| `COUPLE_L` / `BLADE_L` | 58.0 / 108.0 | 梁长 / 叶片长（m） |
| `CAB_L`,`CAB_W`,`TRL_W` | 8.0, 2.6, 3.6 | 牵引车长宽 / 挂车梁宽 |
| `ESCORT_GAP` / `WORKER_GAP` | 60.0 / 50.0 | 皮卡 / 小机工距尾部（m） |
| `FPS`,`DUR`,`P2`,`P3` | 30, 16, 0.16, 0.96 | 30fps、素材16s、片头裁剪点 |
| `MIRROR_Y` | True | 世界 y 取反，与渲染器 y 向下相抵后与 CAD 同向（**不要关**） |
| `DEFAULT_REVERSE` | False | 行驶方向（见要点①） |
| `window`,`max_step` | 120, 4.0 | 尾部求解窗口(点)/单帧步长(点) |

> **车尾梁长被拉长时**：调大 `solve_tail_positions` 的 `window` / `max_step`；
> **车辆朝向反了**：`MIRROR_Y` 或配准 y 方向；**轨迹波浪**：确认用了 `flattening()`。

## 5. 新图纸预检（先跑这个）

```powershell
python -X utf8 preflight_dxf.py "新图纸.dxf"   # 在项目目录内执行（脚本已随包分发）
```
检查轨迹样条颜色、OLE 图片、其它图元是否齐全，避免跑到一半才发现缺轨迹。

## 6. 验收标准（`python -X utf8 _final_check.py`）

| 指标 | 合格 |
|---|---|
| 车尾单调前进 | `True` |
| 最大单帧位移 | < 2 m |
| 挂车梁长 | 49~60 m 区间贴住 `COUPLE_L`（如 57.9~59.0），**偏离 >5m 的帧 = 0** |
| 车挂夹角峰值 | 20°~60°（>90° 说明求解跑偏） |
| 车尾行程 | ≈ 绿线总长 75~85% |
| 皮卡距尾部 | 贴住 `ESCORT_GAP`（如 56.5~60.0） |
| 装货位误差 | < 1 m |

当前（转翠竹路）：梁长 57.9~59.0、夹角 28.1°、车尾 0→177.1/237.8 m、装货位 青线 24.83%。

## 7. 画面与版式

- 横版：宽幅主图（含航拍底图）+ 局部放大窗 + 底部阶段/图例/信息条；**右侧数据面板已移除**（用户要求）。
- 竖版：全局图 + 尾部↔皮卡放大窗。
- 图例文字**不写距离数值**（只要「跟随皮卡」「小机工」），避免与参数脱节。
- 车辆尺寸只从 `leaf_common` 取（`leaf_truck_sim` 顶部已 `BLADE_L = LC.BLADE_L`，**不要在渲染器里复制参数**，会漂移）。

## 8. 交付前（GitHub）

```powershell
cd "D:\Download\叶片车转弯模拟"
python -X utf8 make_videos.py --no-render     # 包内自检（退出码 0）
git status --short
git add -A
git commit -m "一句话说明改动"
git push origin main
```
`.gitignore` 已排除 `_traj.json` / `photo.png` / `_ole_image.emf` / `frames*` 等生成物；
`photo_geo.json` 是标定结果**要提交**。推送前用 `git -c core.quotepath=false ls-tree -r --name-only HEAD` 核对中文文件名。

## 9. 安装到本机 DSH（本 skill 也随仓库走）

仓库里存着可整体安装的副本：`skill/`（`SKILL.md` + `scripts/preflight_dxf.py` + `scripts/set_params.py`）。

```powershell
# 从仓库安装/更新到本机
$repo = "D:\Download\叶片车转弯模拟"            # 或刚 clone 的路径
$dst  = "$env:USERPROFILE\.dsh\skills\blade-truck-sim"
New-Item -ItemType Directory -Path $dst -Force | Out-Null
Copy-Item -Recurse -Force "$repo\skill\*" $dst
```

装完后下次会话即可用 `blade-truck-sim` 触发（或直接说「生成叶片车模拟视频」）。

**脚本有两份，职责不同**：

| 位置 | 用途 |
|---|---|
| `skill/scripts/` | 随 skill 安装到 `.dsh\skills\`，**是镜像** |
| 仓库根目录 `preflight_dxf.py`、`set_params.py` | 在项目目录里直接执行（第 0、5 节命令跑的是**根目录**这份） |

改脚本后**两处都要同步**（或改完根目录直接 `Copy-Item` 覆盖到 `skill\scripts\`），否则会两边漂移。

