import json
import math
import unittest
from pathlib import Path
import numpy as np
from warehouse_planning.grid import Grid,build_mode,scene_obstacles
from warehouse_planning.astar import plan

ROOT=Path(__file__).resolve().parents[1]


def overlap(pose,layer,solid):
    """Independent scalar corner-projection SAT oracle for continuous pose validation."""
    if solid["max"][2]<=layer["bottom"] or solid["min"][2]>=layer["top"]:return False
    x,y,a=pose;c,s=math.cos(a),math.sin(a)
    robot=[(x+c*u-s*v,y+s*u+c*v) for u in (-layer["length"]/2,layer["length"]/2) for v in (-layer["width"]/2,layer["width"]/2)]
    box=[(u,v) for u in (solid["min"][0],solid["max"][0]) for v in (solid["min"][1],solid["max"][1])]
    for ax,ay in ((1,0),(0,1),(c,s),(-s,c)):
        pr=[px*ax+py*ay for px,py in robot];pb=[px*ax+py*ay for px,py in box]
        if max(pr)<=min(pb) or max(pb)<=min(pr):return False
    return True


class GeometryTests(unittest.TestCase):
    def test_half_open_grid_and_roundtrip(self):
        g=Grid([-1,-2,1,2],.1)
        for c,r in ((0,0),(19,39),(10,15)):self.assertEqual(g.cell(*g.world(c,r)),(c,r))
        for p in ((1,0),(0,2),(-1.01,0),(float('nan'),0)):
            with self.assertRaises(ValueError):g.cell(*p)

    def test_height_and_orientation_change_collision(self):
        g=Grid([-2,-2,2,2],.025)
        s=[{"min":[-.1,-.5,.8],"max":[.1,.5,1.0]}]
        low={"layers":[{"length":.8,"width":.3,"bottom":.02,"top":.7}]}
        high={"layers":[dict(low["layers"][0],top=1.1)]}
        lo,_=build_mode(g,s,low);hi,_=build_mode(g,s,high)
        c,r=g.cell(.38,0)
        self.assertFalse(lo[0,r,c]);self.assertTrue(hi[0,r,c]);self.assertFalse(hi[2,r,c])

    def test_corner_cutting_and_invalid_goals(self):
        g=Grid([0,0,3,3],1)
        b=np.zeros((8,3,3),dtype=bool);b[:,:,1]=True;b[:,1,:]=True
        with self.assertRaisesRegex(ValueError,"unreachable"):
            plan(g,b,np.ones((3,3),dtype=bool),[.5,.5,math.pi/4],[2.5,2.5,math.pi/4])
        with self.assertRaisesRegex(ValueError,"blocked"):
            plan(g,b,np.zeros((3,3),dtype=bool),[.5,.5,0],[1.5,1.5,0])


class ActualSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scene=json.loads((ROOT/"maps/scene_geometry.json").read_text(encoding="utf-8-sig"))
        cls.config=json.loads((ROOT/"config/planning.json").read_text())
        cls.grid=Grid(cls.scene["bounds"],cls.config["resolution"])
        cls.arrays=np.load(ROOT/"maps/generated/planning_grids.npz")
        cls.paths=json.loads((ROOT/"maps/generated/demo_paths.json").read_text())

    def test_payload_profiles_and_obstacle_override(self):
        original=scene_obstacles(self.scene)
        carrying=scene_obstacles(self.scene,"carrying")
        self.assertTrue(any(s["kind"]=="pickup_payload" for s in original))
        self.assertFalse(any(s["kind"]=="pickup_payload" for s in carrying))
        self.assertEqual({s["id"] for s in original if s["kind"]!="pickup_payload"},{s["id"] for s in carrying})
        delivered=scene_obstacles(self.scene,"delivered")
        a=next(s for s in original if s["kind"]=="pickup_payload")
        b=next(s for s in delivered if s["id"]==a["id"])
        self.assertAlmostEqual(b["min"][1]-a["min"][1],-5)
        with self.assertRaises(ValueError):scene_obstacles(self.scene,overrides={"disabled_ids":["typo"]})

    def test_low_and_high_clearance_and_docking_rotation(self):
        c,r=self.grid.cell(0,5)
        self.assertFalse(self.arrays["empty"][0,r,c])
        self.assertTrue(self.arrays["raised_empty"][0,r,c])
        self.assertTrue(self.arrays["loaded"][0,r,c])
        for x in np.linspace(-1,5,61):
            c,r=self.grid.cell(x,-5);self.assertFalse(self.arrays["loaded"][0,r,c])
        c,r=self.grid.cell(2,5)
        self.assertFalse(self.arrays["loaded"][6,r,c])
        self.assertTrue(self.arrays["loaded_rotation_blocked"][r,c])

    def test_temporary_block_changes_map(self):
        override=json.loads((ROOT/"config/temporary_high_block.json").read_text())
        b,_=build_mode(self.grid,scene_obstacles(self.scene,"carrying",override),self.config["modes"]["loaded"])
        c,r=self.grid.cell(2,-5)
        self.assertFalse(self.arrays["loaded"][0,r,c]);self.assertTrue(b[0,r,c])

    def test_paths_between_cells_and_during_turns_are_collision_free(self):
        self.assertEqual(len(self.paths),4)
        for path in self.paths.values():
            mode=self.config["modes"][path["mode"]]
            solids=scene_obstacles(self.scene,mode["scene_profile"])
            for a,b in zip(path["poses"],path["poses"][1:]):
                da=(b[2]-a[2]+math.pi)%math.tau-math.pi
                for t in np.linspace(0,1,5):
                    p=(a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),a[2]+t*da)
                    self.assertFalse(any(overlap(p,layer,s) for layer in mode["layers"] for s in solids),str(p))

    def test_pgm_row_flip_matches_numpy(self):
        data=(ROOT/"maps/generated/occupancy.pgm").read_bytes().split(b'\n',3)[3]
        image=np.frombuffer(data,dtype=np.uint8).reshape(self.grid.height,self.grid.width)
        np.testing.assert_array_equal(image==0,self.arrays["occupancy"][::-1])


if __name__=="__main__":unittest.main()
