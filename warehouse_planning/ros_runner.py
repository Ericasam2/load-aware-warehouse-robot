"""Run inside ROS 2: python3 -m warehouse_planning.ros_runner.

Only the empty RobotStart -> Pickup_P1 scenario is enabled until payload
attachment and scenario reset protocols exist in Unity.
"""
import csv
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, PoseStamped
from nav_msgs.msg import Odometry, Path as PathMsg
from std_msgs.msg import Float32, String
from rclpy.qos import QoSProfile, DurabilityPolicy
from rclpy.signals import SignalHandlerOptions

from .planner import Planner, save_result
from .tracking import Follower, map_pose, wrap
from .validation import collides


class Runner(Node):
    def __init__(self):
        super().__init__('warehouse_astar_test')
        self.out = Path('outputs/ros_unity')
        self.out.mkdir(parents=True, exist_ok=True)
        self.status = 'WAITING_FOR_UNITY'
        self.started = time.monotonic()
        self.pose = None
        self.last_odom = self.last_lift = -math.inf
        self.lift = None
        self.context_ok = False
        self.speed = math.inf
        self.previous_stamp = None
        self.settled_since = None
        self.samples = []
        self.progress_pose = None
        self.progress_time = self.started
        self.last_log = self.started
        self.hold_until = 0.
        self.planner = Planner()
        self.result = self.planner.run('empty', 'RobotStart', 'Pickup_P1')
        save_result(self.out, 'planned_path', self.result)
        if self.result['status'] != 'SUCCESS':
            raise ValueError('Planning failed')
        self.follower = Follower(self.result['segments'])
        _, _, self.solids = self.planner.maps('empty')
        self.layers = self.planner.config['modes']['empty']['layers']
        self.cmd = self.create_publisher(Twist, '/cmd_vel', 10)
        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.path_pub = self.create_publisher(PathMsg, '/planned_path', qos)
        self.create_subscription(Odometry, '/odom', self.on_odom, 10)
        self.create_subscription(Float32, '/lift/state', self.on_lift, 10)
        self.create_subscription(String, '/warehouse/test_context', self.on_context, 10)
        path = PathMsg()
        path.header.frame_id = 'map'
        path.header.stamp = self.get_clock().now().to_msg()
        for x, y, a in self.result['poses']:
            p = PoseStamped()
            p.header = path.header
            p.pose.position.x, p.pose.position.y = x, y
            p.pose.orientation.z, p.pose.orientation.w = math.sin(a/2), math.cos(a/2)
            path.poses.append(p)
        self.path_message = path
        self.path_pub.publish(path)
        self.timer = self.create_timer(.05, self.tick)
        self.get_logger().info('Waiting for WarehouseEnvironment Play mode at RobotStart; lift must be retracted.')
        self.write_report()

    def write_report(self):
        goal = self.result['poses'][-1]
        report = dict(status=self.status, passed=self.status == 'SUCCESS',
                      recorded_at_utc=datetime.now(timezone.utc).isoformat(),
                      elapsed_s=time.monotonic()-self.started, samples=len(self.samples),
                      final_map_pose=self.pose, goal=goal,
                      position_error_m=None if self.pose is None else math.dist(self.pose[:2], goal[:2]),
                      yaw_error_rad=None if self.pose is None else abs(wrap(self.pose[2]-goal[2])),
                      verification='ROS odometry feedback; sampled footprint checks, not contact-sensor proof')
        (self.out/'run_report.json').write_text(json.dumps(report, indent=2))
        with (self.out/'actual_trajectory.csv').open('w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['elapsed_s','map_x','map_y','yaw','linear_cmd','angular_cmd','segment'])
            w.writerows(self.samples)

    def finish(self, status):
        self.status = status
        self.cmd.publish(Twist())
        self.write_report()
        self.get_logger().info(status)

    def on_lift(self, msg):
        self.lift = msg.data
        self.last_lift = time.monotonic()

    def on_context(self, msg):
        if self.status not in ('WAITING_FOR_UNITY','RUNNING'): return
        try:
            context = json.loads(msg.data)
            origin = context['map_from_odom']
            expected = self.planner.meta['map_from_odom']
            self.context_ok = (context['scene'] == 'WarehouseEnvironment' and len(origin) == 3
                and all(math.isfinite(v) for v in origin)
                and math.dist(origin[:2], expected[:2]) < .01
                and abs(wrap(origin[2]-expected[2])) < .001)
        except (ValueError, KeyError, TypeError):
            self.context_ok = False
        if not self.context_ok: self.finish('WRONG_UNITY_SCENE_OR_ORIGIN')
        else: self.path_pub.publish(self.path_message)

    def on_odom(self, msg):
        if self.status not in ('WAITING_FOR_UNITY','RUNNING'): return
        if msg.header.frame_id != 'odom':
            self.finish('INVALID_ODOM_FRAME')
            return
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec*1e-9
        if self.previous_stamp is not None and stamp <= self.previous_stamp:
            self.finish('ODOM_CLOCK_RESET')
            return
        self.previous_stamp = stamp
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        values = (p.x,p.y,q.x,q.y,q.z,q.w)
        if not all(math.isfinite(v) for v in values) or abs(sum(v*v for v in values[2:])-1) > .05:
            self.finish('INVALID_ODOM')
            return
        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
        self.pose = map_pose((p.x,p.y,yaw), self.planner.meta['map_from_odom'])
        self.speed = max(abs(msg.twist.twist.linear.x), abs(msg.twist.twist.angular.z))
        self.last_odom = time.monotonic()

    def tick(self):
        now = time.monotonic()
        if self.status not in ('WAITING_FOR_UNITY','RUNNING'):
            self.cmd.publish(Twist())
            return
        if now-self.started > 240:
            self.finish('RUN_TIMEOUT')
            return
        if now-self.last_odom > .5 or now-self.last_lift > 1. or not self.context_ok:
            self.cmd.publish(Twist())
            if self.status == 'RUNNING': self.finish('FEEDBACK_TIMEOUT')
            elif now-self.started > 60: self.finish('UNITY_NOT_READY')
            return
        if not math.isfinite(self.lift) or abs(self.lift) > .005:
            self.finish('LIFT_NOT_RETRACTED')
            return
        if self.status == 'WAITING_FOR_UNITY':
            initial = self.planner.resolve('RobotStart')
            if math.dist(self.pose[:2],initial[:2]) > .04 or abs(wrap(self.pose[2]-initial[2])) > .025:
                self.finish('RESET_UNITY_TO_ROBOT_START')
                return
            if self.count_publishers('/cmd_vel') > 1:
                self.finish('MULTIPLE_VELOCITY_PUBLISHERS')
                return
            self.status = 'RUNNING'
        for layer in self.layers:
            if any(collides(self.pose,layer,solid,.005) for solid in self.solids):
                self.finish('FOOTPRINT_CLEARANCE_VIOLATION')
                return
        if now < self.hold_until or (self.hold_until and self.speed > .01):
            self.cmd.publish(Twist())
            self.samples.append([now-self.started,*self.pose,0.,0.,self.follower.index])
            if now-self.hold_until > 5: self.finish('FAILED_TO_STOP')
            return
        self.hold_until = 0.
        old_index = self.follower.index
        try:
            v,w,done = self.follower.step(self.pose)
        except ValueError as exc:
            self.finish(str(exc))
            return
        if self.follower.index != old_index:
            self.hold_until = now + .6
        self.samples.append([now-self.started,*self.pose,v,w,self.follower.index])
        if self.progress_pose is None or math.dist(self.pose[:2],self.progress_pose[:2]) > .01 or abs(wrap(self.pose[2]-self.progress_pose[2])) > .02:
            self.progress_pose = self.pose
            self.progress_time = now
        elif not done and now-self.progress_time > 12:
            self.finish('ROBOT_NOT_MOVING')
            return
        if now-self.last_log > 5:
            self.last_log = now
            self.get_logger().info(f'segment={self.follower.index} map=({self.pose[0]:.3f},{self.pose[1]:.3f},{self.pose[2]:.3f})')
        command = Twist()
        command.linear.x,command.angular.z = v,w
        self.cmd.publish(command)
        if done:
            goal = self.result['poses'][-1]
            if math.dist(self.pose[:2],goal[:2]) > .035 or abs(wrap(self.pose[2]-goal[2])) > .025:
                self.finish('FINAL_POSE_DRIFT')
                return
            if not math.isfinite(self.speed) or self.speed > .01:
                self.settled_since = None
                return
            if self.settled_since is None: self.settled_since = now
            if now-self.settled_since > 1.: self.finish('SUCCESS')


def main():
    out = Path('outputs/ros_unity')
    out.mkdir(parents=True, exist_ok=True)
    (out/'run_report.json').write_text(json.dumps(dict(status='INITIALIZING', passed=False)))
    # Keep the ROS context alive until the finally block has sent stop commands.
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = None
    try:
        node = Runner()
        while rclpy.ok() and node.status in ('WAITING_FOR_UNITY','RUNNING'):
            rclpy.spin_once(node, timeout_sec=.1)
    except KeyboardInterrupt:
        if node: node.finish('INTERRUPTED')
    except Exception as exc:
        if node: node.finish('RUNTIME_ERROR')
        else: (out/'run_report.json').write_text(json.dumps(dict(status='INITIALIZATION_FAILED', passed=False, message=str(exc))))
        raise
    finally:
        if node:
            for _ in range(5):
                node.cmd.publish(Twist())
                time.sleep(.05)
            node.write_report()
            node.destroy_node()
        rclpy.shutdown()
    if node is None or node.status != 'SUCCESS': raise SystemExit(2)


if __name__ == '__main__':
    main()
