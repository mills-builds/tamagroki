import json,os,numpy as np,trimesh
from shapely.geometry import Polygon
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
src=open('render_v05.py').read(); src=src[:src.index('P="#9B7FE0"')]
exec(src)                                   # reuse render()
ns={'json':json,'os':os,'LIP':1.64}
c=open('cube_v05r3.py').read(); exec(c[c.index('import numpy as np\nVA'):c.index('def win_wire')].replace('os.path.dirname(os.path.abspath(__file__))','"."'),ns)
y0=p["cy0"]
def plate(poly,y,th):
    m=trimesh.creation.extrude_polygon(poly,th)   # along +Z
    m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(90),(1,0,0)))  # z->-y
    m.apply_translation((0,y,0)); return m
from shapely.geometry import box as sbox
bez=sbox(-21.65,-21.65,21.65,21.65).buffer(-4.7).buffer(4.7)
va=Polygon(ns['win_pts'](0))
black=plate(bez.difference(va.buffer(0.001)),y0-0.001,0.02)   # panel border, black
lit=plate(va,y0-0.002,0.02)                                    # lit active area
front=L("sleeve_r3.stl"); back=L("back_cover.stl"); case=L("_ref_case.stl")
P="#9B7FE0"; MAG="#E040FB"
render([(front,P),(back,"#7E5FCC"),(black,"#050505"),(lit,MAG),(case,"#8A63E8")],"view_r3_front_3q.png",20,35,"v0.5r3 front 3/4: window 38.39 (VA-0.3/side), squircle corners, 1.0x45 outward chamfer")
render([(front,P),(black,"#050505"),(lit,MAG)],"view_r3_front.png",0,0,"v0.5r3 straight-on: lit VA (magenta) fills window, no black border visible")
render([(front,P),(black,"#050505"),(lit,MAG)],"view_r3_front_angle35.png",0,35,"v0.5r3 at 35 deg: lip wall/chamfer purple, border still hidden")
# lip section plots: X=0 and diagonal
fig,axs=plt.subplots(1,2,figsize=(13,5))
for ax,(nrm,lab) in zip(axs,(((1,0,0),"X=0 section (top edge)"),((1/np.sqrt(2),0,-1/np.sqrt(2)),"diagonal section (corner)"))):
    for m,col,nm in ((front,P,"sleeve r3"),(L("sleeve.stl"),"none","r2 outline"),(case,"#BBBBBB","case/panel")):
        s=m.section(plane_origin=(0,0,0),plane_normal=nrm)
        for e in s.discrete:
            # in-plane coords: Y and distance along the in-plane horizontal axis
            u=np.cross(nrm,(0,1,0)); u=u/np.linalg.norm(u)
            ax.plot(e[:,1],e@u,color=("k" if col=="none" else col),lw=(0.8 if col=="none" else 1.6),ls=("--" if col=="none" else "-"))
    R=19.495 if nrm[0]==1 else 19.495*np.sqrt(2)-2.512
    ax.axhline(R,color=MAG,lw=1); ax.text(-0.9,R+0.1,"VA edge",color=MAG,fontsize=8)
    ax.axhline(R-0.3,color="g",lw=0.6,ls=":")
    ax.set_xlim(-1,6); ax.set_ylim(R-3,R+8 if nrm[0]==1 else R+10); ax.set_aspect("equal"); ax.set_xlabel("Y (mm, face at 0)"); ax.set_ylabel("radial (mm)")
    ax.set_title(lab+"; dashed = r2"); ax.grid(alpha=.3)
plt.suptitle("v0.5r3 lip: 1.64 lip, land 0.64 on glass (0 gap), 1.0x45 chamfer to face, window 0.30 inside VA")
plt.tight_layout(); plt.savefig("view_r3_section_lip.png",dpi=110); print("view_r3_section_lip.png")
