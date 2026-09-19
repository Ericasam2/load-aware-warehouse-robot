# Load-Aware Warehouse Robot

Pure Python animated simulation (no Unity/ROS): run
`python -m warehouse_planning.animation --show`, adding `--scenario detour` for the
loaded obstacle scenario. Includes search replay, robot animation and GIF export.
See [Python simulation guide](docs/PYTHON_SIMULATION.md).

ROS–Unity closed-loop A* test: run `tools/Run-RosUnityTest.ps1 -PrepareOnly`,
open `WarehouseEnvironment` in Unity and press Play, then run
`tools/Run-RosUnityTest.ps1`. See the [joint test SOP](docs/ROS_UNITY_TEST.md).
The empty start-to-P1 route has passed a ROS 2 + Unity WheelCollider physics run.

Run `tools/Run-AStar.ps1` to plan to pickup, or `tools/Run-AStar.ps1 -Verify`
for the warehouse scenario suite. The planner supports heading-aware forward,
reverse and turn actions, obstacle replanning and independent collision checks.
See [A* planner and results](docs/ASTAR_PLANNER.md).

Height- and heading-aware A* simulation maps are available in `maps/generated`.
They are exported from the saved Unity warehouse colliders, with robot modes,
obstacles, pickup/drop-off poses and a reference planner. Run
`tools/Build-PlanningMap.ps1 -RunTests`; see [planning map usage](docs/PLANNING_MAP.md).

Unity–ROS 2 warehouse robotics demonstrator with a ROS-controlled lift and a
two-wheel physical differential-drive base.

Warehouse environment: open `Assets/Scenes/WarehouseEnvironment.unity` in Unity.
It contains two under-rack pickup/drop-off passages with low entrances and side
transfer openings, a 2.4 m high loaded through-rack passage, a movable obstacle,
and the existing ROS robot. Rebuild with
`Warehouse Robotics > Build Warehouse Environment`.
See [warehouse layout, coordinates and limitations](docs/WAREHOUSE_ENVIRONMENT.md).

P1/P2 use [static open-center conveyor lifts](docs/STATIC_CONVEYOR.md): twin
support tracks leave a continuous slot for robot access, lift lowering and exit.

The robot now has correctly sized drive wheels with rotation markers, a layered
chassis, and twin telescoping lift columns that follow the existing platform.
See [functional robot model and validation](docs/ROBOT_MODEL.md).

Internal setup, implementation, verification, and troubleshooting procedures:
[docs/INTERNAL_SOP.md](docs/INTERNAL_SOP.md).

## Current milestone: load-aware planning and ROS–Unity path execution

As of 2026-09-19, the Unity warehouse, physical differential-drive base,
ROS-controlled lift, height/heading-aware planning maps and load-aware A* are
implemented. The empty `RobotStart → Pickup_P1` route has also completed a
closed-loop ROS 2 + Unity WheelCollider run. The remaining MVP work is dynamic
payload attach/detach, loaded P1 → P2 execution, mission orchestration and lidar
stop/replanning.

### ROS side

The project uses ROS 2 Jazzy in Docker. The development workspace is mounted at
`/root/ros2_ws`.

Start the prepared container and endpoint from PowerShell:

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
& $docker start ros2-jazzy-unity
& $docker exec -d ros2-jazzy-unity bash -lc `
  'source /opt/ros/jazzy/setup.bash && source /root/ros2_ws/install/setup.bash && exec ros2 run ros_tcp_endpoint default_server_endpoint --ros-args -p ROS_IP:=0.0.0.0'
```

The endpoint is exposed to Windows at `127.0.0.1:10000`.

### Unity side

1. Open `unity_project` using Unity `6000.6.0f1`.
2. Wait for Package Manager and script compilation to finish.
3. Open `Robotics > ROS Settings`.
4. Set the protocol to `ROS2`, IP to `127.0.0.1`, and port to `10000`.
5. For a new scene, select `Warehouse Robotics > Build Minimal ROS Robot Scene`.
   For the existing lift scene, select
   `Warehouse Robotics > Upgrade Current Robot To Physical Wheels` and save it.
6. Open `Assets/Scenes/MinimalRosRobot.unity` and press Play.

The drive controller converts `/cmd_vel` into left/right wheel angular-speed
targets and applies torque through two Unity `WheelCollider` components. Robot
motion therefore comes from wheel contact and Rigidbody physics; `/odom` reports
the measured Rigidbody velocity rather than echoing the command.

Measured wheel position and angular velocity are published at approximately
20 Hz using the standard `sensor_msgs/msg/JointState` interface:

```bash
ros2 topic echo /joint_states
ros2 topic echo /joint_states --field velocity
```

The `effort` array is intentionally empty, and simulated slip/contact values are
not published as robot sensor feedback.

### Send a velocity command

Open a shell in the container:

```powershell
$docker = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\bin\docker.exe"
& $docker exec -it ros2-jazzy-unity bash
```

Then run:

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 topic pub --rate 10 /cmd_vel geometry_msgs/msg/Twist \
  "{linear: {x: 0.4}, angular: {z: 0.3}}"
```

In another container shell, verify odometry:

```bash
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
ros2 topic echo /odom
```

Stopping the `/cmd_vel` publisher triggers braking after the 0.5-second command
timeout; the robot should be nearly stationary within about one second.

## Lift position loop

The lift uses a bounded position command (`0.00–0.35 m`) and returns measured
extension plus an at-target flag.

Build and run the ROS 2 node:

```bash
source /opt/ros/jazzy/setup.bash
cd /root/ros2_ws
colcon build --symlink-install --packages-select warehouse_lift_control
source install/setup.bash
ros2 run warehouse_lift_control lift_command_node \
  --ros-args -p target_height:=0.0
```

Change the target while the node is running:

```bash
ros2 param set /lift_command_node target_height 0.25
ros2 topic echo /lift/state
ros2 topic echo /lift/at_target
```

Re-run `Warehouse Robotics > Build Minimal ROS Robot Scene` after pulling this
milestone so the generated scene contains `LiftColumn` and `LiftPlatform`.
