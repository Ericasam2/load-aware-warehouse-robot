import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .grid import Grid, build_mode, raw_layers, scene_obstacles
from .astar import plan

ROOT=Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def pgm(out,name,array,grid):
    image=np.where(array[::-1],0,254).astype(np.uint8)
    (out/(name+".pgm")).write_bytes(f"P5\n{grid.width} {grid.height}\n255\n".encode()+image.tobytes())
    (out/(name+".yaml")).write_text(f"image: {name}.pgm\nmode: trinary\nresolution: {grid.resolution}\norigin: [{grid.bounds[0]}, {grid.bounds[1]}, 0.0]\nnegate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n",encoding="utf-8")


def preview(out,grid,raw,clearance,maps,goals,paths):
    font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf",18) if Path("C:/Windows/Fonts/arial.ttf").exists() else ImageFont.load_default()
    canvas=Image.new("RGB",(grid.width*2*3,grid.height*2+110),(20,28,39));draw=ImageDraw.Draw(canvas)
    panels=[("GROUND + OVERHEAD",raw),("EMPTY / free in at least one heading",maps["empty"][0].all(axis=0)),("LOADED / free in at least one heading",maps["loaded"][0].all(axis=0))]
    for i,(title,mask) in enumerate(panels):
        rgb=np.full((*mask.shape,3),[228,235,238],dtype=np.uint8)
        rgb[(clearance<2.5)&~raw]=[248,213,136]
        rgb[mask]=[54,66,81]
        image=Image.fromarray(rgb[::-1]).resize((grid.width*2,grid.height*2),Image.Resampling.NEAREST)
        canvas.paste(image,(i*grid.width*2,55));draw.text((i*grid.width*2+14,15),title,font=font,fill="white")
        def pixel(x,y):
            c,r=grid.cell(x,y);return i*grid.width*2+c*2,55+(grid.height-1-r)*2
        for name in ("RobotStart","Pickup_P1","Dropoff_P2"):
            x,y=pixel(*goals[name][:2]);draw.ellipse((x-5,y-5,x+5,y+5),fill=(220,63,64));draw.text((x+7,y+3),name,font=font,fill=(200,25,45))
        for key,color in (("start_to_pickup",(0,110,230)),("pickup_to_dropoff",(0,155,93)),("loaded_high_passage",(161,69,201))):
            if i==1 and key!="start_to_pickup":continue
            if i==2 and key=="start_to_pickup":continue
            if key in paths:
                points=[pixel(*p[:2]) for p in paths[key]["poses"]]
                if len(points)>1:draw.line(points,fill=color,width=3)
    draw.text((14,grid.height*2+70),"Blue: empty to P1 | Green: loaded to P2 | Purple: loaded under high rack. Paths use eight heading layers.",font=font,fill="white")
    canvas.save(out/"planning-preview.png")


def build(args):
    config=json.loads((ROOT/"config/planning.json").read_text(encoding="utf-8-sig"))
    source=Path(args.scene);scene=json.loads(source.read_text(encoding="utf-8-sig"))
    actual=ROOT/"unity_project"/scene["scene_path"]
    if actual.exists() and hashlib.sha256(actual.read_bytes()).hexdigest()!=scene["scene_sha256"]:
        raise ValueError("Unity scene changed: re-export geometry before building maps")
    for scene_key,config_value in (("robot_mass_kg",config["robot"]["mass_kg"]),("wheel_radius",config["robot"]["wheel_radius"]),
                                  ("track_width",config["robot"]["track_width"]),("lift_max_extension",config["robot"]["lift_extension"][1])):
        if scene_key not in scene or abs(scene[scene_key]-config_value)>1e-4:
            raise ValueError("Robot definition differs from scene or export is outdated: "+scene_key)
    overrides=json.loads(Path(args.overrides).read_text(encoding="utf-8")) if args.overrides else None
    grid=Grid(scene["bounds"],config["resolution"])
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    raw,clearance=raw_layers(grid,scene_obstacles(scene,"initial",overrides))
    pgm(out,"occupancy",raw,grid)
    maps={};arrays={"occupancy":raw,"clearance_m":clearance};goals={g["id"]:g["pose"] for g in scene["goals"]}
    goals["DropoffApproach"]=[goals["Dropoff_P2"][0],goals["Dropoff_P2"][1]-2.5,-math.pi/2]
    for name,mode in config["modes"].items():
        print("Building",name,flush=True)
        blocked,rotation=build_mode(grid,scene_obstacles(scene,mode["scene_profile"],overrides),mode,config["safety_margin"])
        if config["docking"]["forbid_rotation_in_slot"]:
            for marker in ("Pickup_P1","Dropoff_P2"):
                x,y=goals[marker][:2]
                rotation |= ((np.abs(grid.x[None,:]-x)<=config["docking"]["slot_width"]/2+grid.resolution/2) &
                             (np.abs(grid.y[:,None]-y)<=config["docking"]["track_length"]/2+grid.resolution/2))
        maps[name]=(blocked,rotation);arrays[name]=blocked;arrays[name+"_rotation_blocked"]=rotation
        for k in range(8):pgm(out,f"{name}_h{k}",blocked[k],grid)
    np.savez_compressed(out/"planning_grids.npz",**arrays)
    metadata={"schema_version":1,"frame":"map","resolution":grid.resolution,"origin":grid.bounds[:2].tolist(),
              "width":int(grid.width),"height":int(grid.height),"array_indexing":"[heading, row_y, column_x]; bottom-left origin",
              "heading_radians":[k*math.pi/4 for k in range(8)],"blocked_value":True,"safety_margin":config["safety_margin"],
              "source_scene_sha256":scene["scene_sha256"],"config_sha256":hashlib.sha256((ROOT/"config/planning.json").read_bytes()).hexdigest(),
              "map_from_odom":scene["map_from_odom"],"scene_profiles":{n:m["scene_profile"] for n,m in config["modes"].items()},
              "clearance_definition":"lowest obstacle underside, 0 for floor-mounted obstacles, infinity for no overhead; not a substitute for height layers",
              "overrides":overrides}
    write_json(out/"metadata.json",metadata);write_json(out/"goals.json",goals)
    zones=[]
    for s in scene["obstacles"]:
        if s["name"]=="LowClearanceCrossbeam" or (s["name"]=="OverheadStorageDeck" and "HIGH_THROUGH_RACK" in s["id"]):
            zones.append({"id":s["id"],"kind":"LOW_CLEARANCE" if s["name"]=="LowClearanceCrossbeam" else "HIGH_CLEARANCE",
                          "min_xy":s["min"][:2],"max_xy":s["max"][:2],"clearance":s["min"][2]})
    for marker,kind in (("Pickup_P1","PICKUP_ZONE"),("Dropoff_P2","DROPOFF_ZONE")):
        zones.append({"id":marker,"kind":kind,"centre":goals[marker][:2],"yaw":config["docking"]["yaw"],
                      "slot_width":config["docking"]["slot_width"],"support_height":config["docking"]["support_height"]})
    write_json(out/"semantic_zones.json",{"frame":"map","zones":zones,"note":"Display/mission labels only; collision truth comes from exported 3D solids"})
    if args.no_demo:
        preview(out,grid,raw,clearance,maps,goals,{})
        return
    paths={};failures={}
    for name,mode,start,goal in [
        ("start_to_pickup","empty",goals["RobotStart"],goals["Pickup_P1"]),
        ("pickup_to_dropoff","loaded",goals["Pickup_P1"],goals["Dropoff_P2"]),
        ("empty_low_passage","empty",[-1,5,0],[5,5,0]),
        ("loaded_high_passage","loaded",[-1,-5,0],[5,-5,0])]:
        try:
            result=plan(grid,*maps[mode],start,goal)
            result.update(mode=mode,requested_start=start,requested_goal=goal)
            paths[name]=result;print(name,len(result["poses"]),"poses",flush=True)
        except (ValueError,RuntimeError) as exc:failures[name]=str(exc)
    report={"paths":{n:{k:v for k,v in p.items() if k not in ("states","poses")} for n,p in paths.items()},"failures":failures,
            "scope":"Offline geometric planning only; no commands sent; payload carrying profile assumes external attachment confirmation"}
    write_json(out/"demo_paths.json",paths);write_json(out/"validation.json",report)
    preview(out,grid,raw,clearance,maps,goals,paths)
    if failures:raise RuntimeError(str(failures))


if __name__=="__main__":
    p=argparse.ArgumentParser(description="Build height- and heading-aware A* maps from Unity colliders")
    p.add_argument("--scene",default=str(ROOT/"maps/scene_geometry.json"))
    p.add_argument("--output",default=str(ROOT/"maps/generated"))
    p.add_argument("--overrides",help="JSON disabled_ids/additional obstacles in map coordinates")
    p.add_argument("--no-demo",action="store_true",help="Build maps only; useful for deliberately blocked scenarios")
    build(p.parse_args())
