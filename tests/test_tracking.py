import math
import unittest
from warehouse_planning.tracking import Follower, map_pose, wrap


class TrackingTests(unittest.TestCase):
    def test_map_transform(self):
        x,y,a=map_pose((2,1,.2),(3,4,math.pi/2))
        self.assertAlmostEqual(x,2)
        self.assertAlmostEqual(y,6)
        self.assertAlmostEqual(a,math.pi/2+.2)

    def test_kinematic_forward_turn_reverse(self):
        segments=[dict(action='forward',end=[1,0,0]),
                  dict(action='turn_left',end=[1,0,math.pi/2]),
                  dict(action='reverse',end=[1,-1,math.pi/2])]
        follower=Follower(segments)
        pose=[0.,0.,0.]
        for _ in range(5000):
            v,w,done=follower.step(pose)
            if done:break
            pose[0]+=v*math.cos(pose[2])*.05
            pose[1]+=v*math.sin(pose[2])*.05
            pose[2]=wrap(pose[2]+w*.05)
        self.assertTrue(done)
        self.assertLess(math.dist(pose[:2],[1,-1]),.025)

    def test_deviation_stops(self):
        follower=Follower([dict(action='forward',end=[1,0,0])])
        with self.assertRaisesRegex(ValueError,'TRACKING_DEVIATION'):
            follower.step([0,.1,0])


if __name__=='__main__':unittest.main()
