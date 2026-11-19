"""Run one controlled photo variant without changing production preprocessing."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from PIL import Image,ImageOps,ImageFilter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from photo_prep import _deskew,_staff_metrics,_normalize_lighting
from benchmarks.compare_photo_reference import reference_notes,recognized_notes,compare


def run(args):
    output=args.output.resolve()
    if output.exists():raise ValueError('Use a new output directory to avoid stale recognition results.')
    output.mkdir(parents=True)
    with Image.open(args.source) as opened:image=ImageOps.exif_transpose(opened).convert('L')
    correction={}
    if args.straighten:
        from benchmarks.experimental_staff_straighten import straighten
        image,correction=straighten(image,regularize=args.regularize)
    if args.blur:image=image.filter(ImageFilter.GaussianBlur(args.blur))
    image,angle=_deskew(image);metrics=_staff_metrics(image)
    image=_normalize_lighting(image)
    measured=metrics['staffSpacing'];scale=args.target_spacing/measured if measured else 1
    scale=max(1,min(scale,2.8))
    if max(image.size)*scale>5000:scale=5000/max(image.size)
    if scale>1.03:image=image.resize((round(image.width*scale),round(image.height*scale)),Image.Resampling.LANCZOS)
    source=output/'input.png';image.save(source,optimize=True,dpi=(300,300))
    command=[str(args.audiveris.resolve()),'-batch','-swap','-transcribe','-export','-output',str(output),'--',str(source)]
    env=os.environ.copy();env['JAVA_TOOL_OPTIONS']='-Xmx128m -XX:+UseSerialGC -Djava.awt.headless=true'
    started=time.perf_counter()
    process=subprocess.run(command,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240)
    (output/'engine.log').write_text(process.stdout)
    result={'exitCode':process.returncode,'seconds':round(time.perf_counter()-started,2),
            'geometry':correction,'staffMetrics':metrics,'deskewDegrees':angle,
            'targetSpacing':args.target_spacing,'blurRadius':args.blur}
    mxls=list(output.rglob('*.mxl'))
    if process.returncode==0 and mxls and args.reference_pdf:
        try:result['comparison']=compare(reference_notes(args.reference_pdf,args.page),recognized_notes(mxls[0]))
        except ValueError as exc:result['comparisonUnavailable']=str(exc)
    (output/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--audiveris',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--reference-pdf',type=Path);parser.add_argument('--page',type=int,default=1)
    parser.add_argument('--straighten',action='store_true');parser.add_argument('--regularize',action='store_true')
    parser.add_argument('--blur',type=float,default=0);parser.add_argument('--target-spacing',type=float,default=16)
    args=parser.parse_args()
    if not 0<=args.blur<=1 or not 10<=args.target_spacing<=24:parser.error('Choose blur 0..1 and spacing 10..24.')
    run(args)
