# ROS 2 + Unity A* 联合测试 SOP

当前联调入口执行空载 `RobotStart → Pickup_P1`：ROS 内运行 A*，发布 `/planned_path` 和 `/cmd_vel`，Unity 使用 WheelCollider 物理驱动并反馈 `/odom`、`/lift/state`。ROS 根据反馈跟踪直线段与原地转向段，最后停车并保存实际轨迹。

## 1. 启动 ROS

打开 Docker Desktop，等待 Linux engine 正常运行。使用原有容器 `ros2-jazzy-unity`，其中应已构建 ROS-TCP Endpoint，工作空间为 `/root/ros2_ws`。不需要重建容器。

在项目根目录 PowerShell 执行：

```powershell
.\tools\Run-RosUnityTest.ps1 -PrepareOnly
```

脚本检查 ROS Python、NumPy、Pillow，复制当前规划代码和地图到容器 `/tmp/warehouse-astar`，复用或启动 TCP Endpoint（端口 10000）。如果提示缺少 numpy/PIL，在容器中安装 `python3-numpy python3-pil` 后重试。

## 2. 打开 Unity

如果保存或重建仓库后提示 `Scene changed` / `Stale maps`，先退出 Play，保存 `WarehouseEnvironment`，执行 Unity 菜单 **Warehouse Robotics → Export A Star Planning Geometry**，再在 PowerShell 运行 `.\tools\Build-PlanningMap.ps1 -RunTests`。随后重新运行准备脚本。场景和规划地图必须来自同一版本；启动脚本现在会提前检查并给出更新步骤。

1. 打开 `unity_project`，等待脚本编译完成。
2. 打开 **Assets/Scenes/WarehouseEnvironment.unity**，不要使用 MinimalRosRobot 场景。
3. ROS Settings 使用 ROS2、`127.0.0.1:10000`，项目已保存该配置。
4. 点击 Play。机器人应从保存的起点开始，举升平台完全收回。
5. 停止其他持续发布 `/cmd_vel` 的测试命令。无需手动发布速度。

不要在 Play 中移动机器人 Transform，也不要修改保存的起点。每次重新测试先退出 Play 再进入，确保 odom 原点与地图元数据一致。

## 3. 执行测试

```powershell
.\tools\Run-RosUnityTest.ps1
```

节点最多等待 Unity 60 秒；全程上限 240 秒。默认直线限速 0.18 m/s，转向限速 0.25 rad/s；段间至少停车 0.6 秒并检查实际速度。Unity 显示青色规划路径，小车应前进、停车转向，然后进入 P1 镂空交互通道并停下。本测试到达 P1 后结束，不举升、不搬货。

坐标转换由元数据 `map_from_odom=(-6,7,0)` 完成；Unity 同时上报实际场景与出生位姿，错误场景或原点不一致会拒绝运动。`/planned_path` 使用 map 坐标，本流程没有发布 TF 树，也不依赖 Nav2。

## 4. 判断结果

查看 `outputs/ros_unity/run_report.json`：必须同时满足 `status=SUCCESS`、`passed=true`。终点相对规划格中心误差不超过 0.035 m、航向误差不超过 0.025 rad，并且反馈速度低于阈值持续 1 秒。

- `planned_path.json/csv`：本轮 A* 路径。
- `actual_trajectory.csv`：实际 map 位姿、控制指令、执行段序号。
- `run_report.json`：本轮状态、终点误差、采样数。

可运行 `python tools/Plot-RosUnityRun.py` 生成 `trajectory-comparison.png`（需要 Pillow），蓝色为规划、绿色为实测。仓库灰色投影包含高处结构，不能直接当作地面封闭障碍。

这些文件只在 ROS 节点实际运行后生成；不能把离线 `outputs/astar` 报告当作联合测试通过。

断开 odom/lift 反馈、举升未收回、明显路径偏差、采样轮廓净空不足、起点不匹配或超时都会停车并返回失败。**停止 Unity Play 是直接结束仿真的方式**；Unity 自带 0.5 秒速度指令超时停车。在容器终端直接运行节点时，Ctrl+C 会发送停车并保存中断报告；不要仅依赖关闭 Windows 的 docker exec 窗口来停止容器进程。

## 5. 当前验证记录（2026-09-18）

- 16 项 Python 测试通过，包含跟踪器坐标转换、前进/转向/倒车及偏差拒绝。
- **ROS 2 Jazzy 容器 + Unity 6000.6.0f1 批处理 Play Mode 物理闭环已通过**，不是运动学替身。
- 规划长度 9.941 m，运行约 77.46 秒，记录 1420 个跟踪采样；到达 P1 后确认静止。
- 最终 map 位姿 `(2.01110, 5.02268, -1.57114)`，相对规划格中心位置误差 0.01027 m，航向误差 0.000340 rad（约 0.0195°）。相对原始 P1 标记 `(2,5)` 的位置误差约 0.02525 m；区别来自 0.025 m 栅格中心吸附。
- 结果见 `outputs/ros_unity/run_report.json` 和 `actual_trajectory.csv`。采用独立几何轮廓采样检测 0.005 m 净空；路径规划仍使用 0.02 m 余量。
- 联调发现并修复两项问题：探测 TCP 端口会抢占 Endpoint 活动连接，改为读取 `/proc/net/tcp`；直接用低速 WheelCollider RPM 做高增益反馈会振荡，改为轮位置刚体前向速度 PI 闭环及抗饱和。车轮依然通过 `motorTorque` 和地面摩擦推动刚体，没有直接写 Transform 或刚体速度。
- Docker 首次启动因 `dockerInference` 运行时文件报错，重试后恢复；未重置 Docker，也未删除容器或镜像。
- 保持机器人在 P1，再次运行节点时正确返回 `RESET_UNITY_TO_ROBOT_START`，没有开始第二次行驶；独立报告为 `outputs/ros_unity/reset-guard-report.json`。

载货场景仍需机器人与容器的连接/释放逻辑，本入口暂不开放载货执行。反馈轮廓采样不等于物理接触传感器或真实机器人安全认证。
