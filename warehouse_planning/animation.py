"""Pure Python warehouse A* replay: numpy + Pillow; optional Tk player.

Uses the exported static geometry snapshot; Unity/ROS and the Unity project
directory are not needed. The robot motion is geometric, not dynamics.
"""
import argparse
import base64
import io
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .astar import plan
from .grid import Grid, build_mode, scene_obstacles
from .validation import validate_path

ROOT = Path(__file__).resolve().parents[1]


def motion_frames(segments, start, distance_step=.12, angle_step=.10):
    poses = [start]
    for segment in segments:
        a, b = segment['start'], segment['end']
        da = (b[2]-a[2]+math.pi) % math.tau-math.pi
        n = max(1, math.ceil(math.dist(a[:2], b[:2])/distance_step), math.ceil(abs(da)/angle_step))
        for i in range(1, n+1):
            t = i/n
            poses.append([a[0]+t*(b[0]-a[0]), a[1]+t*(b[1]-a[1]), a[2]+t*da])
    return poses


def generate(scenario, out):
    scene = json.loads((ROOT/'maps/scene_geometry.json').read_text(encoding='utf-8-sig'))
    config = json.loads((ROOT/'config/planning.json').read_text())
    meta = json.loads((ROOT/'maps/generated/metadata.json').read_text())
    if scene['scene_sha256'] != meta['source_scene_sha256'] or hashlib.sha256((ROOT/'config/planning.json').read_bytes()).hexdigest() != meta['config_sha256']:
        raise ValueError('Snapshot/config and generated maps differ; rebuild the planning maps first.')
    goals = {g['id']: g['pose'] for g in scene['goals']}
    mode = 'empty' if scenario == 'pickup' else 'loaded'
    start, goal = (goals['RobotStart'], goals['Pickup_P1']) if scenario == 'pickup' else ([-1,-5,0],[5,-5,0])
    overrides = None if scenario == 'pickup' else json.loads((ROOT/'config/temporary_high_block.json').read_text())
    grid = Grid(scene['bounds'], config['resolution'])
    solids = scene_obstacles(scene, config['modes'][mode]['scene_profile'], overrides)
    if overrides:
        blocked, rotation = build_mode(grid, solids, config['modes'][mode], config['safety_margin'])
        for name in ('Pickup_P1','Dropoff_P2'):
            x,y = goals[name][:2]
            rotation |= ((np.abs(grid.x[None,:]-x) <= config['docking']['slot_width']/2+grid.resolution/2) &
                         (np.abs(grid.y[:,None]-y) <= config['docking']['track_length']/2+grid.resolution/2))
    else:
        with np.load(ROOT/'maps/generated/planning_grids.npz') as arrays:
            blocked, rotation = arrays[mode], arrays[mode+'_rotation_blocked']
    # Capture actual popped states. Display the first expansion of each XY cell;
    # search itself still uses all eight headings and re-opened states.
    seen = set()
    trace = []
    def expanded(state, g, h, count):
        cell = state[:2]
        if cell not in seen:
            seen.add(cell)
            trace.append((state, g, h, count))
    result = plan(grid, blocked, rotation, start, goal, on_expand=expanded)
    result['verification'] = validate_path(result, grid, blocked, rotation, config['modes'][mode], solids, config['safety_margin'])
    result.update(scenario=scenario, mode=mode, simulation='geometric replay; no physics or ROS', displayed_xy_cells=len(trace))
    out.mkdir(parents=True, exist_ok=True)
    (out/'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    scale = 28
    width, height = 660, 690
    font_path = Path('C:/Windows/Fonts/arial.ttf')
    font = ImageFont.truetype(str(font_path),16) if font_path.exists() else ImageFont.load_default()
    small = ImageFont.truetype(str(font_path),12) if font_path.exists() else ImageFont.load_default()
    def pixel(x,y): return (int(75+(x-grid.bounds[0])*scale),int(108+(grid.bounds[3]-y)*scale))
    base = Image.new('RGB',(width,height),'#eff3f8')
    d = ImageDraw.Draw(base)
    for x in range(-9,10):
        d.line([pixel(x,-10),pixel(x,10)], fill='#dfe6ee')
    for y in range(-10,11):
        d.line([pixel(-9,y),pixel(9,y)], fill='#dfe6ee')
    for solid in sorted(solids,key=lambda s:-s['min'][2]):
        lo,hi=solid['min'],solid['max']
        color = '#e4c385' if lo[2]>.46 else '#596a7c'
        if solid.get('kind') == 'temporary':color='#e06459'
        d.rectangle([pixel(lo[0],hi[1]),pixel(hi[0],lo[1])],fill=color)
    frames=[]
    def decorate(canvas,title,subtitle):
        draw=ImageDraw.Draw(canvas)
        draw.rectangle((0,0,width,98), fill='#182b44')
        draw.text((20,12),title,font=font,fill='white')
        draw.text((20,38),subtitle,font=small,fill='#dce8f7')
        draw.text((20,62),'Dark: ground solids | Gold: overhead | Red: added obstacle',font=small,fill='#dce8f7')
        draw.text((20,79),'Cyan: explored XY projection | Green: final path | Orange: robot',font=small,fill='#dce8f7')
        for label,p,color in [('S',start,'#009c80'),('G',goal,'#e34667')]:
            x,y=pixel(*p[:2]);draw.ellipse((x-6,y-6,x+6,y+6),fill=color);draw.text((x+8,y-7),label,font=small,fill='#15243a')
        draw.text((20,674),'Geometric animation. Search uses (x,y,heading) and height-aware footprints.',font=small,fill='#283b52')
        return canvas
    layer=base.copy()
    last=0
    for stop in np.linspace(1,len(trace),65,dtype=int):
        draw=ImageDraw.Draw(layer)
        for state,g,h,count in trace[last:stop]:
            x,y=pixel(*grid.world(*state[:2]));draw.point((x,y),fill='#21bcd0')
        state,g,h,count=trace[stop-1]
        frame=layer.copy();draw=ImageDraw.Draw(frame)
        x,y=pixel(*grid.world(*state[:2]));draw.ellipse((x-3,y-3,x+3,y+3),fill='#ff942e')
        frames.append(decorate(frame,'A* SEARCH  /  '+scenario,f'Expanded states: {count:,}    current g={g:.2f}  h={h:.2f}  f=g+h={g+h:.2f}'))
        last=stop
    poses=motion_frames(result['segments'],result['poses'][0])
    path_pixels=[pixel(*p[:2]) for p in result['poses']]
    for index,p in enumerate(poses):
        frame=base.copy();draw=ImageDraw.Draw(frame)
        if len(path_pixels)>1:draw.line(path_pixels,fill='#079b72',width=3)
        for layer_def in reversed(config['modes'][mode]['layers']):
            c,s=math.cos(p[2]),math.sin(p[2]);L,W=layer_def['length']/2,layer_def['width']/2
            corners=[pixel(p[0]+c*u-s*v,p[1]+s*u+c*v) for u,v in [(-L,-W),(L,-W),(L,W),(-L,W)]]
            draw.polygon(corners,outline='#bf630c',fill='#f5ae43' if layer_def['name']=='base_and_wheels' else None)
        draw.line([pixel(*p[:2]),pixel(p[0]+.5*math.cos(p[2]),p[1]+.5*math.sin(p[2]))],fill='#172b44',width=3)
        frames.append(decorate(frame,'ROBOT PATH REPLAY  /  '+mode,f'Path: {result["length_m"]:.2f} m   turns: {result["turn_steps"]}   replay: {index+1}/{len(poses)}'))
    frames[-1].save(out/'preview.png')
    frames[0].save(out/'simulation.gif',save_all=True,append_images=frames[1:],duration=[80]*65+[70]*(len(poses)-1)+[1800],loop=0,optimize=False)
    write_player(frames,out/'player.html')
    print(f'{scenario}: {result["length_m"]:.2f} m; {result["expansions"]:,} expansions; geometry PASS',flush=True)
    print(out/'simulation.gif',flush=True)
    return frames


def write_player(frames, path):
    data=[]
    for frame in frames:
        buffer=io.BytesIO();frame.save(buffer,format='PNG')
        data.append('data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii'))
    page='''<!doctype html><meta charset="utf-8"><title>A* 仓库动画</title>
<style>body{margin:20px auto;max-width:720px;font:16px system-ui;background:#142238;color:#eef4ff}img{width:100%;max-height:78vh;object-fit:contain}button,select{padding:8px;margin:6px}input{width:100%}</style>
<h2>纯 Python · 仓库 A* 动画</h2><p>先观察搜索展开，再观看机器人沿路径运动。可暂停并拖动进度。</p>
<img id="view" alt="A* 搜索与机器人动画"><div><button id="toggle">暂停</button><button id="replay">重播</button>
<select id="speed"><option value="0.5">0.5 倍速</option><option value="1" selected>1 倍速</option><option value="2">2 倍速</option><option value="4">4 倍速</option></select><span id="state"></span></div>
<input id="seek" type="range" min="0" value="0"><p>青色：搜索展开投影；绿色：规划路径；橙色：机器人。此处为几何运动，不包含动力学。</p>
<script>const frames=__FRAMES__;let i=0,playing=true;const view=document.getElementById('view'),seek=document.getElementById('seek'),toggle=document.getElementById('toggle'),speed=document.getElementById('speed');seek.max=frames.length-1;
function draw(){view.src=frames[i];seek.value=i;document.getElementById('state').textContent=(i<65?'搜索展开':'路径运动')+' · '+(i+1)+' / '+frames.length;toggle.textContent=playing?'暂停':'播放';}
toggle.onclick=()=>{if(i===frames.length-1)i=0;playing=!playing;draw()};document.getElementById('replay').onclick=()=>{i=0;playing=true;draw()};seek.oninput=()=>{i=Number(seek.value);playing=false;draw()};
function tick(){if(playing){i=Math.min(i+1,frames.length-1);if(i===frames.length-1)playing=false;draw()}setTimeout(tick,80/Number(speed.value))}draw();setTimeout(tick,80);</script>'''
    path.write_text(page.replace('__FRAMES__',json.dumps(data)),encoding='utf-8')


def show(frames):
    import tkinter as tk
    from PIL import ImageTk
    root=tk.Tk();root.title('Warehouse A* | Python simulation')
    photos=[ImageTk.PhotoImage(f) for f in frames]
    label=tk.Label(root,image=photos[0]);label.pack()
    playing=tk.BooleanVar(value=True);position=tk.IntVar(value=0);speed=tk.DoubleVar(value=1)
    row=tk.Frame(root);row.pack(fill='x')
    tk.Button(row,text='Play / Pause',command=lambda:playing.set(not playing.get())).pack(side='left')
    tk.Button(row,text='Replay',command=lambda:(position.set(0),playing.set(True))).pack(side='left')
    tk.Label(row,text='Speed').pack(side='left')
    tk.Spinbox(row,values=(.5,1,2,4),textvariable=speed,width=4).pack(side='left')
    tk.Scale(root,from_=0,to=len(frames)-1,orient='horizontal',variable=position,length=640,
             command=lambda value:label.configure(image=photos[int(float(value))])).pack()
    def tick():
        if playing.get():
            position.set(min(position.get()+1,len(frames)-1));label.configure(image=photos[position.get()])
            if position.get()==len(frames)-1:playing.set(False)
        try: delay=max(20,int(80/max(.1,speed.get())))
        except (ValueError,tk.TclError):delay=80
        root.after(delay,tick)
    root.after(80,tick);root.mainloop()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario',choices=['pickup','detour'],default='pickup')
    parser.add_argument('--show',action='store_true',help='Open offline browser animation player')
    parser.add_argument('--tk',action='store_true',help='Use optional Tk player instead')
    args=parser.parse_args()
    frames=generate(args.scenario,ROOT/'outputs/python_sim'/args.scenario)
    if args.tk:show(frames)
    elif args.show:
        import webbrowser
        webbrowser.open((ROOT/'outputs/python_sim'/args.scenario/'player.html').as_uri())


if __name__=='__main__':main()
