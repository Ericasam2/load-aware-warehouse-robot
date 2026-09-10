# Internal SOP — Unity–ROS 2 差速机器人联调

> 文档性质：项目内部开发与运维记录  
> 项目：Load-Aware Warehouse Robot  
> 当前阶段：Milestone 3 — 物理差速轮模型
> 最后维护日期：2026-09-10
> 当前状态：物理差速轮代码与场景升级工具已实现并通过编译；当前场景仍需执行升级菜单并完成 Play Mode 动力学联调

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
        ↓ 差速逆运动学
左右 WheelCollider 轮速闭环
        ↓ 电机扭矩、轮地摩擦与制动
Unity Rigidbody 物理运动
        ↓
Unity /odom
        ↓
ROS-TCP Endpoint
        ↓
ROS 2 /odom
```

举升自由度使用独立闭环：

```text
ROS 2 lift_command_node
        ↓ /lift/command（目标伸长量）
Unity RosLiftController
        ↓ 限速位置运动
LiftPlatform 高度变化
        ↓ /lift/state + /lift/at_target
ROS 2 lift_command_node 到位确认
```

当前功能包括：

- Unity 订阅 `geometry_msgs/msg/Twist`；
- 将线速度和角速度换算为左右轮目标角速度；
- 通过两个 `WheelCollider` 的电机扭矩驱动方形机器人；
- 车轮视觉模型跟随物理轮位置和转角；
- Unity 发布 `nav_msgs/msg/Odometry`；
- Unity 订阅 `/lift/command` 并控制顶撑高度；
- Unity 发布 `/lift/state` 和 `/lift/at_target`；
- ROS 2 `warehouse_lift_control` 节点支持运行时修改目标高度；
- `/cmd_vel` 超过 0.5 秒未更新时自动停车；
- Unity/ROS 坐标系转换；
- 自动生成最小机器人测试场景的 Editor 工具；
- ROS 2 Jazzy Docker 环境；
- Windows 到容器的 TCP  端口映射。

当前不包括：

- 独立 `ArticulationBody` 轮轴与电机动力学；
- 编码器噪声、打滑里程计和轮胎参数标定；
- 货物连接、释放和载货状态机；
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
- 执行差速逆运动学，计算左右轮目标角速度；
- 根据 `WheelCollider.rpm` 做比例轮速控制并施加电机扭矩；
- 静止或命令超时时施加保持制动；
- 使用 `GetWorldPose()` 同步左右轮视觉模型；
- 将 Unity 位姿转换为 ROS 坐标；
- 以约 20 Hz 发布刚体实测 `/odom`。

#### `BuildMinimalRobotScene.cs`

在 Unity 菜单中增加：

```text
Warehouse Robotics > Build Minimal ROS Robot Scene
```

执行后自动创建：

- 地面；
- 方形机器人底盘；
- 左右轮视觉模型和两个物理 `WheelCollider`；
- 前向方向标志；
- Rigidbody；
- `RosDifferentialDrive`；
- 摄像机和灯光；
- `Assets/Scenes/MinimalRosRobot.unity`。

若当前场景已经包含举升结构或其他手工编辑，不希望整场重建，可使用：

```text
Warehouse Robotics > Upgrade Current Robot To Physical Wheels
```

该菜单只升级活动场景中的 `DifferentialRobot`，添加或复用左右 `WheelCollider`，调整底盘离地高度并绑定控制器，不会新建场景。

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
| Cube | `GameObject > 3D Object > Cube` | 机器人底盘视觉 | 子对象 Collider 禁用，根节点保留 BoxCollider |
| Cylinder × 2 | `GameObject > 3D Object > Cylinder` | 左右轮视觉模型 | 禁用 |
| WheelCollider × 2 | Unity Physics | 左右驱动轮接触、悬架和摩擦 | 启用 |
| Cube | `GameObject > 3D Object > Cube` | 橙色前向标志 | 禁用 |
| Cube | `GameObject > 3D Object > Cube` | 举升立柱 | 禁用 |
| Cube | `GameObject > 3D Object > Cube` | 举升平台 | 保留 BoxCollider |
| Directional Light | Unity Light | 场景照明 | 不适用 |
| Camera | Unity Camera | 固定斜上方观察 | 不适用 |

相关资源路径：

```text
Assets/Scenes/MinimalRosRobot.unity
Assets/Materials/GroundMaterial.mat
Assets/Materials/RobotMaterial.mat
Assets/Materials/WheelMaterial.mat
Assets/Materials/ForwardMarkerMaterial.mat
Assets/Materials/LiftMaterial.mat
Assets/Scripts/RosDifferentialDrive.cs
Assets/Scripts/RosLiftController.cs
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
│   ├── Chassis
│   ├── LeftWheel
│   ├── RightWheel
│   ├── LeftWheelCollider
│   ├── RightWheelCollider
│   ├── ForwardMarker
│   ├── LiftColumn
│   └── LiftPlatform
├── Directional Light
└── Main Camera
```

对象职责：

- `Ground`：提供测试区域和物理接触面；
- `DifferentialRobot`：无缩放的机器人根对象，包含底盘 Collider、Rigidbody 和两个 ROS 控制脚本；
- `Chassis`：蓝色底盘视觉模型，不承担独立碰撞；
- `LeftWheel`、`RightWheel`：左右轮视觉模型，通过 `GetWorldPose()` 跟随物理轮滚动；
- `LeftWheelCollider`、`RightWheelCollider`：实际接触地面并接受电机扭矩的物理驱动轮；
- `ForwardMarker`：橙色标志，明确机器人本地 `+Z` 前进方向；
- `LiftColumn`：黄色固定立柱，只用于显示举升结构；
- `LiftPlatform`：黄色移动平台，由 `RosLiftController` 沿本地 Y 轴控制；
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
| Root | `DifferentialRobot`，空 GameObject，Position `(0,0,0)`、Scale `(1,1,1)` |
| Visual | `Chassis`，Local Position `(0,0.32,0)` |
| Chassis Scale | `(0.70, 0.28, 0.90)` |
| 近似外形 | 宽 0.70 m、高 0.28 m、长 0.90 m |
| Material | `RobotMaterial` |
| Color | `(0.10, 0.42, 0.80)`，蓝色 |
| Mass | `40 kg` |
| Use Gravity | `true` |
| Center Of Mass | `(0,0.24,0)` |
| Linear Damping | `0.1` |
| Angular Damping | `0.5` |
| Rotation Constraints | Freeze X、Freeze Z |

根节点保持单位缩放，避免底盘的非均匀缩放影响车轮和举升平台。根节点上的 BoxCollider Center 为 `(0,0.32,0)`、Size 为 `(0.70,0.28,0.90)`，底面高于轮地接触点。X/Z 旋转冻结用于代替当前最小模型尚未加入的万向轮支撑。

#### 左右轮

| 属性 | LeftWheel | RightWheel |
|---|---|---|
| Parent | `DifferentialRobot` | `DifferentialRobot` |
| Local Position | `(-0.39, 0.22, 0)` | `(0.39, 0.22, 0)` |
| Local Rotation | `(0, 0, 90°)` | `(0, 0, 90°)` |
| Local Scale | `(0.18, 0.08, 0.18)` | `(0.18, 0.08, 0.18)` |
| Material | `WheelMaterial` | `WheelMaterial` |
| Color | `(0.04, 0.04, 0.04)` | `(0.04, 0.04, 0.04)` |
| Collider | Disabled | Disabled |

视觉轮的 Collider 保持禁用，避免与物理轮重复接触。对应的 `LeftWheelCollider` 和 `RightWheelCollider` 位于同一局部坐标，半径为 `0.18 m`，轮距为 `0.78 m`，悬架行程为 `0.05 m`。

物理参数：

| 参数 | 值 |
|---|---|
| Wheel mass | `2 kg` |
| Wheel damping rate | `0.5` |
| Suspension spring | `8000` |
| Suspension damper | `1000` |
| Forward friction stiffness | `1.5` |
| Sideways friction stiffness | `2.0` |
| Maximum motor torque | `45 N·m` |
| Holding brake torque | `80 N·m` |

#### 前向标志

| 属性 | 值 |
|---|---|
| Parent | `DifferentialRobot` |
| Local Position | `(0, 0.52, 0.36)` |
| Local Scale | `(0.22, 0.10, 0.15)` |
| Material | `ForwardMarkerMaterial` |
| Color | `(1.00, 0.55, 0.05)`，橙色 |
| Collider | Disabled |

橙色块所在方向即 Unity 本地 `+Z`，也对应 ROS 机器人坐标系的 `+x` 前方。

#### 举升机构

| 对象 | Local Position | Local Scale | Collider |
|---|---|---|---|
| `LiftColumn` | `(0,0.56,0)` | `(0.16,0.18,0.16)` | Disabled |
| `LiftPlatform` | 收回位置 `(0,0.69,0)` | `(0.62,0.08,0.72)` | Enabled |

举升参数：

| 参数 | 值 |
|---|---:|
| 最小伸长量 | `0.00 m` |
| 最大伸长量 | `0.35 m` |
| 运动速度 | `0.15 m/s` |
| 到位容差 | `0.005 m` |
| 状态发布频率 | `20 Hz` |

伸长量是相对于收回位置的局部 Y 轴位移，而不是平台的世界坐标高度。例如命令 `0.25 m` 会将平台从 Local Y `0.69` 移动到约 `0.94`。

#### 灯光与摄像机

| 对象 | 属性 | 值 |
|---|---|---|
| Directional Light | Rotation | `(45°, -30°, 0°)` |
| Directional Light | Intensity | `1.2` |
| Main Camera | Position | `(4.5, 5.0, -5.5)` |
| Main Camera | Look At | `(0, 0.35, 0)` |

### 6.7 组件与物理配置过程

机器人建模过程：

1. 创建空 GameObject 作为机器人根节点并命名为 `DifferentialRobot`；
2. 在根节点添加 BoxCollider，并设置底盘碰撞尺寸；
3. 创建 `Chassis` Cube 子对象，设置位置、缩放和蓝色材质，禁用其重复 Collider；
4. 在根节点添加 Rigidbody，并配置质量、阻尼和重力；
5. 冻结 X/Z 旋转，防止最小模型侧翻或前后翻滚；
6. 创建两个 Cylinder 作为车轮外观，将其绕 Z 轴旋转 90°并禁用 CapsuleCollider；
7. 在相同轮心位置创建 `LeftWheelCollider` 和 `RightWheelCollider`；
8. 添加 `RosDifferentialDrive`，绑定两个物理轮和两个视觉轮；
9. 配置轮半径、轮距、悬架、摩擦、最大扭矩和停车制动力；
10. 创建橙色 Cube 作为前向标志并禁用 Collider；
11. 创建黄色 `LiftColumn` 和 `LiftPlatform`；
12. 保留 LiftPlatform Collider，禁用 LiftColumn Collider；
13. 在根节点添加 `RosLiftController` 并绑定 LiftPlatform；
14. 添加固定摄像机和方向光。

当前 `RosDifferentialDrive` 不再调用 `Rigidbody.MovePosition()` 或 `MoveRotation()`。机器人位移来自左右 `WheelCollider.motorTorque`、轮地摩擦和 Rigidbody 动力学。该方案是本项目的最小物理差速模型；X/Z 旋转仍被冻结，用来代替尚未建模的万向轮和车身姿态动力学。

### 6.8 自动生成脚本的执行过程

`BuildMinimalRobotScene.BuildScene()` 按以下顺序执行：

```text
Ensure Assets/Scenes
  → NewScene
  → CreateGround
  → CreateRobot
      → Rigidbody
      → Chassis
      → LeftWheel / RightWheel
      → LeftWheelCollider / RightWheelCollider
      → RosDifferentialDrive（绑定物理轮与视觉轮）
      → ForwardMarker
      → LiftColumn / LiftPlatform
      → RosLiftController
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

如果场景中已经有举升模型或其他手工调整，不要重建场景。退出 Play Mode，执行：

```text
Warehouse Robotics > Upgrade Current Robot To Physical Wheels
```

确认 Console 出现升级成功日志后保存场景。该操作支持 Undo，并只处理名为 `DifferentialRobot` 的对象层级。

### 6.9 手动复现建模步骤

如果 Editor 脚本不可用，可在 Unity 中手动复现：

1. 新建 Empty Scene；
2. 创建 Plane，缩放为 `(2,1,2)`，命名 `Ground`；
3. 创建 Empty GameObject，命名 `DifferentialRobot`，保持单位缩放；
4. 在根节点添加 BoxCollider，Center `(0,0.32,0)`、Size `(0.70,0.28,0.90)`；
5. 创建 `Chassis` Cube 子对象，Position `(0,0.32,0)`、Scale `(0.70,0.28,0.90)`，禁用其 Collider；
6. 在根节点添加 Rigidbody，Mass 40、Center Of Mass `(0,0.24,0)`，勾选 Freeze Rotation X/Z；
7. 在根节点下创建两个 Cylinder，按照 6.6 表格设置左右位置并禁用它们的 Collider；
8. 创建两个空子对象 `LeftWheelCollider`、`RightWheelCollider`，位置与视觉轮相同，各添加半径 `0.18` 的 WheelCollider；
9. 在根节点添加 `RosDifferentialDrive`，绑定左右物理轮与视觉轮，Wheel Radius 填 `0.18`、Track Width 填 `0.78`；
10. 创建橙色 Cube 作为 ForwardMarker，禁用 Collider；
11. 创建 LiftColumn 和 LiftPlatform，并按照 6.6 表格设置参数；
12. 在根节点添加 `RosLiftController`，将 LiftPlatform 拖入引用字段；
13. 创建 Directional Light 和 Main Camera；
14. 保存为 `Assets/Scenes/MinimalRosRobot.unity`；
15. 在 Build Settings 中加入该场景；
16. 检查机器人橙色标志朝向世界 `+Z`；
17. Play 后执行第 9 节和第 17 节双向通信验证。

### 6.10 当前建模验收标准

- Scene 中能够看到地面、蓝色底盘、两只黑色轮子、橙色方向标志和黄色举升机构；
- 机器人静止时不会穿过地面或发生明显抖动；
- 正 `linear.x` 使机器人沿橙色标志方向移动；
- 正 `angular.z` 符合 ROS 左转约定；
- 左右视觉轮在直行和转向时可见旋转；
- 视觉轮 Collider 禁用，两个 WheelCollider 接地且 `Is Grounded=true`；
- 停止命令后电机扭矩归零并施加制动力；
- 目标伸长量在 `0–0.35 m` 内时，LiftPlatform 可见地上下运动；
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

### 7.2 差速逆运动学

控制器先将 `/cmd_vel` 转换为左右轮目标角速度：

```text
left_target  = (linear - angular × track_width / 2) / wheel_radius
right_target = (linear + angular × track_width / 2) / wheel_radius
```

当前 `wheel_radius=0.18 m`，`track_width=0.78 m`。例如命令 `linear.x=0.5 m/s`、`angular.z=0` 时，两侧目标角速度均约为 `2.78 rad/s`；原地左转时左轮反转、右轮正转。

### 7.3 轮速与刚体动力学

每个 `FixedUpdate()` 使用 WheelCollider 的实测 `rpm` 计算角速度，并用比例轮速控制器生成扭矩：

```text
measured_angular_speed = rpm × 2π / 60
motor_torque = clamp(
    wheel_speed_gain × (target - measured),
    -maximum_motor_torque,
    +maximum_motor_torque)
```

两个 WheelCollider 通过轮地摩擦对根节点 Rigidbody 施力。控制器仅设置 `motorTorque` 和 `brakeTorque`，不直接写机器人位姿。视觉轮使用 `WheelCollider.GetWorldPose()` 同步悬架位置和滚动角度。

### 7.4 命令超时与制动

每次收到 `/cmd_vel` 时记录 Unity 时间。若超过 0.5 秒没有新命令：

```text
linear = 0
angular = 0
```

此时两轮 `motorTorque=0`，并施加 `80 N·m` 保持制动力。因此终止 `ros2 topic pub` 后，控制器在 0.5 秒超时时刻开始制动；验收时机器人应在约 1 秒内接近静止。

### 7.5 坐标转换

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

当前 `/odom` 的 pose 和 twist 使用 Rigidbody ground truth。轮胎打滑会真实反映为车体未达到命令速度，但输出不模拟：

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

测试时同时观察两只视觉轮：直行时同向滚动，原地转向时反向滚动。按 `Ctrl+C` 停止发布；0.5 秒命令超时后应开始制动，并在约 1 秒内接近静止。

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
- `twist.twist.linear.x` 从零逐步接近直行命令，而不是瞬间跳到命令值；
- `twist.twist.angular.z` 从零逐步接近转向命令；
- 打滑、加速和制动期间，实测 twist 允许与命令存在差异。

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

2026-09-10 物理差速轮代码检查：

```text
Assembly-CSharp:        Build succeeded, 0 warnings, 0 errors
Assembly-CSharp-Editor: Build succeeded, 0 warnings, 0 errors
```

该检查证明运行脚本和 Editor 升级工具能够由 Unity 6 工程编译，但不能替代 Play Mode 下的轮地接触、转向方向和参数调优验证。

---

## 10. 日常启动与关闭

### 10.1 每次开发前

1. 启动 Docker Desktop；
2. 启动容器；
3. 检查或启动 Endpoint；
4. 打开 Unity 工程；
5. 检查 ROS Settings；
6. 打开场景并 Play；
7. 启动 `lift_command_node`；
8. 使用 `ros2 node list` 和 `ros2 topic list` 验证。

启动容器：

```powershell
docker start ros2-jazzy-unity
```

检查 Endpoint：

```bash
ros2 node list | grep UnityEndpoint
```

如果不存在，再启动 Endpoint。

升降命令节点不是容器服务，执行 `docker stop`、重启容器或结束节点进程后不会自动恢复。每次需要控制顶撑时，在独立终端启动：

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 run warehouse_lift_control lift_command_node \
  --ros-args -p target_height:=0.0
```

保持该终端运行，再从另一个已经 source 环境的容器终端执行 `ros2 param set`。启动后先确认：

```bash
ros2 node list | grep lift_command_node
```

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

### 11.8 `ros2 param set` 返回 `Node not found`

报错示例：

```text
ros2 param set /lift_command_node target_height 0.25
Node not found
```

这表示参数目标节点没有运行，不代表 Unity–ROS TCP 断开。先检查：

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 node list | grep lift_command_node
```

如果没有输出，按 10.1 或 17.3 启动 `lift_command_node`，保持启动终端运行，然后在第二个终端重新执行：

```bash
ros2 param set /lift_command_node target_height 0.25
```

成功时返回 `Set parameter successful`。若参数成功但 `/lift/state` 没有数据，检查 Unity 是否仍处于 Play；Unity 注册话题后退出或暂停 Play 时，ROS graph 可能暂时仍能看到端点，但不会产生逐帧反馈。

---

## 12. 修改与回归验证规则

以后修改通信、机器人运动、坐标系或场景时，必须至少重新验证：

1. `127.0.0.1:10000` 可连接；
2. `/cmd_vel` 有 Unity subscriber；
3. `/odom` 有 Unity publisher；
4. 正线速度使机器人沿橙色标志方向前进；
5. 正 `angular.z` 的转向与 ROS 约定一致；
6. 两个 WheelCollider 均接触地面，视觉轮滚动方向正确；
7. 停止发布 0.5 秒后进入制动且约 1 秒内接近静止；
8. `/odom` twist 来源于刚体实测速度，运动初期具有合理加速过程；
9. `/odom` 频率接近配置值；
10. Unity Console 无红色错误。

禁止在未完成上述验证时将状态标记为“已完成”。

---

## 13. 后续开发顺序

在保持当前闭环可运行的前提下，按以下顺序扩展：

1. 在当前场景执行物理轮升级并完成直行、原地旋转和制动联调；
2. 调整 WheelCollider 摩擦、悬架和轮速增益，使实测速度稳定；
3. 完成举升自由度的 Unity 运动与 ROS 反馈验证；
4. 添加载货连接和载货状态；
5. 构建简化仓库场景；
6. 添加二维雷达；
7. 添加已知地图和 empty/loaded costmap；
8. 实现 load-aware A*；
9. 实现路径跟踪；
10. 实现取货—运输—放货任务状态机。

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

### 2026-09-10 — Milestone 3 物理差速轮实现

- 将底盘从 `MovePosition`/`MoveRotation` 运动学控制改为双 `WheelCollider` 物理驱动；
- 实现 `/cmd_vel` 到左右轮目标角速度的差速逆运动学；
- 实现基于 WheelCollider `rpm` 的比例轮速扭矩控制；
- 增加 45 N·m 扭矩限幅、80 N·m 停车制动、悬架及轮地摩擦参数；
- 视觉轮通过 `GetWorldPose()` 跟随物理轮滚动；
- `/odom` twist 改为 Rigidbody 实测线速度和角速度；
- 新增 `Upgrade Current Robot To Physical Wheels` 菜单，避免覆盖已有场景；
- Unity 运行与 Editor 工程编译均通过，0 warnings、0 errors；
- Play Mode 动力学方向、接地状态和参数调优等待场景升级后验证。

### 2026-09-10 — 补充举升节点启动与 `Node not found` 排障

- 实测容器重启后 `/lift_command_node` 不会自动启动；
- 在节点缺失时复现 `ros2 param set ...` 返回 `Node not found`；
- 启动 `warehouse_lift_control/lift_command_node` 后确认节点可见；
- 确认 `target_height=0.25` 返回 `Set parameter successful`；
- 确认 `/lift/command` 与 Unity subscriber 匹配，`/lift/state`、`/lift/at_target` 与 ROS 节点 subscription 匹配；
- 将命令节点加入每日启动步骤，并补充 Unity 非 Play 时无反馈的判定方法。

### 2026-09-06 — Milestone 2 举升自由度最小闭环

- 新增 Unity `RosLiftController`；
- 新增 `/lift/command`、`/lift/state` 和 `/lift/at_target`；
- 新增 LiftColumn、LiftPlatform 和 LiftMaterial；
- 将机器人改为单位缩放空根节点与独立 Chassis 子对象；
- 将举升范围设置为 `0–0.35 m`，速度设置为 `0.15 m/s`；
- 新增 ROS 2 Python 包 `warehouse_lift_control`；
- 支持通过 `target_height` 参数在线修改举升目标；
- ROS 包在 Jazzy 容器中构建成功；
- 已验证参数设置为 `0.25 m` 后 `/lift/command` 发布 `data: 0.25`；
- 已验证 `0.50 m` 非法参数被拒绝，当前目标保持 `0.25 m`；
- Unity 模型运动和反馈值等待重建场景后进行最终联调验证。

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

---

## 17. 举升高度控制最小闭环

### 17.1 接口定义

| Topic | 类型 | 方向 | 含义 |
|---|---|---|---|
| `/lift/command` | `std_msgs/msg/Float32` | ROS 2 → Unity | 目标伸长量，单位 m |
| `/lift/state` | `std_msgs/msg/Float32` | Unity → ROS 2 | 当前伸长量，单位 m |
| `/lift/at_target` | `std_msgs/msg/Bool` | Unity → ROS 2 | 是否进入 5 mm 到位容差 |

`/lift/command` 超出 `0–0.35 m` 时，Unity 会将其限制到合法范围。ROS 节点参数回调则会拒绝非法目标值。

### 17.2 Unity 控制过程

`RosLiftController` 收到目标后，在每个 `FixedUpdate()` 中执行：

```text
current_extension = MoveTowards(
    current_extension,
    target_extension,
    lift_speed × fixed_delta_time)
```

随后更新：

```text
LiftPlatform.localPosition = retracted_position + Vector3.up × current_extension
```

控制器以约 20 Hz 发布当前伸长量和到位标志。目标命令是位置设定值，不需要像速度命令一样周期刷新或超时归零。

### 17.3 ROS 2 控制节点

源码：

```text
ros2_ws/src/warehouse_lift_control/
```

构建：

```bash
source /opt/ros/jazzy/setup.bash
cd /root/ros2_ws
colcon build --symlink-install --packages-select warehouse_lift_control
source install/setup.bash
```

启动：

```bash
ros2 run warehouse_lift_control lift_command_node \
  --ros-args -p target_height:=0.0
```

运行时升到 0.25 m：

```bash
ros2 param set /lift_command_node target_height 0.25
```

降回最低位置：

```bash
ros2 param set /lift_command_node target_height 0.0
```

节点会持续发布目标值，并同时订阅 Unity 反馈。当 `/lift/state` 进入容差且 `/lift/at_target=true` 时，日志输出：

```text
Lift reached 0.250 m (target 0.250 m)
```

### 17.4 联调验证 SOP

1. 在 Unity 等待编译完成，确认 Console 无红色错误；
2. 现有场景执行 `Warehouse Robotics > Upgrade Current Robot To Physical Wheels`；首次创建场景时才执行 `Build Minimal ROS Robot Scene`；
3. 打开重新生成的 `MinimalRosRobot.unity`；
4. 确认 Hierarchy 中包含 `LiftColumn` 和 `LiftPlatform`；
5. 点击 Play；
6. 在 ROS 2 容器启动 `lift_command_node`；
7. 设置 `target_height=0.25`；
8. 观察黄色 LiftPlatform 平滑上升；
9. 检查反馈：

```bash
ros2 topic echo /lift/state
ros2 topic echo /lift/at_target
```

10. 确认 `/lift/state` 从 0 逐步接近 0.25；
11. 确认到位后 `/lift/at_target` 为 `true`；
12. 设置 `target_height=0.0`；
13. 确认平台下降并回传 0 和 `true`。

### 17.5 验收标准

- ROS 2 能在线修改合法目标高度；
- Unity 平台高度变化清晰可见；
- 平台运动连续，不发生瞬移；
- `/lift/state` 与可视运动方向一致；
- 目标 0.25 m 的最终误差不超过 0.005 m；
- 到位后 `/lift/at_target=true`；
- 非法参数（如 0.50 m）被 ROS 节点拒绝；
- 举升过程中底盘仍可响应 `/cmd_vel`；
- Unity Console 无红色错误。

---

## 18. 物理差速轮升级与验证

### 18.1 升级当前场景

1. 退出 Play Mode；
2. 等待 Unity 脚本编译完成；
3. 执行 `Warehouse Robotics > Upgrade Current Robot To Physical Wheels`；
4. 保存场景；
5. 展开 `DifferentialRobot`，确认新增 `LeftWheelCollider` 和 `RightWheelCollider`；
6. 选中机器人，确认 `RosDifferentialDrive` 的四个轮引用均不为空；
7. 点击 Play，确认 Console 没有 `requires left and right WheelColliders` 错误。

### 18.2 直行验证

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.4}, angular: {z: 0.0}}"
```

验收：左右轮同向滚动，机器人沿橙色标志方向前进；`/odom` 的 `twist.twist.linear.x` 从零逐渐接近 `0.4`，允许因物理阻力存在小偏差。

### 18.3 原地左转验证

```bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.0}, angular: {z: 0.8}}"
```

验收：左轮反转、右轮正转，机器人按 ROS 正 `angular.z` 原地左转，`/odom` 的 `twist.twist.angular.z` 为正。

### 18.4 制动与接地验证

停止 publisher 后确认：

- 0.5 秒后进入超时制动；
- 机器人约 1 秒内接近静止；
- 车身不穿过地面且没有持续高频抖动；
- 运行中查看两个 WheelCollider 的 `Is Grounded` 均为 true。

若轮子空转但机器人不移动，先检查 WheelCollider 是否接地以及 Ground 是否保留 Collider；若转向方向相反，先核对左右轮引用是否互换，再检查第 7.5 节坐标约定。只有完成以上 Play Mode 验证后，才能将 Milestone 3 标记为已完成。
