"""Runnable named-goal planning and reproducible warehouse scenario validation."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .astar import plan, PlanningError, SearchBudgetExceeded
from .grid import Grid,build_mode,scene_obstacles
from .validation import validate_path
from .__main__ import ROOT,write_json,preview


class Planner:
    def __init__(self):
        self.scene=json.loads((ROOT/"maps/scene_geometry.json").read_text(encoding="utf-8-sig"))
        self.config=json.loads((ROOT/"config/planning.json").read_text())
        self.meta=json.loads((ROOT/"maps/generated/metadata.json").read_text())
        scene_file=ROOT/"unity_project"/self.scene["scene_path"]
        if (hashlib.sha256(scene_file.read_bytes()).hexdigest()!=self.meta["source_scene_sha256"] or
            self.scene["scene_sha256"]!=self.meta["source_scene_sha256"] or
            hashlib.sha256((ROOT/"config/planning.json").read_bytes()).hexdigest()!=self.meta["config_sha256"]):
            raise ValueError("Stale maps: re-export the scene and run python -m warehouse_planning")
        if self.meta["overrides"]:raise ValueError("Base maps must not contain scenario overrides")
        self.goals=json.loads((ROOT/"maps/generated/goals.json").read_text())
        self.grid=Grid(self.scene["bounds"],self.meta["resolution"])
        self.arrays=np.load(ROOT/"maps/generated/planning_grids.npz")

    def resolve(self,value):
        if not isinstance(value,str):return value
        if value in self.goals:return self.goals[value]
        try:pose=[float(v) for v in value.split(',')]
        except ValueError as exc:raise ValueError("Unknown goal name or invalid x,y,yaw: "+value) from exc
        if len(pose)!=3:raise ValueError("Expected goal name or x,y,yaw radians")
        return pose

    def maps(self,mode,overrides=None):
        definition=self.config["modes"][mode]
        solids=scene_obstacles(self.scene,definition["scene_profile"],overrides)
        if overrides is None:return self.arrays[mode],self.arrays[mode+"_rotation_blocked"],solids
        b,r=build_mode(self.grid,solids,definition,self.config["safety_margin"])
        if self.config["docking"]["forbid_rotation_in_slot"]:
            for marker in ("Pickup_P1","Dropoff_P2"):
                x,y=self.goals[marker][:2]
                r |= ((np.abs(self.grid.x[None,:]-x)<=self.config["docking"]["slot_width"]/2+self.grid.resolution/2) &
                      (np.abs(self.grid.y[:,None]-y)<=self.config["docking"]["track_length"]/2+self.grid.resolution/2))
        return b,r,solids

    def run(self,mode,start,goal,overrides=None,max_expansions=1500000):
        b,r,solids=self.maps(mode,overrides)
        start,goal=self.resolve(start),self.resolve(goal)
        try:
            result=plan(self.grid,b,r,start,goal,max_expansions=max_expansions)
        except (PlanningError,SearchBudgetExceeded) as exc:
            return {"status":exc.code,"message":str(exc),"mode":mode,"requested_start":start,"requested_goal":goal,"poses":[],"segments":[]}
        result.update(mode=mode,frame="map",requested_start=start,requested_goal=goal,
                      scene_profile=self.config["modes"][mode]["scene_profile"],overrides=overrides,
                      source_scene_sha256=self.scene["scene_sha256"])
        result["verification"]=validate_path(result,self.grid,b,r,self.config["modes"][mode],solids,self.config["safety_margin"])
        return result


def save_result(out,name,result):
    write_json(out/(name+".json"),result)
    # Always truncate a previous CSV on failure, so a failed replan cannot leave a stale usable path.
    with (out/(name+".csv")).open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(["map_x","map_y","yaw_rad","qz","qw"])
        for x,y,a in result["poses"]:w.writerow([x,y,a,math.sin(a/2),math.cos(a/2)])


def suite(planner,out):
    barrier=json.loads((ROOT/"config/temporary_high_block.json").read_text())
    # Enclose the start (not the goal), producing a small exhaustible disconnected component.
    cage={"additional":[{"id":"cage/"+str(i),"name":"CageWall","kind":"temporary","min":lo+[0],"max":hi+[3]}
        for i,(lo,hi) in enumerate([([-2.4,-6.4],[-2.3,-3.6]),([.3,-6.4],[.4,-3.6]),
                                   ([-2.4,-6.4],[.4,-6.3]),([-2.4,-3.7],[.4,-3.6])])]}
    cases=[
        ("start_to_pickup","empty","RobotStart","Pickup_P1",None,"SUCCESS"),
        ("pickup_to_dropoff","loaded","Pickup_P1","Dropoff_P2",None,"SUCCESS"),
        ("empty_low_passage","empty",[-1,5,0],[5,5,0],None,"SUCCESS"),
        ("loaded_high_passage","loaded",[-1,-5,0],[5,-5,0],None,"SUCCESS"),
        ("raised_high_passage","raised_empty",[-1,-5,0],[5,-5,0],None,"SUCCESS"),
        ("loaded_detour","loaded",[-1,-5,0],[5,-5,0],barrier,"SUCCESS"),
        ("unreachable","loaded",[-1,-5,0],[5,-5,0],cage,"UNREACHABLE"),
        ("blocked_goal","empty","RobotStart",[7,-8,0],None,"GOAL_BLOCKED"),
        ("outside_goal","empty","RobotStart",[10,0,0],None,"OUT_OF_BOUNDS"),
        ("same_pose","empty","RobotStart","RobotStart",None,"SUCCESS"),
    ]
    results={};summary=[]
    for name,mode,start,goal,overrides,expected in cases:
        result=planner.run(mode,start,goal,overrides);save_result(out,name,result);results[name]=result
        ok=result["status"]==expected
        summary.append({"case":name,"expected":expected,"passed":ok,**{k:v for k,v in result.items() if k in (
            "status","length_m","reverse_length_m","turn_steps","cost","expansions","elapsed_s","verification")}})
        print(name,result["status"],round(result.get("length_m",0),3),"m",flush=True)
    if results["loaded_detour"]["status"]=="SUCCESS":
        detour_longer=results["loaded_detour"]["length_m"]>results["loaded_high_passage"]["length_m"]+.1
    else:detour_longer=False
    report={"all_passed":all(c["passed"] for c in summary) and detour_longer,"detour_longer_than_clear_route":detour_longer,
            "source_scene_sha256":planner.scene["scene_sha256"],"cases":summary,
            "scope":"Offline A* and independent geometric checks, not Unity physics or ROS execution"}
    write_json(out/"verification_report.json",report)
    maps={m:planner.maps(m)[:2] for m in ("empty","loaded")}
    preview(out,planner.grid,planner.arrays["occupancy"],planner.arrays["clearance_m"],maps,planner.goals,results)
    # A separate drawing puts the detour and new obstacle on their own map.
    from PIL import Image,ImageDraw
    g=planner.grid;image=Image.new('RGB',(g.width,g.height),(235,240,244))
    draw=ImageDraw.Draw(image)
    def pixel(x,y):
        c,r=g.cell(x,y);return c,g.height-1-r
    for s in scene_obstacles(planner.scene,"carrying",barrier):
        lo,hi=s["min"],s["max"]
        if not (g.bounds[0]<=lo[0]<g.bounds[2] and g.bounds[1]<=lo[1]<g.bounds[3] and g.bounds[0]<=hi[0]<g.bounds[2] and g.bounds[1]<=hi[1]<g.bounds[3]):continue
        a,b=pixel(lo[0],hi[1]),pixel(hi[0],lo[1])
        draw.rectangle([a,b],fill=(210,70,65) if s["id"].startswith("scenario/") else (145,158,170))
    for name,color in (("loaded_high_passage",(75,130,210)),("loaded_detour",(0,150,85))):
        pts=[pixel(*p[:2]) for p in results[name]["poses"]]
        if len(pts)>1:draw.line(pts,fill=color,width=3)
    draw.text((18,18),'LOADED A* REPLAN',fill=(25,40,55))
    draw.text((18,38),'Blue: clear route 6.00 m | Green: detour %.2f m' % results['loaded_detour'].get('length_m',0),fill=(25,40,55))
    draw.text((18,58),'Red: added barrier | Gray: projected scene geometry (includes overhead)',fill=(25,40,55))
    draw.rectangle([0,0,g.width-1,g.height-1],outline=(60,75,90))
    image.save(out/"detour.png")
    if not report["all_passed"]:raise AssertionError("Scenario validation failed; inspect verification_report.json")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['empty','raised_empty','loaded'],default='empty')
    parser.add_argument('--start',default='RobotStart',help='goal name or x,y,yaw radians')
    parser.add_argument('--goal',default='Pickup_P1')
    parser.add_argument('--overrides',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/astar')
    parser.add_argument('--verify-suite',action='store_true')
    parser.add_argument('--max-expansions',type=int,default=1500000)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if args.verify_suite:write_json(args.output/'verification_report.json',{'all_passed':False,'status':'RUNNING'})
    else:save_result(args.output,'path',{'status':'PENDING','poses':[],'segments':[]})
    try:
        planner=Planner()
        if args.verify_suite:suite(planner,args.output)
        else:
            result=planner.run(args.mode,args.start,args.goal,json.loads(args.overrides.read_text()) if args.overrides else None,args.max_expansions)
            save_result(args.output,'path',result)
            print(result['status'],result.get('length_m'),result.get('verification'))
            if result['status']!='SUCCESS':raise SystemExit(2)
    except (ValueError,OSError) as exc:
        failure={'status':'INVALID_REQUEST','message':str(exc),'poses':[],'segments':[]}
        if args.verify_suite:write_json(args.output/'verification_report.json',dict(failure,all_passed=False))
        else:save_result(args.output,'path',failure)
        print(str(exc));raise SystemExit(2) from exc


if __name__=='__main__':main()
