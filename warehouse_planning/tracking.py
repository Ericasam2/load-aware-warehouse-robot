"""ROS-independent, stop/turn/drive segment follower for simulation."""
import math


def wrap(a):
    return (a + math.pi) % math.tau - math.pi


def map_pose(odom, transform):
    x, y, a = transform
    c, s = math.cos(a), math.sin(a)
    return (x+c*odom[0]-s*odom[1], y+s*odom[0]+c*odom[1], wrap(a+odom[2]))


class Follower:
    def __init__(self, segments):
        self.segments = segments
        self.index = 0

    def step(self, pose):
        if self.index >= len(self.segments):
            return 0., 0., True
        segment = self.segments[self.index]
        x, y, yaw = pose
        ex, ey, heading = segment['end']
        error = wrap(heading-yaw)
        if segment['action'].startswith('turn'):
            if math.hypot(x-ex, y-ey) > .06:
                raise ValueError('TURN_POSITION_DRIFT')
            if abs(error) < .012:
                self.index += 1
                return 0., 0., False
            return 0., max(-.25, min(.25, 1.5*error)), False
        sign = 1 if segment['action'] == 'forward' else -1
        c, s = math.cos(heading), math.sin(heading)
        remaining = sign*((ex-x)*c+(ey-y)*s)
        lateral = -(ex-x)*s+(ey-y)*c
        if abs(lateral) > .045 or abs(error) > .15:
            raise ValueError('TRACKING_DEVIATION')
        if abs(remaining) < .012 and abs(lateral) < .025:
            self.index += 1
            return 0., 0., False
        if remaining < -.02:
            raise ValueError('ENDPOINT_OVERSHOOT')
        v = sign * min(.18, max(0., .8*remaining))
        w = max(-.18, min(.18, 2.*error+sign*2.*lateral))
        return v, w, False
