#!/usr/bin/env bash
set -e
source /opt/ros/jazzy/setup.bash
cd /tmp/warehouse-astar
exec python3 -m warehouse_planning.ros_runner
