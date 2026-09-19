import math
import unittest
import numpy as np
from warehouse_planning.astar import plan
from warehouse_planning.grid import Grid
from warehouse_planning.animation import motion_frames


class AnimationTests(unittest.TestCase):
    def test_trace_does_not_change_path(self):
        grid=Grid([0,0,3,3],1)
        blocked=np.zeros((8,3,3),bool)
        rotation=np.zeros((3,3),bool)
        args=(grid,blocked,rotation,[.5,.5,0],[2.5,2.5,math.pi/2])
        plain=plan(*args)
        events=[]
        traced=plan(*args,on_expand=lambda *event:events.append(event))
        self.assertEqual(plain['states'],traced['states'])
        self.assertEqual(len(events),traced['expansions'])
        self.assertEqual([e[3] for e in events],list(range(1,len(events)+1)))

    def test_turn_replay_uses_short_rotation_and_no_translation(self):
        a=[1,2,7*math.pi/4];b=[1,2,0]
        poses=motion_frames([dict(start=a,end=b)],a)
        self.assertTrue(all(p[:2]==[1,2] for p in poses))
        self.assertAlmostEqual(poses[-1][2],math.tau)
        self.assertTrue(all(0 <= q[2]-p[2] <= .101 for p,q in zip(poses,poses[1:])))
