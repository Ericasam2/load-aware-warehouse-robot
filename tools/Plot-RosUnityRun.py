"""Render planned and measured paths from a completed joint run."""
import csv
import json
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
out = root / 'outputs/ros_unity'
report = json.loads((out/'run_report.json').read_text())
planned = json.loads((out/'planned_path.json').read_text())
scene = json.loads((root/'maps/scene_geometry.json').read_text(encoding='utf-8-sig'))
with (out/'actual_trajectory.csv').open() as f:
    rows = list(csv.DictReader(f))
image = Image.new('RGB',(900,900),'#eaf0f5')
d = ImageDraw.Draw(image)
def pixel(x,y): return (round((x+9)*40+90),round((10-y)*40+70))
for solid in scene['obstacles']:
    lo,hi=solid['min'],solid['max']
    x1,y1=pixel(lo[0],hi[1]);x2,y2=pixel(hi[0],lo[1])
    d.rectangle((x1,y1,x2,y2),fill='#99a8b6')
points=[pixel(*p[:2]) for p in planned['poses']]
if len(points)>1:d.line(points,fill='#246ada',width=6)
points=[pixel(float(p['map_x']),float(p['map_y'])) for p in rows]
if len(points)>1:d.line(points,fill='#07a366',width=2)
d.text((20,12),'ROS 2 + UNITY PHYSICS | '+report['status'],fill='#102030')
d.text((20,30),'Blue: A* planned | Green: measured odometry | Gray: geometry including overhead',fill='#102030')
d.text((20,48),f"Final error: {report['position_error_m']:.4f} m | yaw: {report['yaw_error_rad']:.4f} rad",fill='#102030')
for label,p in [('Start',planned['requested_start']),('P1',planned['poses'][-1])]:
    x,y=pixel(*p[:2]);d.ellipse((x-4,y-4,x+4,y+4),fill='#dd493d');d.text((x+8,y+8),label,fill='#102030')
image.save(out/'trajectory-comparison.png')
