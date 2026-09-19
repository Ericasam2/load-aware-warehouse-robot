import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
from warehouse_planning.grid import Grid
from warehouse_planning.astar import plan,PlanningError,SearchBudgetExceeded
from warehouse_planning.planner import save_result


class AStarTests(unittest.TestCase):
    def test_astar_matches_dijkstra_on_random_graphs(self):
        g=Grid([0,0,2,2],.25)
        for seed in range(12):
            rng=np.random.default_rng(seed)
            b=np.repeat((rng.random((8,8))<.16)[None,:,:],8,axis=0)
            b[:,0,0]=False;b[:,7,7]=False
            r=rng.random((8,8))<.2;r[0,0]=False;r[7,7]=False
            outcomes=[]
            for heuristic in (True,False):
                try:outcomes.append(plan(g,b,r,[.125,.125,0],[1.875,1.875,math.pi/2],use_heuristic=heuristic))
                except PlanningError as exc:outcomes.append(exc.code)
            if isinstance(outcomes[0],str):self.assertEqual(outcomes[0],outcomes[1])
            else:
                self.assertIsInstance(outcomes[1],dict)
                self.assertAlmostEqual(outcomes[0]['cost'],outcomes[1]['cost'],places=10)

    def test_reverse_segments_and_cost(self):
        g=Grid([0,0,5,3],1)
        b=np.zeros((8,3,5),bool);r=np.ones((3,5),bool)
        result=plan(g,b,r,[3.5,1.5,0],[.5,1.5,0])
        self.assertEqual(result['length_m'],3)
        self.assertEqual(result['reverse_length_m'],3)
        self.assertAlmostEqual(result['cost'],3.3)
        self.assertEqual(len(result['segments']),1)
        self.assertEqual(result['segments'][0]['action'],'reverse')

    def test_turn_only_and_no_motion(self):
        g=Grid([0,0,3,3],1);b=np.zeros((8,3,3),bool);r=np.zeros((3,3),bool)
        result=plan(g,b,r,[1.5,1.5,0],[1.5,1.5,math.pi/2])
        self.assertEqual(result['turn_steps'],2);self.assertEqual(result['length_m'],0)
        self.assertEqual([s['action'] for s in result['segments']],['turn_left','turn_left'])
        same=plan(g,b,r,[1.5,1.5,0],[1.5,1.5,0])
        self.assertEqual(len(same['poses']),1);self.assertEqual(same['segments'],[])

    def test_budget_and_bad_inputs_are_distinct(self):
        g=Grid([0,0,3,3],1);b=np.zeros((8,3,3),bool);r=np.zeros((3,3),bool)
        with self.assertRaises(SearchBudgetExceeded):plan(g,b,r,[.5,.5,0],[2.5,2.5,0],max_expansions=0)
        for kwargs,code in (({'reverse_multiplier':.5},'INVALID_COST'),({'turn_cost':0},'INVALID_COST')):
            with self.assertRaises(PlanningError) as cm:plan(g,b,r,[.5,.5,0],[2.5,2.5,0],**kwargs)
            self.assertEqual(cm.exception.code,code)
        with self.assertRaises(PlanningError) as cm:plan(g,b,r,[.5,.5,0],[2.5,2.5,.1])
        self.assertEqual(cm.exception.code,'UNSUPPORTED_HEADING')
        with self.assertRaises(PlanningError) as cm:plan(g,b.astype(float),r,[.5,.5,0],[2.5,2.5,0])
        self.assertEqual(cm.exception.code,'INVALID_MAP')

    def test_failed_replan_clears_stale_csv(self):
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);(directory/'path.csv').write_text('old usable path')
            save_result(directory,'path',{'status':'UNREACHABLE','poses':[],'segments':[]})
            self.assertEqual(len((directory/'path.csv').read_text().splitlines()),1)


if __name__=='__main__':unittest.main()
