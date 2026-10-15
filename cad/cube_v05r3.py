# Tamagroki cube v0.5 - back-loading sleeve + snap-latch back cover.
# Axes: X right (seen from front), Z up, Y toward back. Front face Y=0. Units mm.
# FIX vs v0.3b/c: nothing in the sleeve between its back opening and the front lip; the
# stock case slides in from the back. Back cover retains it with 4 corner press posts and
# 2 flexible snap arms (left/right walls, low, clear of grille + mics) that hook into
# windows recessed in the sleeve side walls. Arms sit flush in recessed channels.
import cadquery as cq, json, os
CASE=46.0; CD=22.5; CR=5.8; CL=0.3
W=2.5; S=CASE+2*CL+2*W; H=S/2          # 51.6
RO=CR+CL+W
LIP=0.2+12*0.12; WIN=41.8; WR=4.0; CH=0.6   # v0.5r2: 1.64 lip, 2.4 ring, 45deg outer chamfer
FF=1.6; BF=3.0
cy0=LIP; cyb=CD+cy0                   # case front/back Y (22.81)
BAT=(40.0,8.0,30.0)
by0=cyb+1.0; D=by0+BAT[1]+0.5+W        # 34.81
YS=cyb+0.5                             # sleeve/cover split, 0.5 behind case back
PG=0.1                                 # press-post gap to case back (nominal)
# snap arm parameters
L=13.0; T=1.4; AW=7.5; ZA0=-16.5; ZA1=ZA0+AW   # arm length/thickness/width, z band
HK=0.9; OVL=0.7; RAMP=1.2; HL=1.8; CLR=0.2; SCL=0.3; PLAY=0.15
yt=YS-L                                 # arm tip Y
def rsq(w,h,r,y0,d,cx=0,cz=0):
    return cq.Workplane("XZ",origin=(0,y0,0)).center(cx,cz).rect(w,h).extrude(-d).edges("|Y").fillet(r)
def box(x0,x1,y0,y1,z0,z1):
    return cq.Workplane().box(abs(x1-x0),abs(y1-y0),abs(z1-z0)).translate(((x0+x1)/2,(y0+y1)/2,(z0+z1)/2))
outer=rsq(S,S,RO,0,D).faces("<Y").edges().fillet(FF).faces(">Y").edges().fillet(BF)
pocketw=CASE+2*CL; pr=CR+CL; PI=pocketw/2      # 23.3
# ---------------- sleeve ----------------
sl=outer.intersect(box(-S,S,-1,YS,-S,S)).cut(rsq(pocketw,pocketw,pr,LIP,D))
# v0.5r3 window: follows the panel's active-area outline (Waveshare DXF: VA 38.99 sq, squircle corners,
# 7.75 tangent run, 2.51 diagonal inset ~ R6.07) offset INTO the active area by OV per side.
# Narrowest section (land) sits on the glass at Y=LIP; 45deg outward chamfer CH3 opens toward the face.
import numpy as np
VA=38.99; OV=0.3; CH3=1.0; LAND=LIP-CH3
_C=np.array(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),"_va_corner.json"))))
def win_pts(off):            # VA outline offset by off (negative = inward), as closed point list
    c=_C; t=np.gradient(c,axis=0); t/=np.linalg.norm(t,axis=1)[:,None]; n=np.c_[t[:,1],-t[:,0]]  # outward normal
    q=c+off*n; q=np.vstack([[VA/2+off,0.0],q[1:-1],[0.0,VA/2+off]]) if False else q
    quad=[(VA/2+off,0.0)]+[tuple(p) for p in q]+[(0.0,VA/2+off)]
    pts=[]
    for sx,sy,rev in ((1,1,False),(-1,1,True),(-1,-1,False),(1,-1,True)):
        Q=[(sx*x,sy*y) for x,y in quad]; pts+= (Q[::-1] if rev else Q)
    out=[]
    for p in pts:
        if not out or (abs(p[0]-out[-1][0])+abs(p[1]-out[-1][1]))>1e-4: out.append(p)
    if abs(out[0][0]-out[-1][0])+abs(out[0][1]-out[-1][1])<1e-4: out.pop()
    return out
def win_wire(off,y):
    return cq.Workplane("XZ",origin=(0,y,0)).polyline(win_pts(off)).close()
WIN=VA-2*OV
sl=sl.cut(win_wire(-OV,LAND-0.01).extrude(-(LIP-LAND+1)))           # land through to the glass
sl=sl.cut(cq.Workplane("XZ",origin=(0,-0.01,0)).polyline(win_pts(-OV+CH3+0.01)).close()
          .workplane(offset=-(CH3+0.02)).polyline(win_pts(-OV)).close().loft(ruled=True))
uy=8.62+cy0
sl=sl.cut(cq.Workplane().box(13.0,7.5,10).edges('|Z').fillet(1.5).translate((0,uy,-H)))
by=9.6+cy0; zt=CASE/2; PROUD=0.97
for x in (-10,0,10):
    sl=sl.cut(cq.Workplane().cylinder(10,1.65).translate((x,by,H)))
    sl=sl.cut(cq.Workplane().cylinder(1.9,3.2).translate((x,by,zt+0.95)))
    # insertion groove for the proud button caps (r2.65, top z=23.97) from the back opening to the pocket
    sl=sl.cut(box(x-3.0,x+3.0,by,YS+1,PI-1,zt+PROUD+0.33))
gy=15.65+cy0; mz=13.0; my=8.45+cy0
for dz,ln in ((-5,2.0),(-3,5.5),(-1,3.5),(1,7.5),(3,5.0),(5,2.0)):
    sl=sl.cut(cq.Workplane().box(10,ln+0.4,1.2).edges('|X').fillet(0.55).translate((H,gy,dz)))
for sx in (-1,1):
    sl=sl.cut(cq.Workplane("YZ",origin=(sx*H,0,0)).center(my,mz).circle(0.8).extrude(6,both=True))
    sl=sl.union(cq.Workplane("YZ",origin=(sx*PI,0,0)).center(my,mz).circle(2.0).circle(0.8).extrude(sx*-0.15))
# latch channels (recess for flush arm), pry recess ahead of tip, catch window through channel floor
FLOOR=H-T-CLR                            # channel floor outer face x=24.2 (floor 0.9 thick)
for sx in (-1,1):
    def bx(a,b,y0,y1,z0,z1): return box(sx*a,sx*b,y0,y1,z0,z1)
    sl=sl.cut(bx(FLOOR,H+1,yt-2.0,YS+1,ZA0-SCL,ZA1+SCL))
    sl=sl.cut(bx(PI-0.5,FLOOR+0.01,yt-0.3,yt+HL+PLAY,ZA0-SCL,ZA1+SCL))
# ---------------- back cover ----------------
cv=outer.intersect(box(-S,S,YS,D+1,-S,S)).cut(rsq(pocketw,pocketw,pr,YS-1,(D-W)-(YS-1)))
PY=D-W                                   # plate inner face 32.31
feat=None
def add(o):
    global feat; feat=o if feat is None else feat.union(o)
for x in (-18.5,18.5):                   # corner press posts (diamond section: self-supporting when printed Z-up)
    for z in (-18.5,18.5):
        add(cq.Workplane("XZ",origin=(0,cyb+PG,0)).center(x,z).polygon(4,4.2).extrude(-(PY+0.5-cyb-PG)))
for sx in (-1,1):
    add(box(sx*20.3,sx*21.5,by0+0.2,PY+0.5,-PI-0.7,12))          # battery X stops, standing on floor
    add(box(sx*7.25,sx*8.75,by0+0.2,PY+0.5,-PI-0.7,-BAT[2]/2-0.3))  # battery floor ribs
    g=(cq.Workplane("YZ",origin=(sx*8-0.75,0,0)).polyline([(PY+0.5,BAT[2]/2+0.3),(PY-2.0,BAT[2]/2+0.3),(by0+0.5,BAT[2]/2+0.3+(PY-2.0-by0-0.5)),(by0+0.5,PI+0.7),(PY+0.5,PI+0.7)]).close().extrude(1.5))
    add(g)                                                        # top gussets, 45 deg underside
clip=rsq(pocketw-0.5,pocketw-0.5,pr-0.25,cyb+PG,YS-cyb-PG+0.01).union(outer.intersect(box(-S,S,YS,D+1,-S,S)))
cv=cv.union(feat.intersect(clip))
arms=None; hooks=None
for sx in (-1,1):
    a=box(sx*(H-T),sx*H,yt,YS+0.6,ZA0,ZA1)
    xi=H-T; pts=[(xi,yt),(xi-HK,yt+RAMP),(xi-HK,yt+HL),(xi,yt+HL)]
    pts=[(sx*px,py) for px,py in pts]
    hk=cq.Workplane("XY",origin=(0,0,ZA0)).polyline(pts).close().extrude(AW)
    arms=a if arms is None else arms.union(a); hooks=hk if hooks is None else hooks.union(hk)
cover_nohook=cv.union(arms)
cover=cover_nohook.union(hooks)
# ---------------- small parts / refs ----------------
ft=0.6; plen=(H-(zt+PROUD))+1.0
pin=cq.Workplane().cylinder(ft,2.7).translate((0,0,ft/2)).union(cq.Workplane().cylinder(plen,1.4).translate((0,0,plen/2))).faces(">Z").edges().fillet(0.5)
cb=cq.Workplane("XY").rect(CASE,CASE).extrude(1.6).edges("|Z").fillet(CR)
for x in (-18.5,18.5):
    for y in (-17,17): cb=cb.cut(cq.Workplane().cylinder(5,1.41).translate((x,y,0))).cut(cq.Workplane().cylinder(1.5,2.335).translate((x,y,1.6)))
cb=cb.cut(cq.Workplane().box(2.0,6,5).translate((14,-CASE/2+2,0)))
case=rsq(43.3,43.3,4.7,cy0,0.49).union(rsq(CASE,CASE,CR,cy0+0.49,CD-0.49))
for x in (-10,0,10): case=case.union(cq.Workplane().cylinder(PROUD+0.5,2.65).translate((x,by,zt+(PROUD-0.5)/2)))
battm=cq.Workplane().box(*BAT).translate((0,by0+BAT[1]/2,0))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
for n,o in (("sleeve_r3",sl),):
    cq.exporters.export(o,n+".stl",tolerance=0.02,angularTolerance=0.1); cq.exporters.export(o,n+".step")
cq.exporters.export(case,"_ref_case.stl"); cq.exporters.export(battm,"_ref_battery.stl")

print("WINDOW land %.3f, face opening %.3f"%(WIN,VA-2*OV+2*CH3))
# ---------------- verification ----------------
V=lambda o:o.val() if hasattr(o,"val") else o
vs,vc,vcn,vk,vh,vb=V(sl),V(cover),V(cover_nohook),V(case),V(hooks),V(battm)
def iv(a,b): return a.intersect(b).Volume()
pv=lambda x:[ (x0,y,z) for x0 in (-10,0,10) for (y,z) in [(by,zt+PROUD)] ]
pins=[V(pin.translate((x,by,zt+PROUD))) for x in (-10,0,10)]
print("solids: sleeve",len(vs.Solids())," cover",len(vc.Solids()))
print("FINAL  case∩sleeve %.4f  case∩cover %.4f  battery∩cover %.4f  sleeve∩cover %.4f  pins∩sleeve %.4f  pins∩case %.4f"%(
  iv(vk,vs),iv(vk,vc),iv(vb,vc),iv(vs,vc),sum(iv(p,vs) for p in pins),sum(iv(p,vk) for p in pins)))
# min gaps
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
def dist(a,b): d=BRepExtrema_DistShapeShape(a.wrapped,b.wrapped); d.Perform(); return d.Value()
print("GAPS   case-sleeve %.3f  case-cover(posts) %.3f  battery-cover %.3f  hook-window(seated) %.3f"%(dist(vk,vs),dist(vk,vc),dist(vb,vc),dist(vh,vs)))
import numpy as np
mx=0; steps=0; bad=[]
for off in np.arange(YS-cy0+0.5,-0.001,-0.5):        # case front starts behind sleeve back opening
    c=vk.translate(cq.Vector(0,off,0)); v=iv(c,vs); steps+=1; mx=max(mx,v)
    if v>1e-6: bad.append((round(off,2),round(v,4)))
print("SWEEP case +Y->seat: %d steps (offset %.1f..0, 0.5mm), max intersection %.6f mm3, hits %s"%(steps,YS-cy0+0.5,mx,bad[:10]))
mx=0; mxc=0; steps=0; bad=[]; defl=[]
for off in np.arange(L+1.0,-0.001,-0.5):
    t=cq.Vector(0,off,0); cn=vcn.translate(t); v=iv(cn,vs); vcc=iv(V(cover).translate(t),vk); steps+=1
    mx=max(mx,v); mxc=max(mxc,vcc)
    if v>1e-6: bad.append((round(off,2),round(v,4)))
    hi=vh.translate(t).intersect(vs)
    d=0.0
    if hi.Volume()>1e-6:
        for sx in (-1,1):
            part=hi.intersect(V(box(sx*0,sx*40,-50,80,-40,40)))
            if part.Volume()>1e-6: bb=part.BoundingBox(); d=max(d,bb.xmax-bb.xmin)
    defl.append((round(off,1),round(d,3)))
print("SWEEP cover (no hooks) vs sleeve: %d steps, max %.6f mm3, hits %s;  cover vs seated case max %.6f mm3"%(steps,mx,bad[:10],mxc))
print("HOOK deflection per step (offset,mm):",defl)
print("max arm deflection %.3f mm; strain est 1.5*t*d/L^2 = %.2f%%"%(max(d for _,d in defl),150*T*max(d for _,d in defl)/L**2))
