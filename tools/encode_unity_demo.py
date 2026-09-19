"""Encode real Unity camera frames using their recorded wall-clock timestamps."""
import csv
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/unity-basic'
sys.path.insert(0,str(ROOT/'outputs/demo_dependencies'))
import imageio_ffmpeg

report=json.loads((OUT/'run_report.json').read_text(encoding='utf-8-sig'))
if not report.get('passed'):raise RuntimeError('Cannot label a failed run as a completed demo')
with (OUT/'frames/timestamps.csv').open() as f:rows=list(csv.DictReader(f))
times=np.array([float(r['elapsed_seconds']) for r in rows])
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',22)
small=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',16)
def picture(t,speed):
    index=int(np.clip(np.searchsorted(times,t,side='right')-1,0,len(rows)-1))
    source=Image.open(OUT/'frames'/f'frame-{int(rows[index]["frame"]):06d}.jpg').convert('RGB')
    canvas=Image.new('RGB',(960,640),'#111d30');canvas.paste(source,(0,64))
    d=ImageDraw.Draw(canvas)
    d.text((20,9),'UNITY + ROS 2  |  Empty robot to P1',font=font,fill='white')
    d.text((20,38),f'Actual Unity camera recording  |  {speed}x playback  |  {t:.1f} s',font=small,fill='#b9d2e5')
    d.text((20,614),f'Run result: SUCCESS  |  Final grid-goal error: {report["position_error_m"]*100:.2f} cm  |  Physical wheel drive',font=small,fill='#7ee3c3')
    return canvas

fps=12
video=OUT/'unity-basic-demo.mp4'
ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
process=subprocess.Popen([ffmpeg,'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','960x640','-r',str(fps),'-i','-','-an','-c:v','libx264','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=subprocess.PIPE)
for t in np.arange(times[0],times[-1],1/fps):process.stdin.write(picture(float(t),1).tobytes())
process.stdin.close()
if process.wait()!=0:raise RuntimeError('MP4 encoding failed')
gif=[picture(float(t),3).resize((720,480),Image.Resampling.LANCZOS) for t in np.arange(times[0],times[-1],.3)]
gif[0].save(OUT/'unity-basic-demo-3x.gif',save_all=True,append_images=gif[1:],duration=100,loop=0,optimize=False)
picture(float(times[len(times)//2]),1).save(OUT/'preview.png')
subprocess.run([ffmpeg,'-v','error','-i',str(video),'-f','null','-'],check=True)
(OUT/'recording-info.json').write_text(json.dumps(dict(source='Unity Camera.Render during ROS-controlled Play Mode',rendering='Direct3D 11',raw_frames=len(rows),duration_seconds=float(times[-1]-times[0]),mp4_fps=fps,gif_playback_speed=3,video_decode='PASS',result=report),indent=2))
(OUT/'index.html').write_text('''<!doctype html><meta charset="utf-8"><title>Unity ROS 2 Basic Demo</title><style>body{max-width:960px;margin:30px auto;background:#111d30;color:white;font:17px system-ui}video,img{width:100%}a{color:#7ee3c3}</style><h1>Unity + ROS 2 Basic Demo</h1><p>Empty robot: start to P1, then stop. Actual Unity camera capture of physical wheel motion.</p><video controls preload="metadata" poster="preview.png" src="unity-basic-demo.mp4"></video><p><a href="unity-basic-demo-3x.gif">3x animated GIF</a> | <a href="run_report.json">Run verification</a></p>''',encoding='utf-8')
print(json.dumps(dict(raw_frames=len(rows),duration_seconds=float(times[-1]-times[0]),video_decode='PASS')))
