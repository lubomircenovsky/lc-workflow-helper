"""Triangle narrow phase in float64; positive-area coplanar overlap or proper segment crossing."""
import numpy as np

def cross2(a,b):return a[0]*b[1]-a[1]*b[0]

def clipped_area(a,b):
    if cross2(b[1]-b[0],b[2]-b[0])<0:b=b[::-1]
    poly=list(a)
    for q,r in zip(b,np.roll(b,-1,axis=0)):
        output=[]
        for p,s in zip(poly,poly[1:]+poly[:1]):
            dp=cross2(r-q,p-q);ds=cross2(r-q,s-q)
            ip=dp>=0;ins=ds>=0
            if ip:output.append(p)
            if ip!=ins:output.append(p+(s-p)*(dp/(dp-ds)))
        poly=output
        if not poly:return 0.
    return abs(sum(cross2(p,s) for p,s in zip(poly,poly[1:]+poly[:1])))/2

def proper_cross(a,b,normal):
    distances=(a-b[0])@normal
    for i in range(3):
        j=(i+1)%3;d1=distances[i];d2=distances[j]
        if (d1>1e-9 and d2<-1e-9) or (d1<-1e-9 and d2>1e-9):
            p=a[i]+(a[j]-a[i])*(d1/(d1-d2))
            ab=b[1]-b[0];ac=b[2]-b[0];ap=p-b[0];nn=np.cross(ab,ac);den=nn@nn
            u=np.cross(ap,ac)@nn/den;v=np.cross(ab,ap)@nn/den
            if u>1e-8 and v>1e-8 and u+v<1-1e-8:return True
    return False

def intersections(vertices,triangles):
    p=vertices[triangles];low=p.min(axis=1);high=p.max(axis=1)
    cr=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]);length=np.linalg.norm(cr,axis=1);norm=cr/np.maximum(length[:,None],1e-30)
    hits=[];tested=0
    for i in range(len(p)):
        ids=np.flatnonzero(np.all(high>=low[i]-1e-9,axis=1)&np.all(low<=high[i]+1e-9,axis=1))
        for j in ids:
            if j<=i:continue
            da=(p[j]-p[i,0])@norm[i];db=(p[i]-p[j,0])@norm[j]
            if da.min()>1e-9 or da.max()<-1e-9 or db.min()>1e-9 or db.max()<-1e-9:continue
            tested+=1
            if max(abs(da))<1e-9 and max(abs(db))<1e-9:
                axis=int(np.argmax(abs(norm[i])));axes=[k for k in range(3) if k!=axis]
                area=clipped_area(p[i][:,axes]-p[i,0,axes],p[j][:,axes]-p[i,0,axes])
                if area>1e-12:hits.append({'a':int(i),'b':int(j),'type':'coplanar_positive_area','area_projected':area})
            elif proper_cross(p[i],p[j],norm[j]) or proper_cross(p[j],p[i],norm[i]):hits.append({'a':int(i),'b':int(j),'type':'proper_crossing'})
    return {'intersections':hits,'narrow_phase_pairs':tested,'tolerance_m':1e-9,'coplanar_area_threshold_m2':1e-12,'method':'float64 AABB all pairs, coplanar convex polygon clipping and strict interior segment-triangle crossings; tangential contacts excluded'}
