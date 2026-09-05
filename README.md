# Load-Aware Warehouse Robot

Unity–ROS 2 warehouse robotics demonstrator. The first milestone is a minimal
ROS-controlled differential-drive robot.

Internal setup, implementation, verification, and troubleshooting procedures:
[docs/INTERNAL_SOP.md](docs/INTERNAL_SOP.md).

## Current milestone: Unity ↔ ROS 2 smoke test

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
5. Select `Warehouse Robotics > Build Minimal ROS Robot Scene`.
6. Open `Assets/Scenes/MinimalRosRobot.unity` and press Play.

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

Stopping the `/cmd_vel` publisher should stop the robot within 0.5 seconds.
