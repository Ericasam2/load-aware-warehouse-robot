"""Independent vertex-projection oracle; not the vectorized costmap implementation."""
import math
import numpy as np


def collides(pose, layer, solid, margin):
    if solid["max"][2]<=layer["bottom"] or solid["min"][2]>=layer["top"]:return False
    x,y,a=pose;c,s=math.cos(a),math.sin(a)
    robot=[(x+c*u-s*v,y+s*u+c*v) for u in (-layer["length"]/2,layer["length"]/2) for v in (-layer["width"]/2,layer["width"]/2)]
    box=[(u,v) for u in (solid["min"][0]-margin,solid["max"][0]+margin)
         for v in (solid["min"][1]-margin,solid["max"][1]+margin)]
    for ax,ay in ((1,0),(0,1),(c,s),(-s,c)):
        pr=[px*ax+py*ay for px,py in robot];pb=[px*ax+py*ay for px,py in box]
        if max(pr)<=min(pb) or max(pb)<=min(pr):return False
    return True


def validate_path(result,grid,blocked,rotation,mode,solids,margin):
    poses=result["poses"];samples=0
    for p in poses:
        c,r=grid.cell(*p[:2]);h=round(p[2]/(math.pi/4))%8
        if blocked[h,r,c]:raise AssertionError("Path visits a blocked cell")
    edges=list(zip(poses,poses[1:])) or [(poses[0],poses[0])]
    for a,b in edges:
        da=(b[2]-a[2]+math.pi)%math.tau-math.pi
        distance=math.hypot(b[0]-a[0],b[1]-a[1])
        if distance and abs(da)>1e-6:raise AssertionError("Moving while rotating is not a graph action")
        if distance and abs((b[0]-a[0])*math.sin(a[2])-(b[1]-a[1])*math.cos(a[2]))>1e-6:
            raise AssertionError("Lateral motion is not valid for differential drive")
        if abs(da)>1e-6:
            c,r=grid.cell(*a[:2])
            if rotation[r,c]:raise AssertionError("Rotation violates the swept-space or docking restriction")
        n=max(1,math.ceil(distance/(grid.resolution/2)),math.ceil(abs(da)/math.radians(2)))
        for t in np.linspace(0,1,n+1):
            p=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1]),a[2]+t*da];samples+=1
            for layer in mode["layers"]:
                c,s=abs(math.cos(p[2])),abs(math.sin(p[2]))
                ex=c*layer["length"]/2+s*layer["width"]/2+margin
                ey=s*layer["length"]/2+c*layer["width"]/2+margin
                if p[0]-ex<grid.bounds[0] or p[0]+ex>grid.bounds[2] or p[1]-ey<grid.bounds[1] or p[1]+ey>grid.bounds[3]:
                    raise AssertionError("Footprint leaves map bounds")
                for solid in solids:
                    if collides(p,layer,solid,margin):raise AssertionError("Collision with "+solid["id"]+" at "+str(p))
    return {"passed":True,"sampled_poses":samples,"translation_step_max_m":grid.resolution/2,
            "rotation_step_max_deg":2,"checked_margin_m":margin}
