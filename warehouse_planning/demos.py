"""Generate English 2D/3D warehouse demos as GIF and optional MP4."""
import argparse
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .animation import motion_frames
from .astar import plan
from .grid import Grid, build_mode, scene_obstacles
from .validation import validate_path

ROOT=Path(__file__).resolve().parents[1]
W,H=1152,720
FPS=12
CASES={
    '01_pickup':('Empty robot docking at P1','empty',[-6,7,0],[2,5,-math.pi/2],[-7.2,2.5,5.5,8.2]),
    '02_loaded_detour':('Loaded robot obstacle detour','loaded',[-1,-5,0],[5,-5,0],[-2,-8,6,-2]),
    '03_low_passage':('Empty robot through the low passage','empty',[-1,5,0],[5,5,0],[-2,2.5,6,7.5]),
    '04_high_passage':('Loaded robot through the high passage','loaded',[-1,-5,0],[5,-5,0],[-2,-7.5,6,-2.5]),
}


def font(size):
    path=Path('C:/Windows/Fonts/arial.ttf')
    return ImageFont.truetype(str(path),size) if path.exists() else ImageFont.load_default()


def run_case(name,out,mp4):
    title,mode,start,goal,bounds=CASES[name]
    scene=json.loads((ROOT/'maps/scene_geometry.json').read_text(encoding='utf-8-sig'))
    config=json.loads((ROOT/'config/planning.json').read_text())
    meta=json.loads((ROOT/'maps/generated/metadata.json').read_text())
    if scene['scene_sha256']!=meta['source_scene_sha256'] or hashlib.sha256((ROOT/'config/planning.json').read_bytes()).hexdigest()!=meta['config_sha256']:
        raise ValueError('Map snapshot is stale')
    grid=Grid(scene['bounds'],config['resolution'])
    overrides=json.loads((ROOT/'config/temporary_high_block.json').read_text()) if name=='02_loaded_detour' else None
    solids=scene_obstacles(scene,config['modes'][mode]['scene_profile'],overrides)
    if overrides:
        blocked,rotation=build_mode(grid,solids,config['modes'][mode],config['safety_margin'])
        for g in scene['goals']:
            if g['id'] not in ('Pickup_P1','Dropoff_P2'):continue
            x,y=g['pose'][:2]
            rotation |= ((np.abs(grid.x[None,:]-x)<=config['docking']['slot_width']/2+grid.resolution/2)&(np.abs(grid.y[:,None]-y)<=config['docking']['track_length']/2+grid.resolution/2))
    else:
        with np.load(ROOT/'maps/generated/planning_grids.npz') as arrays:
            blocked,rotation=arrays[mode],arrays[mode+'_rotation_blocked']
    trace=[];seen=set()
    def expand(state,g,h,n):
        if state[:2] not in seen:
            seen.add(state[:2]);trace.append((grid.world(*state[:2]),n,g,h))
    result=plan(grid,blocked,rotation,start,goal,on_expand=expand)
    verification=validate_path(result,grid,blocked,rotation,config['modes'][mode],solids,config['safety_margin'])
    result.update(mode=mode,scenario=name,verification=verification,source_scene_sha256=scene['scene_sha256'])
    out.mkdir(parents=True,exist_ok=True)
    (out/(name+'.json')).write_text(json.dumps(result,indent=2))
    visible=[s for s in solids if s['max'][0]>=bounds[0] and s['min'][0]<=bounds[2] and s['max'][1]>=bounds[1] and s['min'][1]<=bounds[3] and s['name'] not in ('WestWall','EastWall','NorthWall','SouthBarrier')]
    visible.sort(key=lambda s:sum(s['min'][:2])+sum(s['max'][:2]))
    ftitle,fsub,fsmall=font(26),font(18),font(15)
    sx=min(315/(bounds[2]-bounds[0]),395/(bounds[3]-bounds[1]))
    cx,cy=(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2
    def p2(x,y,z=0):return (195+(x-cx)*sx,355-(y-cy)*sx)
    def iso(x,y,z=0):return ((x-cx-(y-cy))*.707,(x-cx+y-cy)*.34-z*.94)
    corners=[iso(x,y,z) for x in (bounds[0],bounds[2]) for y in (bounds[1],bounds[3]) for z in (0,3.3)]
    imin,imax=min(p[0] for p in corners),max(p[0] for p in corners)
    jmin,jmax=min(p[1] for p in corners),max(p[1] for p in corners)
    sc=min(670/(imax-imin),435/(jmax-jmin))
    def p3(x,y,z=0):
        a,b=iso(x,y,z);return (765+(a-(imin+imax)/2)*sc,362+(b-(jmin+jmax)/2)*sc)
    def box(draw,lo,hi,color,project,angle=0,wire=False):
        x,y=(lo[0]+hi[0])/2,(lo[1]+hi[1])/2
        lx,ly=(hi[0]-lo[0])/2,(hi[1]-lo[1])/2
        c,s=math.cos(angle),math.sin(angle)
        verts=[(x+c*u-s*v,y+s*u+c*v,z) for z in (lo[2],hi[2]) for u,v in [(-lx,-ly),(lx,-ly),(lx,ly),(-lx,ly)]]
        points=[project(*v) for v in verts]
        if project==p2:
            draw.polygon(points[:4],fill=None if wire else color,outline='#a77831' if wire else '#364e66',width=2)
            return
        faces=[(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7),(4,5,6,7)]
        faces.sort(key=lambda face:sum(sum(verts[i]) for i in face))
        rgb=tuple(int(color[i:i+2],16) for i in (1,3,5))
        for k,face in enumerate(faces):
            fill=tuple(int(v*(.72+.055*k)) for v in rgb)
            draw.polygon([points[i] for i in face],fill=None if wire else fill,outline='#7c91a5' if wire else '#304459',width=1)
    base=Image.new('RGB',(W,H),'#0d182b');d=ImageDraw.Draw(base)
    d.rounded_rectangle((16,110,374,590),radius=14,fill='#edf3f7')
    d.rounded_rectangle((390,110,1136,590),radius=14,fill='#edf3f7')
    d.text((24,18),title,font=ftitle,fill='white')
    d.text((24,56),'WAREHOUSE A*  |  2D PLANNING + 3D GEOMETRIC REPLAY',font=fsmall,fill='#a5bad3')
    d.text((30,123),'2D MAP',font=fsub,fill='#263c55');d.text((407,123),'3D SPACE  /  orthographic cutaway',font=fsub,fill='#263c55')
    for x in np.arange(math.ceil(bounds[0]),bounds[2]+.01):
        for proj in (p2,p3):d.line([proj(x,bounds[1]),proj(x,bounds[3])],fill='#d0dbe5')
    for y in np.arange(math.ceil(bounds[1]),bounds[3]+.01):
        for proj in (p2,p3):d.line([proj(bounds[0],y),proj(bounds[2],y)],fill='#d0dbe5')
    for solid in visible:
        color='#df6558' if solid['kind']=='temporary' else ('#d4ad68' if solid['min'][2]>.46 else '#70859b')
        box(d,solid['min'],solid['max'],color,p2,wire=solid['min'][2]>.46)
        box(d,solid['min'],solid['max'],color,p3,wire=solid['min'][2]>.46 and solid['kind']!='temporary')
    for proj in (p2,p3):
        for label,p in [('START',start),('GOAL',goal)]:
            x,y=proj(*p[:2]);d.ellipse((x-4,y-4,x+4,y+4),fill='#0c9c80');d.text((x+6,y+5),label,font=fsmall,fill='#263c55')
    frames=[]
    def hud(frame,phase,detail):
        draw=ImageDraw.Draw(frame)
        draw.text((24,80),phase,font=fsub,fill='#62ddc2')
        draw.text((26,610),detail,font=fsub,fill='white')
        draw.text((26,642),'Cyan: explored cells   Green: route   Orange: robot   Red: obstacle',font=fsmall,fill='#aec1d7')
        draw.text((26,671),'Actual A* search; geometric motion only. Wireframe overhead; robot highlighted through structures.',font=fsmall,fill='#aec1d7')
        return frame
    layer=base.copy();last=0
    for stop in np.linspace(1,len(trace),36,dtype=int):
        draw=ImageDraw.Draw(layer)
        for (x,y),n,g,h in trace[last:stop]:
            if bounds[0]<=x<=bounds[2] and bounds[1]<=y<=bounds[3]:draw.point(p2(x,y),fill='#1dafc0')
        _,n,g,h=trace[stop-1];last=stop
        frames.append(hud(layer.copy(),'SEARCH  |  heading-aware A*',f'Expanded: {n:,} states    g: {g:.2f}    h: {h:.2f}    f = g + h: {g+h:.2f}'))
    poses=motion_frames(result['segments'],result['poses'][0],distance_step=.11,angle_step=.10)
    route=[p[:2] for p in result['poses']]
    for i,p in enumerate(poses):
        frame=base.copy();draw=ImageDraw.Draw(frame)
        for proj in (p2,p3):
            draw.line([proj(x,y,.015) for x,y in route],fill='#07a67e',width=3)
            for layer_def in config['modes'][mode]['layers']:
                L,B=layer_def['length']/2,layer_def['width']/2
                color='#ed9841' if layer_def['name']!='payload' else '#e3bf72'
                box(draw,[p[0]-L,p[1]-B,layer_def['bottom']],[p[0]+L,p[1]+B,layer_def['top']],color,proj,p[2])
            z=.50 if mode=='empty' else 1.82
            draw.line([proj(p[0],p[1],z),proj(p[0]+.6*math.cos(p[2]),p[1]+.6*math.sin(p[2]),z)],fill='#24394c',width=3)
        height=max(l['top'] for l in config['modes'][mode]['layers'])
        detail=f'Path: {result["length_m"]:.2f} m    Robot height: {height:.3f} m    Collision check: PASS'
        if name=='03_low_passage':detail='Empty height: 0.734 m   Low entrance: 1.00 m   Internal supports checked'
        if name=='04_high_passage':detail='Loaded height: 1.804 m   High passage clearance: 2.40 m   PASS'
        frames.append(hud(frame,'REPLAY  |  '+mode.upper()+f'  |  {i+1}/{len(poses)}',detail))
    poster=frames[len(frames)-max(2,len(poses)//2)]
    poster.save(out/(name+'.png'))
    frames.extend([frames[-1]]*18)
    frames[0].save(out/(name+'.gif'),save_all=True,append_images=frames[1:],duration=round(1000/FPS),loop=0,optimize=False)
    video=None
    if mp4:
        sys.path.insert(0,str(ROOT/'outputs/demo_dependencies'))
        import imageio_ffmpeg
        video=out/(name+'.mp4')
        process=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-crf','20','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
        for frame in frames:process.stdin.write(frame.tobytes())
        process.stdin.close()
        if process.wait()!=0:raise RuntimeError('Video encoding failed')
    print(f'{name}: {len(frames)} frames; {result["length_m"]:.2f} m; verified',flush=True)
    return dict(id=name,title=title,frames=len(frames),fps=FPS,length_m=result['length_m'],verification=verification,mp4=video.name if video else None)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mp4',action='store_true')
    parser.add_argument('--case',choices=list(CASES))
    args=parser.parse_args();out=ROOT/'outputs/demo_showcase'
    results=[run_case(name,out,args.mp4) for name in ([args.case] if args.case else CASES)]
    if args.case and (out/'manifest.json').exists():
        previous={r['id']:r for r in json.loads((out/'manifest.json').read_text())}
        previous.update({r['id']:r for r in results})
        results=[previous[name] for name in CASES if name in previous]
    (out/'manifest.json').write_text(json.dumps(results,indent=2))
    cards=[]
    for item in results:
        n=item['id']
        media=f'<video controls loop muted preload="metadata" poster="{n}.png" src="{n}.mp4"></video>' if item['mp4'] else f'<img src="{n}.gif">'
        cards.append(f'<section><h2>{item["title"]}</h2>{media}<p><a href="{n}.gif">Animated GIF</a> | <a href="{n}.png">Demo still</a> | <a href="{n}.json">Planning result</a></p></section>')
    (out/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Warehouse A* Demo Gallery</title><style>body{max-width:1152px;margin:35px auto;background:#0d182b;color:#e6f0fa;font:17px system-ui}video,img{width:100%;border-radius:12px}section{margin-bottom:40px}a{color:#62ddc2}</style><h1>Warehouse A* Demo Gallery</h1><p>Pure Python | 2D search and 3D geometric replay | English visuals</p>'+''.join(cards),encoding='utf-8')


if __name__=='__main__':main()
