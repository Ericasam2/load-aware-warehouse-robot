# Internal SOP — Unity–ROS 2 差速机器人联调

> 文档性质：项目内部开发与运维记录  
> 项目：Load-Aware Warehouse Robot  
> 当前阶段：Milestone 1 — Unity–ROS 2 最小双向通信闭环  
> 最后维护日期：2026-09-06
> 当前状态：已验证 ROS-TCP Endpoint、`/cmd_vel` 和 `/odom` 接口可见；源码已发布至 GitHub

## 1. 文档目的

本文档记录当前功能是如何搭建、实现和验证的，确保后续可以：

- 在新终端或电脑重启后恢复开发环境；
- 快速判断问题位于 Unity、TCP、Docker 还是 ROS 2；
- 理解差速小车控制和里程计发布代码；
- 在不破坏已完成闭环的前提下加入顶撑、雷达和路径规划；
- 为 GitHub README、项目汇报和申请材料提供可追溯的技术依据。

本文档应随项目同步维护，不能只记录预期功能。只有经过实际验证的内容才能标记为“已完成”。

---

## 2. 当前功能范围

当前已经实现的最小闭环：

```text
ROS 2 /cmd_vel
        ↓
ROS-TCP Endpoint（Docker，端口 10000）
        ↓
Unity ROSConnection
        ↓
RosDifferentialDrive
        ↓
Unity Rigidbody 运动
        ↓
Unity /odom
        ↓
ROS-TCP Endpoint
        ↓
ROS 2 /odom
```

当前功能包括：

- Unity 订阅 `geometry_msgs/msg/Twist`；
- 根据线速度和角速度驱动方形机器人；
- Unity 发布 `nav_msgs/msg/Odometry`；
- `/cmd_vel` 超过 0.5 秒未更新时自动停车；
- Unity/ROS 坐标系转换；
- 自动生成最小机器人测试场景的 Editor 工具；
- ROS 2 Jazzy Docker 环境；
- Windows 到容器的 TCP  端口映射。

当前不包括：

- 真实左右轮动力学；
- WheelCollider 或 ArticulationBody 轮组；
- 顶撑和载货状态；
- 激光雷达；
- TF 发布；
- A*、Pure Pursuit 或 PID；
- 仓库环境。

---

## 3. 已验证环境

| 组件 | 当前配置 |
|---|---|
| Host OS | Windows 11 |
| Unity | `6000.6.0f1` |
| ROS 2 | Jazzy |
| ROS 2 运行方式 | Docker Desktop Linux container |
| ROS 镜像 | `osrf/ros:jazzy-desktop` |
| 联调容器 | `ros2-jazzy-unity` |
| 旧容器 | `ros2-jazzy`，保留且未删除 |
| ROS workspace（Windows） | `$ROS2_WS`，本机实际 workspace 路径 |
| ROS workspace（容器） | `/root/ros2_ws` |
| Unity 工程 | `load-aware-warehouse-robot/unity_project` |
| ROS-TCP host | `127.0.0.1` |
| ROS-TCP port | `10000` |
| ROS-TCP Endpoint 版本 | `0.7.0`，官方 `main-ros2` 分支 |
| Unity ROS-TCP Connector | `v0.7.0` |

### 3.1 为什么创建第二个容器

原有 `ros2-jazzy` 容器没有发布 TCP 端口：

```text
Ports={}
```

Docker 不支持给已经创建的容器直接追加端口映射。为避免删除或覆盖旧容器，项目创建了新的联调容器：

```text
ros2-jazzy-unity
0.0.0.0:10000 → container:10000
```

两个容器可以复用同一个 Windows workspace，但日常 Unity 联调只使用 `ros2-jazzy-unity`。

---

## 4. 项目文件结构

```text
load-aware-warehouse-robot/
├── .gitignore
├── README.md
├── docs/
│   └── INTERNAL_SOP.md
└── unity_project/
    ├── Assets/
    │   ├── Editor/
    │   │   └── BuildMinimalRobotScene.cs
    │   └── Scripts/
    │       └── RosDifferentialDrive.cs
    ├── Packages/
    │   └── manifest.json
    └── ProjectSettings/
        └── ProjectVersion.txt

ros2_ws/
├── src/
│   ├── ROS-TCP-Endpoint/
│   ├── mobile_robot_description/
│   └── simple_client/
├── build/
├── install/
└── log/
```

### 4.1 关键文件说明

#### `unity_project/Packages/manifest.json`

固定 ROS-TCP Connector 版本：

```json
"com.unity.robotics.ros-tcp-connector": "https://github.com/Unity-Technologies/ROS-TCP-Connector.git?path=/com.unity.robotics.ros-tcp-connector#v0.7.0"
```

固定版本的目的：

- 保证开发环境可复现；
- 避免上游 `main` 分支变化导致突然无法编译；
- 使 Unity Connector 与 ROS Endpoint 版本一致。

#### `RosDifferentialDrive.cs`

负责：

- 订阅 `/cmd_vel`；
- 限制最大线速度和角速度；
- 检测命令超时；
- 在 `FixedUpdate()` 中更新 Rigidbody；
- 将 Unity 位姿转换为 ROS 坐标；
- 以约 20 Hz 发布 `/odom`。

#### `BuildMinimalRobotScene.cs`

在 Unity 菜单中增加：

```text
Warehouse Robotics > Build Minimal ROS Robot Scene
```

执行后自动创建：

- 地面；
- 方形机器人底盘；
- 左右轮视觉模型；
- 前向方向标志；
- Rigidbody；
- `RosDifferentialDrive`；
- 摄像机和灯光；
- `Assets/Scenes/MinimalRosRobot.unity`。

车轮当前仅用于视觉显示，不参与动力学计算。

---

## 5. ROS 侧搭建过程

### 5.1 添加 ROS-TCP Endpoint

官方仓库的 ROS 2 主分支当前名称为 `main-ros2`：

```powershell
git clone --branch main-ros2 --single-branch `
  https://github.com/Unity-Technologies/ROS-TCP-Endpoint.git `
  ros2_ws/src/ROS-TCP-Endpoint
```

### 5.2 构建 Endpoint

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"

& $docker exec ros2-jazzy bash -lc `
  'source /opt/ros/jazzy/setup.bash && cd /root/ros2_ws && colcon build --symlink-install --packages-select ros_tcp_endpoint'
```

构建结果：

```text
Summary: 1 package finished
```

构建过程中出现 setuptools 的 dash-separated option 弃用警告。该警告来自上游包配置，目前不影响构建或运行。

### 5.3 创建 Unity 联调容器

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"

$ros2Ws = (Resolve-Path '..\ros2_ws').Path

& $docker run -dit `
  --name ros2-jazzy-unity `
  -p 10000:10000 `
  -v "${ros2Ws}:/root/ros2_ws" `
  osrf/ros:jazzy-desktop `
  bash
```

此命令只在第一次创建容器时运行。后续不要重复执行 `docker run`。

### 5.4 启动 Endpoint

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"

& $docker start ros2-jazzy-unity

& $docker exec -d ros2-jazzy-unity bash -lc `
  'source /opt/ros/jazzy/setup.bash && source /root/ros2_ws/install/setup.bash && exec ros2 run ros_tcp_endpoint default_server_endpoint --ros-args -p ROS_IP:=0.0.0.0'
```

注意：重复启动命令前，应先检查是否已经存在 `/UnityEndpoint`，避免启动多个 Endpoint 进程。

### 5.5 验证 Endpoint

```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 10000
```

预期：

```text
TcpTestSucceeded : True
```

检查 ROS 节点：

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 node list
```

预期包含：

```text
/UnityEndpoint
```

---

## 6. Unity 侧搭建过程

### 6.1 打开工程

通过 Unity Hub 打开：

```text
<repository-root>\unity_project
```

首次打开时等待 Package Manager 下载 ROS-TCP Connector 并完成脚本编译。

### 6.2 ROS 设置

打开：

```text
Robotics > ROS Settings
```

设置：

| 参数 | 值 |
|---|---|
| Protocol | `ROS2` |
| ROS IP Address | `127.0.0.1` |
| ROS Port | `10000` |

切换 Protocol 后 Unity 会更新 `ROS2` scripting define 并重新编译消息类。

### 6.3 创建测试场景

点击：

```text
Warehouse Robotics > Build Minimal ROS Robot Scene
```

打开：

```text
Assets/Scenes/MinimalRosRobot.unity
```

点击 Play。

### 6.4 当前建模资源清单

当前最小场景没有下载或使用第三方 3D 模型，全部由 Unity 内置 Primitive 和项目脚本生成。这样可以减少资源导入、比例不一致、许可证和版本兼容问题。

| 资源 | Unity 来源 | 项目用途 | Collider |
|---|---|---|---|
| Plane | `GameObject > 3D Object > Plane` | 测试地面 | 保留 MeshCollider |
| Cube | `GameObject > 3D Object > Cube` | 机器人底盘 | 保留 BoxCollider |
| Cylinder × 2 | `GameObject > 3D Object > Cylinder` | 左右轮视觉模型 | 禁用 |
| Cube | `GameObject > 3D Object > Cube` | 橙色前向标志 | 禁用 |
| Directional Light | Unity Light | 场景照明 | 不适用 |
| Camera | Unity Camera | 固定斜上方观察 | 不适用 |

相关资源路径：

```text
Assets/Scenes/MinimalRosRobot.unity
Assets/Materials/GroundMaterial.mat
Assets/Materials/RobotMaterial.mat
Assets/Materials/WheelMaterial.mat
Assets/Materials/ForwardMarkerMaterial.mat
Assets/Scripts/RosDifferentialDrive.cs
Assets/Editor/BuildMinimalRobotScene.cs
Assets/Resources/ROSConnectionPrefab.prefab
Assets/Resources/GeometryCompassSettings.asset
```

`ROSConnectionPrefab.prefab` 和 `GeometryCompassSettings.asset` 由 ROS-TCP Connector 的设置流程生成，保存 ROS 地址、端口和坐标方向配置。它们不是机器人几何模型。

### 6.5 场景层级

运行场景生成器后的核心 Hierarchy：

```text
MinimalRosRobot
├── Ground
├── DifferentialRobot
│   ├── LeftWheel
│   ├── RightWheel
│   └── ForwardMarker
├── Directional Light
└── Main Camera
```

对象职责：

- `Ground`：提供测试区域和物理接触面；
- `DifferentialRobot`：机器人根对象，包含底盘 Collider、Rigidbody 和 ROS 控制脚本；
- `LeftWheel`、`RightWheel`：表示差速结构，当前只随底盘运动；
- `ForwardMarker`：橙色标志，明确机器人本地 `+Z` 前进方向；
- `Directional Light`：提供统一照明；
- `Main Camera`：以斜上方固定视角观察运动。

### 6.6 模型尺寸、位置和外观

Unity 场景采用 `1 Unity unit = 1 metre`。

#### 地面

| 属性 | 值 |
|---|---|
| Primitive | Plane |
| Position | `(0, 0, 0)` |
| Local Scale | `(2, 1, 2)` |
| 实际覆盖范围 | 约 `20 m × 20 m` |
| Material | `GroundMaterial` |
| Color | `(0.18, 0.20, 0.22)`，深灰色 |

Unity 内置 Plane 原始尺寸约为 `10 m × 10 m`，因此 X/Z 缩放为 2 后得到约 20 米见方的测试区域。

#### 机器人底盘

| 属性 | 值 |
|---|---|
| Primitive | Cube |
| Name | `DifferentialRobot` |
| Position | `(0, 0.30, 0)` |
| Local Scale | `(0.70, 0.30, 0.90)` |
| 近似外形 | 宽 0.70 m、高 0.30 m、长 0.90 m |
| Material | `RobotMaterial` |
| Color | `(0.10, 0.42, 0.80)`，蓝色 |
| Mass | `40 kg` |
| Use Gravity | `true` |
| Linear Damping | `0.2` |
| Angular Damping | `1.0` |
| Rotation Constraints | Freeze X、Freeze Z |

底盘中心位于 `y=0.30 m`。当前值以快速联调为目标，不代表真实仓储机器人的精确尺寸。

#### 左右轮

| 属性 | LeftWheel | RightWheel |
|---|---|---|
| Parent | `DifferentialRobot` | `DifferentialRobot` |
| Local Position | `(-0.42, -0.10, 0)` | `(0.42, -0.10, 0)` |
| Local Rotation | `(0, 0, 90°)` | `(0, 0, 90°)` |
| Local Scale | `(0.28, 0.10, 0.28)` | `(0.28, 0.10, 0.28)` |
| Material | `WheelMaterial` | `WheelMaterial` |
| Color | `(0.04, 0.04, 0.04)` | `(0.04, 0.04, 0.04)` |
| Collider | Disabled | Disabled |

轮子是底盘子对象，会继承根对象缩放。因此 Inspector 中显示的是 local scale，不应将其直接解释为最终世界尺寸。后续升级真实轮组时，应将机器人根节点改为空 GameObject，把底盘 Mesh 作为独立子对象，避免非均匀父级缩放影响车轮。

#### 前向标志

| 属性 | 值 |
|---|---|
| Parent | `DifferentialRobot` |
| Local Position | `(0, 0.28, 0.36)` |
| Local Scale | `(0.22, 0.10, 0.15)` |
| Material | `ForwardMarkerMaterial` |
| Color | `(1.00, 0.55, 0.05)`，橙色 |
| Collider | Disabled |

橙色块所在方向即 Unity 本地 `+Z`，也对应 ROS 机器人坐标系的 `+x` 前方。

#### 灯光与摄像机

| 对象 | 属性 | 值 |
|---|---|---|
| Directional Light | Rotation | `(45°, -30°, 0°)` |
| Directional Light | Intensity | `1.2` |
| Main Camera | Position | `(4.5, 5.0, -5.5)` |
| Main Camera | Look At | `(0, 0.2, 0)` |

### 6.7 组件与物理配置过程

机器人建模过程：

1. 创建 Cube 作为底盘；
2. 命名为 `DifferentialRobot`；
3. 设置位置、缩放和蓝色材质；
4. 保留 Cube 自动生成的 BoxCollider；
5. 添加 Rigidbody，并配置质量、阻尼和重力；
6. 冻结 X/Z 旋转，防止最小模型侧翻或前后翻滚；
7. 添加 `RosDifferentialDrive`；
8. 创建两个 Cylinder 作为车轮并设为底盘子对象；
9. 将 Cylinder 绕 Z 轴旋转 90°，使轮轴方向与底盘横向一致；
10. 禁用车轮 Collider，避免视觉轮与底盘 Collider 重复接触地面；
11. 创建橙色 Cube 作为前向标志并禁用 Collider；
12. 添加固定摄像机和方向光。

当前 Rigidbody 的实际位移由 `RosDifferentialDrive` 调用 `MovePosition()` 和 `MoveRotation()` 完成。车轮不会根据左右轮角速度独立旋转，也不会通过摩擦力驱动车体。

采用这一实现的原因：

- 当前里程碑首先验证 Unity 与 ROS 2 的双向通信；
- 避免把 WheelCollider 调参与 TCP、topic、坐标转换问题混在一起；
- 运动结果确定，便于检查 `/cmd_vel` 符号和 `/odom` 坐标；
- 后续可在保持 ROS 接口不变的情况下替换底层驱动实现。

### 6.8 自动生成脚本的执行过程

`BuildMinimalRobotScene.BuildScene()` 按以下顺序执行：

```text
Ensure Assets/Scenes
  → NewScene
  → CreateGround
  → CreateRobot
      → Rigidbody
      → RosDifferentialDrive
      → LeftWheel / RightWheel
      → ForwardMarker
  → CreateLighting
  → CreateCamera
  → SaveScene
  → Add scene to EditorBuildSettings
  → Select DifferentialRobot
```

材质通过 `CreateMaterial()` 创建：

1. 优先查找 `Universal Render Pipeline/Lit`；
2. 如果不存在，则使用 `Standard`；
3. 如果同名 `.mat` 已存在，则复用现有材质；
4. 如果不存在，则创建材质资产并保存到 `Assets/Materials`。

场景保存到固定路径：

```text
Assets/Scenes/MinimalRosRobot.unity
```

重要：再次运行该菜单会创建一个新的空场景并覆盖同一路径。对该场景进行重要手工修改前，应先提交 Git，或复制为新场景。正式仓库建模阶段应创建新的 `Warehouse.unity`，不要继续覆盖最小联调场景。

### 6.9 手动复现建模步骤

如果 Editor 脚本不可用，可在 Unity 中手动复现：

1. 新建 Empty Scene；
2. 创建 Plane，缩放为 `(2,1,2)`，命名 `Ground`；
3. 创建 Cube，命名 `DifferentialRobot`；
4. 设置 Position `(0,0.30,0)`、Scale `(0.70,0.30,0.90)`；
5. 添加 Rigidbody，Mass 40，勾选 Freeze Rotation X/Z；
6. 添加 `RosDifferentialDrive` 组件；
7. 在底盘下创建两个 Cylinder，按照 6.6 表格设置左右位置；
8. 禁用两个 Cylinder 的 Collider；
9. 创建橙色 Cube 作为 ForwardMarker，禁用 Collider；
10. 创建 Directional Light 和 Main Camera；
11. 保存为 `Assets/Scenes/MinimalRosRobot.unity`；
12. 在 Build Settings 中加入该场景；
13. 检查机器人橙色标志朝向世界 `+Z`；
14. Play 后执行第 9 节双向通信验证。

### 6.10 当前建模验收标准

- Scene 中能够看到地面、蓝色方形底盘、两只黑色轮子和橙色方向标志；
- 机器人静止时不会穿过地面或发生明显抖动；
- 正 `linear.x` 使机器人沿橙色标志方向移动；
- 正 `angular.z` 符合 ROS 左转约定；
- 轮子和方向标志不会产生额外物理碰撞；
- 运行过程中 Console 无红色错误；
- 场景保存后重新打开仍保留对象和组件。

### 6.11 已修复的编译兼容问题

首次导入时项目仍处于默认 ROS1 编译分支，出现：

```text
CS1503: cannot convert from 'int' to 'uint'
CS7036: required parameter 'frame_id' of HeaderMsg
```

原因：

- ROS1 版本的 `TimeMsg.sec` 是 `uint`；
- ROS1 版本的 `HeaderMsg` 构造函数包含 `seq`；
- ROS2 版本的 `TimeMsg.sec` 是 `int`；
- ROS2 版本的 `HeaderMsg` 不包含 `seq`。

代码使用 `#if ROS2` 分别调用正确构造函数，使项目能够在切换 Protocol 前后正常编译。

黄色 Input Manager deprecation 信息不影响当前里程碑，可暂时忽略。

---

## 7. 差速运动实现

### 7.1 输入消息

ROS 2 输入：

```text
Topic: /cmd_vel
Type: geometry_msgs/msg/Twist
```

当前只使用：

```text
linear.x   前后速度，单位 m/s
angular.z  偏航角速度，单位 rad/s
```

默认限制：

```text
|linear.x|  <= 1.0 m/s
|angular.z| <= 1.5 rad/s
```

### 7.2 运动更新

运动在 Unity `FixedUpdate()` 中执行：

```text
位置增量 = robot_forward × linear_velocity × fixed_delta_time
角度增量 = angular_velocity × fixed_delta_time
```

当前使用：

```csharp
Rigidbody.MovePosition(...)
Rigidbody.MoveRotation(...)
```

这是最小联调阶段的运动学实现。优点是确定性较高，能够先证明通信、坐标和 topic 正确。

### 7.3 命令超时

每次收到 `/cmd_vel` 时记录 Unity 时间。若超过 0.5 秒没有新命令：

```text
linear = 0
angular = 0
```

因此终止 `ros2 topic pub` 后，机器人应在 0.5 秒内停止。

### 7.4 坐标转换

ROS 使用 FLU，Unity 使用 RUF：

| ROS | Unity |
|---|---|
| `+x` forward | `+z` forward |
| `+y` left | `-x` |
| `+z` up | `+y` up |

位置转换：

```text
ros_x = unity_z
ros_y = -unity_x
ros_z = unity_y
```

ROS 正 `angular.z` 对应 Unity 负 Y 轴旋转。

---

## 8. 里程计实现

输出接口：

```text
Topic: /odom
Type: nav_msgs/msg/Odometry
Rate: approximately 20 Hz
Frame: odom
Child frame: base_link
```

当前位置相对于启动 Play 时的机器人位姿计算，因此每次重新 Play 后 odometry 从局部原点开始。

当前 `/odom` 使用 Unity ground truth，不模拟：

- 轮胎打滑；
- 编码器噪声；
- 累积漂移；
- 时间同步误差。

这符合当前项目“已知地图、无需定位感知”的范围。

---

## 9. 双向通信验证 SOP

### 9.1 前置条件

- Docker Desktop 正在运行；
- `ros2-jazzy-unity` 状态为 Up；
- ROS-TCP Endpoint 正在运行；
- Unity ROS Settings 使用 ROS2、`127.0.0.1:10000`；
- Unity 已打开 `MinimalRosRobot` 场景；
- Unity 处于 Play 状态；
- Console 没有红色错误。

### 9.2 进入容器

```powershell
docker exec -it ros2-jazzy-unity bash
```

每个新 shell 都要执行：

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
```

### 9.3 检查 Unity topic

```bash
ros2 topic list
```

Unity 进入 Play 后预期包含：

```text
/cmd_vel
/odom
```

更详细检查：

```bash
ros2 topic info /cmd_vel -v
ros2 topic info /odom -v
```

预期：

- `/cmd_vel` 至少有一个 Unity subscriber；
- `/odom` 至少有一个 Unity publisher。

### 9.4 测试 ROS 2 → Unity

直行：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.5}, angular: {z: 0.0}}"
```

原地转向：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.8}}"
```

弧线运动：

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.4}, angular: {z: 0.3}}"
```

按 `Ctrl+C` 停止发布。机器人应在 0.5 秒内停止。

### 9.5 测试 Unity → ROS 2

另开一个容器 shell：

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 topic echo /odom
```

预期：

- 直行时 `pose.pose.position.x/y` 变化；
- 转向时 `pose.pose.orientation` 变化；
- `twist.twist.linear.x` 与命令一致；
- `twist.twist.angular.z` 与命令一致。

检查频率：

```bash
ros2 topic hz /odom
```

预期约为 20 Hz。

### 9.6 当前已获得的验证证据

2026-09-05 检查结果：

```text
Container: ros2-jazzy-unity Up
Port: 0.0.0.0:10000->10000/tcp
Windows TCP test: True
ROS node: /UnityEndpoint
Unity subscriber node: /cmd_vel_RosSubscriber
Unity publisher node: /odom_RosPublisher
Topics: /cmd_vel, /odom
```

这证明 TCP 和 ROS topic 注册已经成功。小车实际运动和 `/odom` 数值变化仍应按 9.4、9.5 进行人工观察确认。

---

## 10. 日常启动与关闭

### 10.1 每次开发前

1. 启动 Docker Desktop；
2. 启动容器；
3. 检查或启动 Endpoint；
4. 打开 Unity 工程；
5. 检查 ROS Settings；
6. 打开场景并 Play；
7. 使用 `ros2 topic list` 验证。

启动容器：

```powershell
docker start ros2-jazzy-unity
```

检查 Endpoint：

```bash
ros2 node list | grep UnityEndpoint
```

如果不存在，再启动 Endpoint。

### 10.2 开发结束

先退出 Unity Play Mode，再停止容器：

```powershell
docker stop ros2-jazzy-unity
```

停止容器不会删除 workspace 或构建结果。

---

## 11. 常见问题排查

### 11.1 Unity 看不到 `/cmd_vel` 或 `/odom`

按顺序检查：

1. Unity 是否处于 Play；
2. Console 是否有红色错误；
3. ROS Settings 是否为 ROS2；
4. 地址是否为 `127.0.0.1:10000`；
5. `Test-NetConnection` 是否成功；
6. `ros2 node list` 是否包含 `/UnityEndpoint`；
7. 是否错误进入了旧容器 `ros2-jazzy`。

### 11.2 `docker exec` 提示容器未运行

```powershell
docker start ros2-jazzy-unity
```

### 11.3 端口 10000 不通

```powershell
docker ps --filter name=ros2-jazzy-unity
Test-NetConnection 127.0.0.1 -Port 10000
```

确认输出包含：

```text
0.0.0.0:10000->10000/tcp
```

### 11.4 Endpoint package 不可见

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 pkg prefix ros_tcp_endpoint
```

如果只 source ROS 基础环境而没有 source workspace，ROS 2 找不到该包。

### 11.5 小车一直运动，停止命令无效

正常行为是 publisher 停止 0.5 秒后自动停车。检查：

- Unity 是否仍在运行旧脚本；
- Inspector 中 `Command Timeout Seconds` 是否被改大；
- 是否有第二个 `/cmd_vel` publisher 持续发布。

```bash
ros2 topic info /cmd_vel -v
```

### 11.6 小车运动方向反了

检查 Unity 模型的前方是否为本地 `+Z`。场景中的橙色 `ForwardMarker` 表示机器人前方。

### 11.7 Unity 出现 Input Manager deprecation 警告

这是 Unity 6 的黄色弃用提示，不影响当前功能，不作为阻塞问题处理。

---

## 12. 修改与回归验证规则

以后修改通信、机器人运动、坐标系或场景时，必须至少重新验证：

1. `127.0.0.1:10000` 可连接；
2. `/cmd_vel` 有 Unity subscriber；
3. `/odom` 有 Unity publisher；
4. 正线速度使机器人沿橙色标志方向前进；
5. 正 `angular.z` 的转向与 ROS 约定一致；
6. 停止发布后 0.5 秒内停车；
7. `/odom` 频率接近配置值；
8. Unity Console 无红色错误。

禁止在未完成上述验证时将状态标记为“已完成”。

---

## 13. 后续开发顺序

在保持当前闭环可运行的前提下，按以下顺序扩展：

1. 验证实际运动方向、角速度符号和 odometry 数值；
2. 将运动学底盘升级为显式左右轮速度模型；
3. 添加顶撑和载货状态；
4. 构建简化仓库场景；
5. 添加二维雷达；
6. 添加已知地图和 empty/loaded costmap；
7. 实现 load-aware A*；
8. 实现路径跟踪；
9. 实现取货—运输—放货任务状态机。

当前通信闭环在每个阶段都应保持可独立运行。

---

## 14. 文档维护规则

每次完成一项功能时，同一个变更中必须更新：

- 第 2 节“当前功能范围”；
- 第 3 节“已验证环境”（如版本发生变化）；
- 对应实现章节；
- 第 9 节验证流程与证据；
- 第 13 节后续顺序；
- 第 15 节变更日志；
- 页首“最后维护日期”和“当前状态”。

若实际实现与项目计划不同，SOP 记录实际实现，项目计划记录目标和范围。

---

## 15. 变更日志

### 2026-09-06 — 补充 Unity 建模 SOP

- 记录当前建模使用的全部 Unity 内置资源；
- 记录场景 Hierarchy、对象命名和资源路径；
- 记录地面、底盘、轮子、前向标志、灯光和摄像机参数；
- 记录 Collider、Rigidbody、质量、阻尼和旋转约束；
- 说明运动学底盘方案的选择原因和当前限制；
- 记录自动场景生成器的内部执行顺序；
- 补充不依赖 Editor 脚本的手动复现流程；
- 增加场景覆盖风险提示和建模验收标准。

### 2026-09-05 — Milestone 1 基础搭建

- 确认 Unity `6000.6.0f1`；
- 确认 ROS 2 Jazzy 位于 Docker 容器；
- 保留原有 `ros2-jazzy` 容器；
- 添加并构建官方 `ros_tcp_endpoint`；
- 创建发布 `10000` 端口的 `ros2-jazzy-unity` 容器；
- 验证 Windows TCP 连接；
- 固定 Unity ROS-TCP Connector `v0.7.0`；
- 实现 `/cmd_vel` 订阅；
- 实现运动学差速底盘；
- 实现 0.5 秒命令超时；
- 实现 `/odom` 发布；
- 添加最小测试场景生成工具；
- 修复 ROS1/ROS2 `HeaderMsg` 和 `TimeMsg` 构造函数差异；
- 验证 `/UnityEndpoint`、`/cmd_vel_RosSubscriber`、`/odom_RosPublisher` 可见。

### 2026-09-05 — Git 与 GitHub 发布

- 将 `load-aware-warehouse-robot` 初始化为独立 Git 仓库；
- 默认分支设置为 `main`；
- 配置 Unity、ROS 2、IDE 和操作系统生成文件忽略规则；
- 清理公开文档中的本机绝对路径；
- 检查待提交内容中是否存在 Token、密钥和个人邮箱；
- 添加 Apache License 2.0；
- 创建首个提交 `0766fbf`；
- 创建公开仓库 `Ericasam2/load-aware-warehouse-robot`；
- 配置 `origin` 并成功推送 `main`；
- 在 GitHub 页面验证 README、License、文档和源码可见。

---

## 16. Git 与 GitHub SOP

远端仓库：

```text
https://github.com/Ericasam2/load-aware-warehouse-robot
```

分支策略：

- 当前开发阶段使用 `main`；
- 每个可独立验证的功能使用一笔清晰提交；
- 后续复杂功能可以使用短期 feature branch；
- 不提交 Unity `Library`、`Temp`、`Logs`、`UserSettings`；
- 不提交 ROS 2 `build`、`install`、`log`；
- 不提交公司、客户或真实仓库项目的敏感参数。

日常提交：

```bash
git status
git add <changed-files>
git commit -m "<type>: <verified change>"
git push origin main
```

建议提交类型：

```text
feat: 新功能
fix: 缺陷修复
docs: 文档更新
test: 测试与验证
refactor: 不改变外部行为的重构
```

推送前检查：

1. Unity Console 无红色错误；
2. 运行与本次修改相关的回归验证；
3. `git status` 中没有缓存、日志或临时文件；
4. 检查是否包含账号、Token、客户名称和本机绝对路径；
5. 更新本 SOP 的当前状态、验证证据或变更日志。
