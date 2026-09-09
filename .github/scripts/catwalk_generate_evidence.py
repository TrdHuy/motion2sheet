import json, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'sample/humanoid_motion/mixamo/catwalk-walk'
OUT = SRC
with open(SRC / 'animation.json', encoding='utf-8') as f:
    anim = json.load(f)
gif = Image.open(SRC / 'preview.gif')
hips = anim['hips']['translations']

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
F_TITLE = ImageFont.truetype(BOLD, 28)
F_SECTION = ImageFont.truetype(BOLD, 21)
F_LABEL = ImageFont.truetype(BOLD, 18)
F_TEXT = ImageFont.truetype(FONT, 15)
F_SMALL = ImageFont.truetype(FONT, 13)

def frame(i):
    gif.seek(i)
    return gif.convert('RGB')

def center(d, box, text, font, fill='black'):
    x0,y0,x1,y1=box
    bb=d.textbbox((0,0),text,font=font)
    d.text(((x0+x1-(bb[2]-bb[0]))/2,(y0+y1-(bb[3]-bb[1]))/2),text,font=font,fill=fill)

def wrap(d,text,font,w):
    lines=[]; cur=''
    for word in text.split():
        t=word if not cur else cur+' '+word
        if d.textbbox((0,0),t,font=font)[2] <= w: cur=t
        else:
            if cur: lines.append(cur)
            cur=word
    if cur: lines.append(cur)
    return lines

def q_euler_xyz_deg(q):
    w,x,y,z=q
    # standard quaternion -> XYZ Euler
    sinr=2*(w*x+y*z); cosr=1-2*(x*x+y*y)
    rx=math.atan2(sinr,cosr)
    sinp=2*(w*y-z*x)
    ry=math.copysign(math.pi/2,sinp) if abs(sinp)>=1 else math.asin(sinp)
    siny=2*(w*z+x*y); cosy=1-2*(y*y+z*z)
    rz=math.atan2(siny,cosy)
    return tuple(math.degrees(v) for v in (rx,ry,rz))

def root_yaws():
    raw=[q_euler_xyz_deg(q)[2] for q in anim['root']['rotations']]
    out=[raw[0]]
    for a in raw[1:]:
        prev=out[-1]
        k=round((prev-a)/360.0)
        cand=a+360*k
        if cand-prev>180: cand-=360
        elif cand-prev<-180: cand+=360
        out.append(cand)
    return out
YAW=root_yaws()

def path_len(a,b):
    s=0.0
    for i in range(a,b):
        dx=hips[i+1][0]-hips[i][0]; dy=hips[i+1][1]-hips[i][1]
        s += math.hypot(dx,dy)
    return s

def joint_z(j,f):
    return q_euler_xyz_deg(anim['joints'][j]['rotations'][f])[2]

# phases.png
phases=[(0,148,'outbound catwalk'),(149,240,'presentation U-turn to rear'),(241,370,'rear-facing return catwalk'),(371,418,'fast pivot back to front'),(419,454,'settle / loop closure')]
W=1000; header=78; rh=278
im=Image.new('RGB',(W,header+rh*len(phases)+30),'white'); d=ImageDraw.Draw(im)
d.text((24,18),'phases — exact boundary frames',font=F_TITLE,fill='black')
d.text((24,52),f"Frame indices come from animation.json ({anim['frameCount']} frames @ {anim['fps']:.0f} FPS).",font=F_SMALL,fill=(50,50,50))
for r,(a,b,label) in enumerate(phases):
    y=header+r*rh
    if r: d.line((20,y,W-20,y),fill=(210,210,210),width=1)
    d.text((28,y+22),f'f{a}–f{b}',font=F_SECTION,fill='black')
    x1,x2,iy=220,700,y+32
    im.paste(frame(a),(x1,iy)); im.paste(frame(b),(x2,iy))
    center(d,(x1,y+4,x1+224,y+30),f'f{a}',F_LABEL); center(d,(x2,y+4,x2+224,y+30),f'f{b}',F_LABEL)
    d.line((x1+238,iy+112,x2-16,iy+112),fill=(70,70,70),width=3)
    d.polygon([(x2-16,iy+112),(x2-30,iy+104),(x2-30,iy+120)],fill=(70,70,70))
    yy=iy+130
    for line in wrap(d,label,F_TEXT,230): center(d,(x1+240,yy,x2-15,yy+22),line,F_TEXT); yy+=21
im.save(OUT/'phases.png')

# key-poses.png
poses=[(0,'opening hand-on-hip stance'),(129,'cross-step + lateral hip-sway accent'),(192,'held presentation pose in U-turn'),(240,'rear-facing turn completion'),(405,'front-facing alignment in fast pivot'),(454,'loop closure: opening pose restored')]
cw,ch=330,310; header=74
im=Image.new('RGB',(990,header+620),'white'); d=ImageDraw.Draw(im)
d.text((24,17),'key-poses — selected motion beats',font=F_TITLE,fill='black')
d.text((24,50),'Only frames with a distinct structural or narrative role are included.',font=F_SMALL,fill=(50,50,50))
for i,(f,role) in enumerate(poses):
    c=i%3; r=i//3; x0=c*cw; y0=header+r*ch
    if c: d.line((x0,y0+12,x0,header+620-12),fill=(225,225,225),width=1)
    if r: d.line((0,y0,990,y0),fill=(225,225,225),width=1)
    center(d,(x0,y0+8,x0+cw,y0+34),f'f{f}',F_LABEL)
    fx=x0+(cw-224)//2; fy=y0+38; im.paste(frame(f),(fx,fy))
    yy=fy+230
    for line in wrap(d,role,F_TEXT,cw-30)[:2]: center(d,(x0+10,yy,x0+cw-10,yy+20),line,F_TEXT); yy+=20
im.save(OUT/'key-poses.png')

# weight-transfer.png
wf=[84,94,117,129]
im=Image.new('RGB',(1100,455),'white'); d=ImageDraw.Draw(im)
d.text((24,16),'weight-transfer — alternating lateral pelvis shift',font=F_TITLE,fill='black')
d.text((24,50),'Hips X is from animation.json; +X is right in the canonical coordinate system.',font=F_SMALL,fill=(50,50,50))
for i,f in enumerate(wf):
    x0=30+i*260; iy=95
    center(d,(x0,iy-28,x0+224,iy-4),f'f{f}',F_LABEL); im.paste(frame(f),(x0,iy))
    center(d,(x0,iy+230,x0+224,iy+254),f'Hips X = {hips[f][0]:+.3f} MLL',F_TEXT)
    center(d,(x0,iy+257,x0+224,iy+281),'right shift' if hips[f][0]>0 else 'left shift',F_SMALL)
    if i<3:
        ax,bx,ay=x0+226,x0+252,iy+112; d.line((ax,ay,bx,ay),fill=(80,80,80),width=3); d.polygon([(bx,ay),(bx-10,ay-6),(bx-10,ay+6)],fill=(80,80,80))
d.line((30,395,1070,395),fill=(210,210,210),width=1)
d.text((30,410),'Alternating right/left Hips-X extrema support lateral weight transfer.',font=F_SMALL,fill=(30,30,30))
d.text((30,430),'Support-foot labels are intentionally omitted because the source has no explicit foot-contact events.',font=F_SMALL,fill=(30,30,30))
im.save(OUT/'weight-transfer.png')

# body-mechanics.png
im=Image.new('RGB',(1180,1180),'white'); d=ImageDraw.Draw(im)
d.text((24,16),'body-mechanics — gait coupling and turn construction',font=F_TITLE,fill='black')
d.text((24,50),'Local rotations are rest-relative; root yaw represents scene heading.',font=F_SMALL,fill=(50,50,50))
a=90; d.text((24,a),'A. Catwalk stride: pelvis shift couples with alternating spine/chest axial rotation',font=F_SECTION,fill='black')
for i,f in enumerate(wf):
    x0=24+i*280; y=a+42; center(d,(x0,y-4,x0+224,y+20),f'f{f}',F_LABEL); im.paste(frame(f),(x0,y+22))
    d.text((x0,y+252),f'Hips X {hips[f][0]:+.3f} MLL',font=F_SMALL,fill='black')
    d.text((x0,y+273),f"Spine Z {joint_z('Spine',f):+.1f}° | Chest Z {joint_z('Chest',f):+.1f}°",font=F_SMALL,fill='black')
d.line((20,445,1160,445),fill=(205,205,205),width=1)

b=462; d.text((24,b),'B. First turn: wide translated U-turn with a presentation hold',font=F_SECTION,fill='black')
xbase=50; cw=360; y=b+42
for i,(f,lab) in enumerate(zip([149,192,240],['turn entry','presentation hold','rear-facing exit'])):
    x0=xbase+i*cw; center(d,(x0,y-2,x0+224,y+22),f'f{f} — {lab}',F_SMALL); im.paste(frame(f),(x0,y+26)); d.text((x0,y+253),f'root yaw {YAW[f]:+.1f}°',font=F_SMALL,fill='black')
d.text((24,b+310),f'f149→f240: hips path {path_len(149,240):.2f} MLL; heading change {YAW[240]-YAW[149]:.1f}°.',font=F_SMALL,fill=(30,30,30))
d.line((20,810,1160,810),fill=(205,205,205),width=1)

c=827; d.text((24,c),'C. Second turn: tight near-in-place pivot back to front',font=F_SECTION,fill='black'); y=c+42
for i,(f,lab) in enumerate(zip([371,395,405],['pivot start','rapid-turn midpoint','front alignment'])):
    x0=xbase+i*cw; center(d,(x0,y-2,x0+224,y+22),f'f{f} — {lab}',F_SMALL); im.paste(frame(f),(x0,y+26)); d.text((x0,y+253),f'root yaw {YAW[f]:+.1f}°',font=F_SMALL,fill='black')
d.text((24,c+310),f'f371→f405: hips path {path_len(371,405):.2f} MLL; heading change {YAW[405]-YAW[371]:.1f}°.',font=F_SMALL,fill=(30,30,30))
d.text((24,c+331),'The first turnaround travels broadly; the second achieves a similar heading change with much less pelvis travel.',font=F_SMALL,fill=(30,30,30))
im.save(OUT/'body-mechanics.png')

for name in ['phases.png','key-poses.png','weight-transfer.png','body-mechanics.png']:
    print(name, (OUT/name).stat().st_size)
