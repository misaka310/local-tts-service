#!/usr/bin/env python3
"""Combine 14 SAPI narration WAVs at the start of their scene windows."""
import json, wave
from array import array
from pathlib import Path
ROOT=Path(__file__).resolve().parent
scenes=json.loads((ROOT/'storyboard.json').read_text(encoding='utf-8'))
hz=22050
duration=sum(float(s['seconds']) for s in scenes)
buffer=array('h',[0])*int(hz*duration)
start=0.
for i,scene in enumerate(scenes):
    p=ROOT/'narration'/f'narration_{i:02d}.wav'
    with wave.open(str(p),'rb') as f:
        assert f.getframerate()==hz and f.getsampwidth()==2 and f.getnchannels()==1, p
        clip=array('h');clip.frombytes(f.readframes(f.getnframes()))
    at=int((start+0.8)*hz)
    upper=min(len(buffer),int((start+float(scene['seconds'])-.25)*hz))
    for n,s in enumerate(clip):
        j=at+n
        if j>=upper:break
        buffer[j]=int(max(-32768,min(32767,buffer[j]+s*.92)))
    print(f'{i:02d} narration={len(clip)/hz:.2f}s scene={scene["seconds"]}s')
    start+=float(scene['seconds'])
with wave.open(str(ROOT/'narration_timeline.wav'),'wb') as f:
    f.setnchannels(1);f.setsampwidth(2);f.setframerate(hz);f.writeframes(buffer.tobytes())
print('WROTE',ROOT/'narration_timeline.wav')
