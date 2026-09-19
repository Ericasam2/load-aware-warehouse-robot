# 纯 Python A* 动画仿真

无需启动 Unity、ROS 或 Docker。程序读取已经导出的仓库几何快照及栅格地图，不读取 Unity 场景文件。依赖为 NumPy、Pillow；默认交互播放器是生成的离线 HTML，使用浏览器打开，无需联网；可选 --tk 使用 Tkinter。

## 1. 打开终端并进入项目

以下命令在 PowerShell 或 VS Code 的 PowerShell 终端执行，不是在 Python 的 `>>>` 提示符中执行。如果已经进入 `>>>`，先输入 `exit()`。不需要运行 CMD/PS1 启动脚本，也不需要修改 PowerShell 执行策略。

```powershell
cd "C:\Users\hairo\OneDrive\文档\找工\load-aware-warehouse-robot"
```

## 2. 选择 Python（每个新终端执行一次）

当前电脑已经验证过的 Python 和依赖可直接使用：

```powershell
$simPython = "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
& $simPython --version
& $simPython -c "import numpy, PIL; print('Dependencies OK')"
```

这里 `$simPython` 只是解释器路径变量，`&` 表示直接运行该解释器，没有调用启动脚本。输出 `Dependencies OK` 后继续第 3 步。

如果使用自己的 Python，可改为 `$simPython = 'python'`，随后执行相同检查。如果提示缺少依赖，首次安装：

```powershell
& $simPython -m pip install -r requirements-planning.txt
```

安装依赖需要网络，之后仿真无需联网。

## 3. 启动空载到 P1 仿真

```powershell
& $simPython -m warehouse_planning.animation --scenario pickup --show
```

等待搜索、碰撞检查和动画生成完成，终端会输出路径长度、展开数量和 `geometry PASS`，随后默认浏览器打开本地播放器。先播放搜索展开，再播放机器人沿路径移动。播放器支持暂停、重播、调速及拖动进度。

## 4. 启动载货绕障仿真

```powershell
& $simPython -m warehouse_planning.animation --scenario detour --show
```

该场景在高通道加入临时障碍，载货机器人重新规划绕行路径。

## 5. 只生成文件 / 检查结果

```powershell
& $simPython -m warehouse_planning.animation --scenario pickup
& $simPython -m warehouse_planning.animation --help
```

如果系统已经支持 `python` 命令，上述调用可直接简写为：

```powershell
python -m warehouse_planning.animation --scenario pickup --show
python -m warehouse_planning.animation --scenario detour --show
```

程序生成文件后就会退出，浏览器播放器独立运行；关闭浏览器标签即可结束观看。生成期间可在终端按 Ctrl+C 取消。

## 从 Python / Jupyter 内调用

如果希望在 Python 代码中运行，而不是终端命令，选择装有 NumPy、Pillow 的解释器后执行：

```python
import os
import sys
import webbrowser
from pathlib import Path

project = Path(r"C:\Users\hairo\OneDrive\文档\找工\load-aware-warehouse-robot")
os.chdir(project)
if str(project) not in sys.path:
    sys.path.insert(0, str(project))

from warehouse_planning.animation import generate

scenario = "pickup"  # 改为 "detour" 可观看绕障
output = project / "outputs" / "python_sim" / scenario
frames = generate(scenario, output)
webbrowser.open((output / "player.html").as_uri())
```

常见问题：`No module named warehouse_planning` 表示未进入项目根目录；`No module named numpy/PIL` 表示依赖未安装在当前使用的解释器中。浏览器未自动打开时，手动打开输出目录中的 `player.html`。

去掉 `--show` 只生成动画和播放器文件。也可直接双击已生成的 player.html 播放，不需要重新规划。独立复制运行时保留 `warehouse_planning`、`config`、`maps` 文件夹即可，不需要 `unity_project` 或 `ros2_ws`。

## 动画内容

1. A* 搜索：青色逐步覆盖已展开的 XY 栅格，橙色点为本帧最后显示的搜索位置，顶部显示展开状态数量和该状态的 `g`、`h`、`f=g+h`。
2. 路径结果：绿色为最终路径，橙色矩形及箭头表示机器人尺寸和朝向；载货模式还显示负载轮廓。
3. 路径播放：按前进、倒车和原地转向段插值，转向时不平移。

深灰表示低处实体，金色表示高处结构，红色表示临时障碍。高处结构不一定阻挡当前机器人，碰撞检查依照模式的分层高度和朝向计算。

搜索动画来自真实 A* 展开回调，按实际先后顺序分批播放；为了看清过程，时间经过压缩，同一 XY 栅格只显示首次展开。算法本身保留全部 8 个朝向，不是二维点机器人搜索。动画未显示开放列表，不能把青色理解为完整 open/closed 状态。

## 输出

`outputs/python_sim/pickup/` 和 `outputs/python_sim/detour/` 各包含：

- `player.html`：离线播放器，支持暂停、进度拖动和调速。
- `simulation.gif`：可循环播放的动画。
- `preview.png`：最终路径画面。
- `result.json`：路径、长度、展开数和独立几何检查结果。

这是几何运动演示，不模拟轮胎摩擦、惯性或传感器噪声，也不执行自动取放货。每条路径仍经过原有独立碰撞校验。

