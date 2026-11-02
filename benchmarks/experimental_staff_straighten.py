"""Rejected preprocessing experiment; never imported by the production server.

Needs NumPy and SciPy in addition to Pillow. Staff traces can look better while
OMR becomes worse. Run only on copies; compare recognized notes with a reference.
"""
from PIL import Image,ImageOps
import numpy as np
from scipy.signal import find_peaks
from pathlib import Path
import json


def straighten(image, regularize=False):
    a=np.asarray(image)
    height,width=a.shape
    half=max(40,round(width*.08))
    def profile(x):
        return (a[:,max(0,x-half):min(width,x+half)]<145).mean(axis=1)
    anchors=[]
    for fraction in [.35,.45,.55,.65]:
        center=round(width*fraction)
        base=profile(center)
        peaks,_=find_peaks(base,height=.65,distance=4,prominence=.1)
        groups=[];i=0
        while i<=len(peaks)-5:
            g=peaks[i:i+5];gaps=np.diff(g);s=float(np.median(gaps))
            if 5<s<30 and max(abs(gaps-s))<s*.2:
                groups.append(g.astype(float));i+=5
            else:i+=1
        anchors.append((len(groups),center,groups))
    _,center,groups=max(anchors,key=lambda v:v[0])
    if len(groups)<2:raise ValueError('Too few reliable five-line staff groups')
    if regularize:
        groups=[np.polyval(np.polyfit(np.arange(5),g,1),np.arange(5)) for g in groups]
    reference=np.concatenate(groups)
    centers=list(range(round(width*.1),round(width*.94)+1,max(50,width//20)))
    centers=sorted(set(centers+[center]))
    tracks={center:reference.copy()}
    for direction in [-1,1]:
        last=reference.copy()
        for x in sorted([x for x in centers if (x-center)*direction>0],reverse=direction<0):
            p=profile(x);current=[]
            for j,g in enumerate(groups):
                pred=last[j*5:j*5+5]
                spacing=float(np.median(np.diff(pred)))
                best=None
                for shift in np.arange(-4,4.01,.5):
                    for gap in np.arange(spacing-.35,spacing+.36,.175):
                        candidate=pred[2]+shift+(np.arange(5)-2)*gap
                        value=np.mean(np.interp(candidate,np.arange(height),p))-.001*shift*shift
                        if best is None or value>best[0]:best=(value,candidate)
                if best[0]<.4:raise ValueError('Staff trace lost across page')
                current.extend(best[1])
            last=np.array(current);tracks[x]=last.copy()
    xs=sorted(tracks)
    tracks[0]=tracks[xs[0]];tracks[width]=tracks[xs[-1]]
    xs=sorted(tracks)
    ys=np.concatenate(([0],np.round(reference),[height])).astype(int)
    mesh=[]
    for x0,x1 in zip(xs,xs[1:]):
        left=np.concatenate(([0],tracks[x0],[height]));right=np.concatenate(([0],tracks[x1],[height]))
        if np.any(np.diff(left)<=0) or np.any(np.diff(right)<=0):
            raise ValueError('Staff traces would fold over')
        for k,(y0,y1) in enumerate(zip(ys,ys[1:])):
            if y1<=y0:raise ValueError('Non-monotonic warp')
            mesh.append(((x0,int(y0),x1,int(y1)),(x0,float(left[k]),x0,float(left[k+1]),x1,float(right[k+1]),x1,float(right[k]))))
    output=image.transform(image.size,Image.Transform.MESH,mesh,resample=Image.Resampling.BICUBIC,fillcolor=255)
    return output,{'staffGroups':len(groups),'maxVerticalShift':float(max(np.max(abs(v-reference)) for v in tracks.values())),'referenceLines':reference.tolist()}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    parser.add_argument('--regularize',action='store_true')
    args=parser.parse_args()
    if args.source.resolve()==args.destination.resolve():
        parser.error('Use a separate output path to preserve the source.')
    with Image.open(args.source) as source:
        image=ImageOps.exif_transpose(source).convert('L')
    image,metrics=straighten(image,regularize=args.regularize)
    image.save(args.destination)
    print(json.dumps(metrics,indent=2))
