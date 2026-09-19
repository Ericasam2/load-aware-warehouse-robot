#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash
exec ros2 run ros_tcp_endpoint default_server_endpoint --ros-args -p ROS_IP:=0.0.0.0 > /tmp/warehouse-endpoint.log 2>&1
