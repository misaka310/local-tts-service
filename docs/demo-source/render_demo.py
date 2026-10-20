#!/usr/bin/env python3
"""Recreated README tutorial. Scene script is in storyboard.json.
Requires Pillow and ffmpeg. Produces a captioned, soundtrack-only preview.
The original narration/actual desktop capture were lost with the untracked project.
"""
from pathlib import Path
import json, math, subprocess, wave, struct
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
W,H=854,480
FONT='/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
BOLD='/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'

def font(size,bold=False):
    try:return ImageFont.truetype(BOLD if bold else FONT,size)
    except: return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',size)
def txt(d,xy,s,size=22,fill='#273653',bold=False,anchor=None):
    d.text(xy,s,font=font(size,bold),fill=fill,anchor=anchor,stroke_width=0)
def rrect(d,box,r=14,fill='#ffffff',outline=None,width=1): d.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)
def chip(d,box,label,color='#d7e8ff',text='#2460b8'):
    rrect(d,box,11,color)
    txt(d,(box[0]+12,(box[1]+box[3])//2),label,14,text,True,'lm')
def cat(d,cx=772,cy=304,blink=False,mouth=True):
    # copyright-free geometric illustration made by this script
    d.ellipse((cx-49,cy-35,cx+49,cy+52),fill='#343b56')
    d.polygon([(cx-41,cy-13),(cx-37,cy-66),(cx-2,cy-34)],fill='#343b56')
    d.polygon([(cx+41,cy-13),(cx+37,cy-66),(cx+2,cy-34)],fill='#343b56')
    d.polygon([(cx-33,cy-28),(cx-30,cy-49),(cx-11,cy-31)],fill='#e6a0aa')
    d.polygon([(cx+33,cy-28),(cx+30,cy-49),(cx+11,cy-31)],fill='#e6a0aa')
    if blink:
        for dx in (-23,23): d.line((cx+dx-10,cy,cx+dx+10,cy),fill='#e9eefc',width=3)
    else:
        for dx in (-23,23):
            d.ellipse((cx+dx-9,cy-10,cx+dx+9,cy+13),fill='#f9e3a6')
            d.ellipse((cx+dx-3,cy-8,cx+dx+3,cy+12),fill='#283049')
    d.polygon([(cx-5,cy+20),(cx+5,cy+20),(cx,cy+26)],fill='#e9a1b2')
    if mouth:d.arc((cx-9,cy+21,cx+9,cy+35),start=5,end=175,fill='#f2cad5',width=2)
    for y in (cy+20,cy+29):
        d.line((cx-15,y,cx-48,y-4),fill='#e7d5db',width=2)
        d.line((cx+15,y,cx+48,y-4),fill='#e7d5db',width=2)

def generate_slide(scene,i,n):
    im=Image.new('RGB',(W,H),'#e9eef7');d=ImageDraw.Draw(im)
    d.rectangle((0,0,W,7),fill='#5275dd')
    rrect(d,(24,22,830,382),20,'#ffffff','#d5def0',2)
    rrect(d,(24,22,830,75),19,'#253453')
    d.rectangle((24,58,830,75),fill='#253453')
    d.ellipse((41,42,53,54),fill='#89e2bb')
    d.ellipse((60,42,72,54),fill='#ffd781')
    d.ellipse((79,42,91,54),fill='#f3a6aa')
    txt(d,(111,49),'local-tts-service',20,'#ffffff',True,'lm')
    chip(d,(657,39,809,63),'Qwen3-TTS / Demo','#38527f','#d4e5ff')
    rrect(d,(40,88,188,364),12,'#f1f5fc')
    txt(d,(57,113),'メニュー',18,'#63738a',True)
    menus=['通常生成','モデル比較','参照音声','RVC 声質変換']
    selected=scene.get('menu',0)
    for k,label in enumerate(menus):
        y=157+k*42
        if k==selected:rrect(d,(49,y-8,179,y+30),10,'#dae7ff')
        txt(d,(62,y),('● ' if k==selected else '○ ')+label,15,'#2454a0' if k==selected else '#5e708b',k==selected)
    x0=210
    txt(d,(x0,99),scene['title'],25,'#203756',True)
    txt(d,(x0,131),scene['detail'],14,'#78879e')
    typ=scene['type']
    if typ=='intro':
        txt(d,(230,179),'声を選ぶ、言葉を入力する。',23,'#2b528d',True)
        txt(d,(230,225),'日本語の音声をローカルで生成',19,'#39536f')
        chip(d,(225,278,466,311),'1.7B  Voice Clone')
    elif typ in ('launch','select'):
        chip(d,(226,166,431,200),'モデルの選択','#e4edff','#2a5ec1')
        rrect(d,(223,211,603,255),10,'#f9fbff','#bacce9')
        txt(d,(237,232),'Qwen3-TTS 1.7B (Voice Clone)',17,'#25456a',True,'lm')
        txt(d,(578,232),'▾',20,'#4f74ac',False,'mm')
        if typ=='select':
            rrect(d,(223,258,601,312),10,'#dce9ff')
            txt(d,(240,285),'✓  参照音声で声質を再現するモデル',14,'#3665a1',True,'lm')
    elif typ in ('ref','reftext'):
        chip(d,(225,164,412,196),'参照音声 (WAV)')
        rrect(d,(225,205,611,244),10,'#f9fbff','#bed0e5')
        txt(d,(238,224),'voice.wav   ✓ 読み込み済み',16,'#356087',True,'lm')
        chip(d,(225,257,448,286),'対応する書き起こし', '#eff1ff','#655cbd')
        rrect(d,(225,293,612,333),9,'#f9fbff','#bed0e5')
        txt(d,(239,312),'voice.txt  / 参照文を登録',15,'#39556e',False,'lm')
    elif typ in ('prompt','generate'):
        chip(d,(226,167,435,198),'生成する文章')
        rrect(d,(225,209,624,292),12,'#f9fbff','#bed0e5')
        txt(d,(237,231),'こんにちは。音声生成を試してみましょう。',15,'#2f526e')
        rrect(d,(472,309,620,347),10,'#4269d1' if typ=='generate' else '#98b2e7')
        txt(d,(546,328),'生成する ▶',17,'#ffffff',True,'mm')
    elif typ=='progress':
        chip(d,(225,171,473,206),'音声を生成しています')
        rrect(d,(228,236,630,258),10,'#e3eaf6')
        rrect(d,(228,236,518,258),10,'#6588e3')
        txt(d,(228,284),'生成状況と経過時間を確認できます。',16,'#50617a')
    elif typ in ('listen','cat'):
        chip(d,(223,167,407,200),'生成音声プレビュー')
        rrect(d,(222,212,613,290),12,'#f7faff','#c7d8ec')
        d.ellipse((240,233,281,274),fill='#4269d1');txt(d,(260,253),'▶',18,'#fff',True,'mm')
        for q in range(40):
            h=9+int(20*abs(math.sin(q*2.17)))
            xx=306+q*7
            d.line((xx,253-h//2,xx,253+h//2),fill='#6a91d7',width=3)
        txt(d,(241,323),'音声：あみたろ様（元作品の表示例）',14,'#7b6673')
    elif typ=='save':
        chip(d,(225,174,397,205),'音声ファイルを保存')
        rrect(d,(223,224,586,280),11,'#4269d1')
        txt(d,(404,252),'↓   WAVをダウンロード',19,'#ffffff',True,'mm')
        txt(d,(232,310),'生成した音声はPCに保存できます。',15,'#4e647c')
    elif typ=='compare':
        for q,(lab,co) in enumerate([('Qwen3-TTS','#4876da'),('Irodori v3','#38a6a0')]):
            y=185+64*q;rrect(d,(225,y,618,y+50),12,'#f4f7fc','#ccd8e7')
            rrect(d,(238,y+10,249,y+39),4,co)
            txt(d,(263,y+14),lab,17,'#3b5069',True)
            txt(d,(561,y+25),'▶',18,co,True,'mm')
    elif typ=='end':
        txt(d,(265,195),'ご覧いただき',24,'#294d80',True)
        txt(d,(265,241),'ありがとうございました。',24,'#294d80',True)
        chip(d,(263,296,485,330),'GitHubでセットアップへ')
    cat(d,753,298,blink=i in (3,9,12),mouth=typ not in ('listen','cat'))
    # Subtitle bar and progress
    rrect(d,(24,391,830,460),13,'#253453')
    txt(d,(45,401),f'{i+1:02d} / {n:02d}   {scene["heading"]}',14,'#8ab2ef',True)
    txt(d,(45,430),scene['subtitle'],20,'#ffffff',True,anchor='lm')
    d.rectangle((25,474,25+round((i+1)/n*805),480),fill='#6b8dff')
    return im

def soundtrack(path,duration):
    # Soft sound bed only; this is not a replacement for the deleted narrator audio.
    import numpy as np
    sr=22050
    with wave.open(str(path),'wb') as wf:
        wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(sr)
        n=int(duration*sr);block=sr*2
        for start in range(0,n,block):
            sz=min(block,n-start)
            t=np.arange(start,start+sz,dtype=np.float64)/sr
            base=np.zeros(sz,dtype=np.float64)
            for hz,amp in ((196,.31),(246.94,.19),(293.66,.16),(392,.10)):
                base+=amp*np.sin(2*np.pi*hz*t)
            pulse=(.45+.55*np.maximum(0,np.sin(2*np.pi*.22*t)))
            fade=np.minimum(1,t/2)*np.minimum(1,np.maximum(0,duration-t)/2)
            a=np.clip(base*pulse*fade*.05,-.95,.95)
            wf.writeframes((a*32767).astype('<i2').tobytes())

def main():
    scenes=json.loads((ROOT/'storyboard.json').read_text(encoding='utf-8'))
    out=ROOT/'slides';out.mkdir(exist_ok=True)
    lines=['ffconcat version 1.0']
    for i,scene in enumerate(scenes):
        name=f'scene_{i:02d}.png';generate_slide(scene,i,len(scenes)).save(out/name,optimize=True)
        lines+=['file '+name, 'duration '+str(scene['seconds'])]
    lines.append('file scene_'+f'{len(scenes)-1:02d}.png')
    (out/'slides.ffconcat').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    duration=sum(s['seconds'] for s in scenes)
    soundtrack(ROOT/'soundbed.wav',duration)
    video=ROOT/'local-tts-qwen3-1.7b-cat-rebuilt-preview.mp4'
    cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','concat','-safe','0','-i',str(out/'slides.ffconcat'),'-i',str(ROOT/'soundbed.wav'),'-vf','fps=15,format=yuv420p','-c:v','libx264','-preset','medium','-crf','27','-c:a','aac','-b:a','48k','-movflags','+faststart','-t',str(duration),str(video)]
    subprocess.run(cmd,check=True)
    print(video,video.stat().st_size,'bytes',duration,'seconds')
if __name__=='__main__':main()
