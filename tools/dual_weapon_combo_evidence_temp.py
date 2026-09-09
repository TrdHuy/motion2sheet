import json, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path('sample/humanoid_motion/mixamo/dual-weapon-combo')
anim = json.loads((root/'animation.json').read_text())
gif = Image.open(root/'preview.gif')
assert anim['frameCount'] == 110 and anim['fps'] == 30.0
assert gif.n_frames == anim['frameCount'], (gif.n_frames, anim['frameCount'])

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
def fnt(n, bold=False):
    try: return ImageFont.truetype(BOLD if bold else FONT, n)
    except: return ImageFont.load_default()

def frame(i):
    gif.seek(i)
    return gif.convert('RGB').copy()

def wrap(draw, text, font, width):
    words=text.split(); lines=[]; cur=''
    for w in words:
        trial=(cur+' '+w).strip()
        if draw.textbbox((0,0),trial,font=font)[2] <= width: cur=trial
        else:
            if cur: lines.append(cur)
            cur=w
    if cur: lines.append(cur)
    return '\n'.join(lines)

def contact_sheet(title, subtitle, items, cols, out, footer=None, panel=224, text_h=78):
    margin=24; rows=(len(items)+cols-1)//cols
    w=margin*2+cols*panel; header=88
    h=header+rows*(panel+text_h)+margin+(28 if footer else 0)
    im=Image.new('RGB',(w,h),'white'); d=ImageDraw.Draw(im)
    d.text((margin,16),title,font=fnt(30,True),fill='black')
    d.text((margin,54),subtitle,font=fnt(17),fill=(50,50,50))
    y0=header
    for idx,(fi,label,note) in enumerate(items):
        r,c=divmod(idx,cols); x=margin+c*panel; y=y0+r*(panel+text_h)
        p=frame(fi).resize((panel,panel)); im.paste(p,(x,y))
        if c: d.line((x,y,x,y+panel),fill=(140,140,140),width=1)
        ty=y+panel+5
        d.text((x+6,ty),f'f{fi}',font=fnt(17,True),fill='black')
        d.text((x+6,ty+21),wrap(d,label,fnt(15,True),panel-12),font=fnt(15,True),fill='black',spacing=2)
        if note:
            d.text((x+6,ty+42),wrap(d,note,fnt(12),panel-12),font=fnt(12),fill=(45,45,45),spacing=1)
    if footer: d.text((margin,h-25),footer,font=fnt(13),fill=(55,55,55))
    im.save(root/out)

phase_items=[
    (0,'guarded prep start',''),(13,'guarded load end','boundary'),
    (14,'broad attack starts','boundary'),(44,'first arc settles','boundary'),
    (45,'compact attack starts','boundary'),(59,'compact strike settles','boundary'),
    (60,'overhead re-chamber','boundary'),(71,'crossed overhead apex','boundary'),
    (72,'finishing release','boundary'),(84,'wide finish settles','boundary'),
    (85,'recovery starts','boundary'),(109,'guard recovered','')]
contact_sheet('phases — dual-weapon-combo',
              'Frame indices come from animation.json; preview.gif supplies only the rendered pose view.',
              phase_items,4,'phases.png',
              'Boundary pairs: 13/14, 44/45, 59/60, 71/72, 84/85. Source: 110 frames @ 30 FPS.')

key_items=[
    (0,'guard-ready','baseline fighting stance'),
    (28,'high unilateral wind-up','one arm reaches overhead while the opposite arm stays lower'),
    (42,'first long extension','extended attack/follow-through silhouette'),
    (54,'second lateral extension','opposite attack arc reaches a long lateral line'),
    (71,'crossed overhead wind-up','both arms gathered high before final release'),
    (80,'broad bilateral finish','both arms open wide at the finishing extension'),
    (109,'recovered guard','returns to the initial guarded stance')]
contact_sheet('key poses — dual-weapon-combo',
              'Only poses that materially define the combo silhouette or transition are included.',
              key_items,4,'key-poses.png')

trans=anim['hips']['translations']
xs=[p[0] for p in trans]; ys=[p[1] for p in trans]; zs=[p[2] for p in trans]
extrema=[(0,'start'),(42,'max backward Y'),(75,'max forward (-Y)'),(80,'max left (-X)'),(86,'lowest pelvis Z'),(109,'return ≈ start')]
W,H=1128,818; m=24
im=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(im)
d.text((m,16),'weight transfer — pelvis evidence',font=fnt(30,True),fill='black')
d.text((m,54),'Canonical axes: +X right, -Y forward, +Z up. No support-foot claim is made.',font=fnt(17),fill=(50,50,50))
pw=(W-2*m)//6; top=90
for j,(fi,label) in enumerate(extrema):
    x=m+j*pw; p=frame(fi).resize((pw,pw)); im.paste(p,(x,top))
    if j: d.line((x,top,x,top+pw),fill=(140,140,140))
    tx=x+4; y=top+pw+5
    d.text((tx,y),f'f{fi}  {label}',font=fnt(12),fill='black')
    d.text((tx,y+18),f'X {xs[fi]:+.3f}  Y {ys[fi]:+.3f}\nZ {zs[fi]:+.3f}',font=fnt(11),fill=(50,50,50))
plot_y=360; plot_h=405; gap=24; plot_w=(W-2*m-gap)//2
boxes=[(m,plot_y,m+plot_w,plot_y+plot_h),(m+plot_w+gap,plot_y,W-m,plot_y+plot_h)]
for b in boxes: d.rectangle(b,outline=(90,90,90),width=1)
d.text((boxes[0][0]+12,plot_y+10),'Pelvis ground-plane path (X vs Y)',font=fnt(18,True),fill='black')
d.text((boxes[1][0]+12,plot_y+10),'Pelvis height Z by frame',font=fnt(18,True),fill='black')
def norm(v,a,b,p0,p1): return p0+(v-a)/(b-a)*(p1-p0) if b!=a else (p0+p1)/2
bx=boxes[0]; xa,xb=min(xs),max(xs); ya,yb=min(ys),max(ys)
pts=[]
for x,y in zip(xs,ys):
    px=norm(x,xa,xb,bx[0]+45,bx[2]-35); py=norm(y,ya,yb,bx[1]+55,bx[3]-45); pts.append((px,py))
d.line(pts,fill=(35,35,35),width=2)
for fi in [0,42,75,80,86,109]:
    px,py=pts[fi]; d.ellipse((px-5,py-5,px+5,py+5),fill='white',outline='black',width=2); d.text((px+6,py-8),f'f{fi}',font=fnt(11),fill='black')
d.text((bx[0]+44,bx[1]+33),'↑ forward (-Y)',font=fnt(13),fill=(60,60,60))
d.text((bx[0]+44,bx[3]-35),'-X left ←              → +X right',font=fnt(13),fill=(60,60,60))
bz=boxes[1]; za,zb=min(zs),max(zs); zpts=[]
for i,z in enumerate(zs):
    px=norm(i,0,109,bz[0]+45,bz[2]-25); py=norm(z,zb,za,bz[1]+55,bz[3]-40); zpts.append((px,py))
d.line(zpts,fill=(35,35,35),width=2)
for fi in [0,30,86,109]:
    px,py=zpts[fi]; d.ellipse((px-5,py-5,px+5,py+5),fill='white',outline='black',width=2); d.text((px+5,py-8),f'f{fi}',font=fnt(11),fill='black')
d.text((bz[0]+45,bz[1]+33),f'higher  (max f{max(range(110),key=lambda i:zs[i])} Z={max(zs):+.3f})',font=fnt(13),fill=(60,60,60))
d.text((bz[0]+45,bz[3]-35),f'lower   (min f{min(range(110),key=lambda i:zs[i])} Z={min(zs):+.3f})',font=fnt(13),fill=(60,60,60))
d.text((m,H-24),'Data conclusion: backward excursion peaks at f42; pelvis then drives forward-left through f75–f80, lowers through f86, and returns to the start by f109.',font=fnt(13),fill=(45,45,45))
im.save(root/'weight-transfer.png')

def qdelta(q1,q2):
    dot=sum(a*b for a,b in zip(q1,q2)); dot=max(-1,min(1,abs(dot)))
    return math.degrees(2*math.acos(dot))
def rot(name): return anim['hips']['rotations'] if name=='Hips' else anim['joints'][name]['rotations']
def dq(name,i): return qdelta(rot(name)[i],rot(name)[i+1])
body=[
    (17,'LeftUpperArm initiates',f'Δθ f17→18 = {dq("LeftUpperArm",17):.1f}°'),
    (20,'LeftLowerArm follows',f'Δθ f20→21 = {dq("LeftLowerArm",20):.1f}°'),
    (21,'LeftHand distal peak',f'Δθ f21→22 = {dq("LeftHand",21):.1f}°'),
    (28,'Hips rotation rises',f'Δθ f28→29 = {dq("Hips",28):.1f}°'),
    (29,'Spine + right shoulder',f'{dq("Spine",29):.1f}° / {dq("RightShoulder",29):.1f}°'),
    (30,'Chest rotation peak',f'Δθ f30→31 = {dq("Chest",30):.1f}°'),
    (32,'Right distal-arm release',f'forearm {dq("RightLowerArm",32):.1f}°; hand {dq("RightHand",32):.1f}°'),
    (34,'RightUpperArm follows',f'Δθ f34→35 = {dq("RightUpperArm",34):.1f}°'),
    (71,'Final overhead cross','visible wind-up apex / phase boundary'),
    (80,'Broad bilateral finish',f'RightUpperArm Δθ f80→81 = {dq("RightUpperArm",80):.1f}°')]
contact_sheet('body mechanics — coordination order',
              'Local quaternion Δθ comes from animation.json; pose panels show the same sequence indices.',
              body,5,'body-mechanics.png',
              'Observed pattern: left arm initiates → trunk/right-shoulder turn → right distal-arm release; final action re-chambers overhead, then opens into a broad two-arm finish.')
