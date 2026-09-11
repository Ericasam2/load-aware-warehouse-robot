# Load-Aware Warehouse Robot

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

## Current milestone: physical differential-drive integration

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
