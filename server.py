"""Local prototype server: static app + real Audiveris PDF/image recognition."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse
import base64, hashlib, json, os, shutil, signal, subprocess, tempfile, threading, time, uuid, zipfile
import urllib.error, urllib.request
import xml.etree.ElementTree as ET
from engrave import convert_mxl
from render import find_musescore, render_pdf, render_preview, render_pages_and_lines
from photo_prep import prepare_photo

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", os.environ.get("LETTER_NOTEHEAD_PORT", "10000")))
API_TOKEN = os.environ.get("LETTER_NOTEHEAD_API_TOKEN", "").strip()
REVIEW_PASSWORD = os.environ.get("LETTER_NOTEHEAD_REVIEW_PASSWORD", "").strip()
JOBS = {}
JOBS_LOCK = threading.Lock()
RECOGNITION_LOCK = threading.Lock()
PROCESS_LOCK = threading.Lock()
ACTIVE_PROCESSES = {}
CACHE_DIR = Path(os.environ.get("LETTER_NOTEHEAD_CACHE_DIR", "/tmp/letter-notehead-cache"))
CACHE_VERSION = "recognition-v5-pdf-350"
CACHE_MAX_BYTES = 120 * 1024 * 1024
CACHE_MAX_FILES = 4


def cache_path(score_bytes, quality):
    digest = hashlib.sha256(score_bytes + b"|" + CACHE_VERSION.encode() + b"|" + quality.encode()).hexdigest()
    return CACHE_DIR / f"{digest}.json"


def read_cached_result(path):
    try:
        if not path.exists(): return None
        os.utime(path, None)
        result = json.loads(path.read_text(encoding="utf-8"))
        result["cacheHit"] = True
        return result
    except Exception:
        return None


def write_cached_result(path, result):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result), encoding="utf-8")
        temporary.replace(path)
        files = sorted(CACHE_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        total = 0
        for index, item in enumerate(files):
            total += item.stat().st_size
            if index >= CACHE_MAX_FILES or total > CACHE_MAX_BYTES:
                item.unlink(missing_ok=True)
    except Exception as exc:
        print(f"Recognition cache warning: {exc}", flush=True)


def run_async_job(job_id, raw, content_type, authorization):
    request = urllib.request.Request(
        f"http://127.0.0.1:{PORT}/api/recognize",
        data=raw,
        method="POST",
        headers={"Content-Type": content_type, "Authorization": authorization, "X-Job-ID": job_id},
    )
    try:
        # Audiveris and MuseScore are memory-heavy; serialize jobs on the 512 MB service.
        with RECOGNITION_LOCK:
            with urllib.request.urlopen(request, timeout=600) as response:
                result = json.loads(response.read().decode("utf-8"))
        job = {"status": "complete", "result": result}
    except urllib.error.HTTPError as exc:
        try: payload = json.loads(exc.read().decode("utf-8"))
        except Exception: payload = {"error": f"Recognition failed with status {exc.code}."}
        job = {"status": "failed", "error": payload.get("error", "Recognition failed."), "serverStatus": exc.code}
        print(f"Recognition job {job_id} failed ({exc.code}): {job['error']}", flush=True)
    except Exception as exc:
        job = {"status": "failed", "error": str(exc)}
        print(f"Recognition job {job_id} failed: {exc}", flush=True)
    with JOBS_LOCK:
        if JOBS.get(job_id, {}).get("status") != "cancelled":
            JOBS[job_id] = job


def stop_job_process(job_id):
    with PROCESS_LOCK:
        process = ACTIVE_PROCESSES.get(job_id)
    if process and process.poll() is None:
        try:
            if os.name == "posix": os.killpg(process.pid, signal.SIGTERM)
            else: process.terminate()
        except ProcessLookupError:
            pass


def find_audiveris():
    configured = os.environ.get("AUDIVERIS_BIN")
    candidates = [configured, shutil.which("Audiveris"), shutil.which("audiveris")]
    if os.name == "nt":
        candidates += [
            r"C:\Program Files\Audiveris\Audiveris.exe",
            r"C:\Program Files\Audiveris\bin\Audiveris.exe",
        ]
    for candidate in candidates:
        if candidate and Path(candidate).exists(): return str(Path(candidate))
    return None

def parse_musicxml(mxl_path):
    with zipfile.ZipFile(mxl_path) as zf:
        score_name = next(n for n in zf.namelist() if n.endswith('.xml') and not n.startswith('META-INF/'))
        root = ET.fromstring(zf.read(score_name))
    parts=[]; note_count=0; measure_numbers=set(); durations=[]
    for part in root.findall('part'):
        pdata={"id":part.attrib.get('id'),"measures":[]}
        for measure in part.findall('measure'):
            number=measure.attrib.get('number'); measure_numbers.add(number)
            divisions=int(measure.findtext('attributes/divisions') or 1); notes=[]
            for n in measure.findall('note'):
                if n.find('rest') is not None: continue
                p=n.find('pitch')
                if p is None: continue
                step=p.findtext('step') or '?'; alter=p.findtext('alter'); octave=p.findtext('octave') or ''
                pitch=step+({'1':'#','-1':'b'}.get(alter,'') if alter else '')+octave
                duration=int(n.findtext('duration') or 0)/divisions
                notes.append({"pitch":pitch,"letter":step,"duration":duration,"voice":n.findtext('voice') or '1'})
                note_count+=1; durations.append(duration)
            pdata['measures'].append({"number":number,"notes":notes})
        parts.append(pdata)
    fifths_text=root.findtext('part/measure/attributes/key/fifths')
    try: fifths=int(fifths_text or 0)
    except ValueError: fifths=0
    sharp_order=['F♯','C♯','G♯','D♯','A♯','E♯','B♯']
    flat_order=['B♭','E♭','A♭','D♭','G♭','C♭','F♭']
    altered=sharp_order[:fifths] if fifths > 0 else flat_order[:abs(fifths)] if fifths < 0 else []
    key_guide=('Sharps: '+', '.join(altered)) if fifths > 0 else ('Flats: '+', '.join(altered)) if fifths < 0 else 'No sharps or flats'
    return {"parts":parts,"noteCount":note_count,"measureCount":len(measure_numbers),"durations":sorted(set(durations)),"keyGuide":key_guide}


def validate_musicxml(mxl_path):
    """Flag measures whose exported timeline does not fill the active meter."""
    with zipfile.ZipFile(mxl_path) as zf:
        score_name=next(n for n in zf.namelist() if n.endswith('.xml') and not n.startswith('META-INF/'))
        root=ET.fromstring(zf.read(score_name))
    suspects=[]
    for part in root.findall('part'):
        divisions=1; beats=None; beat_type=None
        for index,measure in enumerate(part.findall('measure')):
            divisions=int(measure.findtext('attributes/divisions') or divisions)
            beats_text=measure.findtext('attributes/time/beats'); type_text=measure.findtext('attributes/time/beat-type')
            if beats_text and type_text:
                try: beats=int(beats_text); beat_type=int(type_text)
                except ValueError: beats=beat_type=None
            cursor=0; furthest=0; pitched=0
            for child in measure:
                duration=int(child.findtext('duration') or 0)
                if child.tag == 'backup': cursor=max(0,cursor-duration)
                elif child.tag == 'forward': cursor+=duration; furthest=max(furthest,cursor)
                elif child.tag == 'note':
                    if child.find('pitch') is not None: pitched+=1
                    if child.find('chord') is None and child.find('grace') is None:
                        cursor+=duration; furthest=max(furthest,cursor)
            expected=(divisions*beats*4/beat_type) if beats and beat_type else None
            implicit=measure.attrib.get('implicit') == 'yes' or index == 0
            if expected and not implicit and furthest < expected*.98:
                suspects.append({"part":part.attrib.get('id'),"measure":measure.attrib.get('number'),"filled":round(furthest/expected,3),"recognizedNotes":pitched})
    return {"suspectMeasures":suspects,"suspectMeasureCount":len(suspects),"method":"meter-duration-check"}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def send_json(self,status,payload):
        body=json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.end_headers()
    def authorized(self):
        return not API_TOKEN or self.headers.get('Authorization','') == 'Bearer '+API_TOKEN
    def review_authorized(self):
        if not REVIEW_PASSWORD: return True
        expected='Basic '+base64.b64encode(('letterscore:'+REVIEW_PASSWORD).encode()).decode()
        return self.headers.get('Authorization','') == expected
    def require_review_auth(self):
        self.send_response(401); self.send_header('WWW-Authenticate','Basic realm="LetterScore Test Lab"'); self.send_header('Cache-Control','no-store'); self.end_headers()
    def do_GET(self):
        path=urlparse(self.path).path
        if path in {'/review','/review.html','/review.css','/review.js','/review-config.js'} and not self.review_authorized():
            return self.require_review_auth()
        if path == '/review':
            self.send_response(302); self.send_header('Location','/review.html'); self.end_headers(); return
        if path in {'/review.html','/review.css','/review.js'}:
            return super().do_GET()
        if path == '/review-config.js':
            body=("window.LETTERSCORE_REVIEW_CONFIG="+json.dumps({"apiToken":API_TOKEN})+";").encode()
            self.send_response(200); self.send_header('Content-Type','application/javascript'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body); return
        if path.startswith('/api/jobs/'):
            if not self.authorized(): return self.send_json(401,{"error":"Unauthorized"})
            job_id=path.rsplit('/',1)[-1]
            with JOBS_LOCK:
                job=JOBS.get(job_id)
                if job and job.get('status') in {'complete','failed'}: JOBS.pop(job_id,None)
            if job is None: return self.send_json(404,{"error":"Recognition job not found."})
            return self.send_json(200,job)
        if path in {'/','/health','/api/status'}:
            binary=find_audiveris(); renderer=find_musescore(); return self.send_json(200,{"ready":bool(binary),"engine":"Audiveris","configuredPath":binary,"pdfReady":bool(renderer),"renderer":"MuseScore Studio","rendererPath":renderer})
        return self.send_json(404,{"error":"Not found"})
    def do_POST(self):
        path=urlparse(self.path).path
        if path.startswith('/api/jobs/') and path.endswith('/cancel'):
            if not self.authorized(): return self.send_json(401,{"error":"Unauthorized"})
            job_id=path.strip('/').split('/')[-2]
            with JOBS_LOCK:
                job=JOBS.get(job_id)
                if job is None: return self.send_json(404,{"error":"Recognition job not found."})
                if job.get("status") == "complete": return self.send_json(409,{"error":"Recognition has already finished."})
                JOBS[job_id]={"status":"cancelled"}
            stop_job_process(job_id)
            return self.send_json(200,{"jobId":job_id,"status":"cancelled"})
        if path == '/api/recognize-async':
            if not self.authorized(): return self.send_json(401,{"error":"Unauthorized"})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length <= 0 or length > 30*1024*1024: raise ValueError('Choose a file smaller than 30 MB.')
                raw=self.rfile.read(length)
                job_id=uuid.uuid4().hex
                with JOBS_LOCK: JOBS[job_id]={"status":"processing"}
                worker=threading.Thread(target=run_async_job,args=(job_id,raw,self.headers.get('Content-Type',''),self.headers.get('Authorization','')),daemon=True)
                worker.start()
                return self.send_json(202,{"jobId":job_id,"status":"processing"})
            except Exception as exc: return self.send_json(400,{"error":str(exc)})
        if path == '/api/convert-mode':
            if not self.authorized(): return self.send_json(401,{"error":"Unauthorized"})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length <= 0 or length > 20*1024*1024: raise ValueError('Conversion request is too large.')
                payload=json.loads(self.rfile.read(length).decode('utf-8'))
                mode=payload.get('mode')
                if mode not in {'guide','none'}: raise ValueError('Choose guide or standard notation.')
                source_bytes=base64.b64decode(payload.get('sourceMxl',''),validate=True)
                title=str(payload.get('title') or 'Recognized Score')[:200]
                suffix='fewer-hints' if mode == 'guide' else 'standard'
                with tempfile.TemporaryDirectory(prefix='letter-notehead-mode-') as td:
                    source=Path(td)/'source.mxl'; source.write_bytes(source_bytes)
                    converted=Path(td)/f'{suffix}.mxl'
                    label_count=convert_mxl(source,converted,title=title,clean_layout=False,label_mode=mode)
                    result={"labelCount":label_count,"mxl":base64.b64encode(converted.read_bytes()).decode('ascii'),"pdf":None,"preview":None,"pages":[],"lines":[]}
                    renderer=find_musescore()
                    if renderer:
                        rendered=Path(td)/f'{suffix}.pdf'; render_pdf(converted,rendered)
                        result['pdf']=base64.b64encode(rendered.read_bytes()).decode('ascii')
                        pages,lines=render_pages_and_lines(rendered,Path(td)/f'{suffix}-images')
                        result['pages']=[base64.b64encode(p.read_bytes()).decode('ascii') for p in pages]
                        result['lines']=[base64.b64encode(p.read_bytes()).decode('ascii') for p in lines]
                        result['preview']=result['pages'][0] if result['pages'] else None
                return self.send_json(200,result)
            except Exception as exc: return self.send_json(400,{"error":str(exc)})
        if path != '/api/recognize': return self.send_json(404,{"error":"Not found"})
        if not self.authorized(): return self.send_json(401,{"error":"Unauthorized"})
        binary=find_audiveris()
        if not binary: return self.send_json(503,{"error":"Audiveris is not installed or AUDIVERIS_BIN is not configured."})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length <= 0 or length > 30*1024*1024: raise ValueError('Choose a file smaller than 30 MB.')
            raw=self.rfile.read(length)
            msg=BytesParser(policy=default).parsebytes(b'Content-Type: '+self.headers['Content-Type'].encode()+b'\r\nMIME-Version: 1.0\r\n\r\n'+raw)
            item=next((p for p in msg.iter_parts() if p.get_param('name',header='content-disposition')=='score'),None)
            if item is None: raise ValueError('No score file was received.')
            filename=Path(item.get_filename() or 'score.pdf').name
            suffix=Path(filename).suffix.lower()
            if suffix not in {'.pdf','.png','.jpg','.jpeg','.tif','.tiff'}: raise ValueError('Use a PDF, PNG, JPG, or TIFF file.')
            quality_item=next((p for p in msg.iter_parts() if p.get_param('name',header='content-disposition')=='recognitionMode'),None)
            quality=(quality_item.get_payload(decode=True).decode('utf-8','ignore').strip() if quality_item else 'fast')
            if quality not in {'fast','best'}: quality='fast'
            score_bytes=item.get_payload(decode=True)
            recognition_profile='pdf-optimized-350' if suffix == '.pdf' else quality
            cached_path=cache_path(score_bytes,recognition_profile)
            cached=read_cached_result(cached_path)
            if cached is not None: return self.send_json(200,cached)
            with tempfile.TemporaryDirectory(prefix='letter-notehead-') as td:
                timings={}; total_started=time.monotonic(); stage_started=total_started
                td_path=Path(td)
                prepared_bytes,prepared_suffix,quality_assessment=prepare_photo(score_bytes,suffix,td_path,quality)
                timings['preprocessing']=round(time.monotonic()-stage_started,3)
                if suffix == '.pdf':
                    quality_assessment={"kind":"document","confidence":"high","profile":"Optimized vector PDF","pdfResolutionDpi":350,"warnings":["Measures flagged by the rhythm check still require visual review."]}
                if quality_assessment.get('confidence') == 'low' and quality_assessment.get('staffLineCount', 10) < 5:
                    raise ValueError('This photo is too unclear to recognize reliably. Fill the frame with one flat page, avoid shadows, and retake it straight on.')
                source=td_path/('score'+prepared_suffix); source.write_bytes(prepared_bytes); out=td_path/'output'; out.mkdir()
                command=['xvfb-run','-a','-s','-screen 0 1280x1024x24',binary,'-batch','-swap']
                if suffix == '.pdf':
                    command += ['-constant','org.audiveris.omr.image.ImageLoading.pdfResolution=350','-constant','org.audiveris.omr.text.tesseract.TesseractOCR.useOCR=false']
                command += ['-transcribe','-export','-output',str(out),'--',str(source)]
                java_env=os.environ.copy()
                # Leave native-memory headroom for Java, Python, Xvfb, and the
                # renderer on Render's 512 MB instance. The 350-DPI benchmark
                # produces the same 601-note result with a 200 MB Java heap.
                java_env['JAVA_TOOL_OPTIONS']='-Xmx200m -XX:+UseSerialGC'
                job_id=self.headers.get('X-Job-ID','')
                stage_started=time.monotonic()
                process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=java_env,start_new_session=(os.name == 'posix'))
                if job_id:
                    with PROCESS_LOCK: ACTIVE_PROCESSES[job_id]=process
                    with JOBS_LOCK: cancelled_before_start=JOBS.get(job_id,{}).get('status') == 'cancelled'
                    if cancelled_before_start: stop_job_process(job_id)
                try:
                    stdout,stderr=process.communicate(timeout=480)
                except subprocess.TimeoutExpired:
                    if os.name == 'posix': os.killpg(process.pid,signal.SIGKILL)
                    else: process.kill()
                    process.communicate()
                    raise
                finally:
                    if job_id:
                        with PROCESS_LOCK: ACTIVE_PROCESSES.pop(job_id,None)
                with JOBS_LOCK:
                    cancelled=bool(job_id and JOBS.get(job_id,{}).get('status') == 'cancelled')
                if cancelled: raise RuntimeError('Recognition was cancelled.')
                # Audiveris writes book outputs in a score-named subfolder
                # beneath the configured output directory.
                mxl=next(out.rglob('*.mxl'),None)
                if process.returncode or not mxl:
                    diagnostic=(stderr or stdout or 'No diagnostic output').strip()[-6000:]
                    print(f'Audiveris failed ({process.returncode}) for {filename}:\n{diagnostic}',flush=True)
                    raise RuntimeError('Recognition did not produce a score. Try a clearer, straight-on image.')
                timings['recognition']=round(time.monotonic()-stage_started,3)
                stage_started=time.monotonic()
                data=parse_musicxml(mxl)
                validation=validate_musicxml(mxl)
                timings['scoreAnalysis']=round(time.monotonic()-stage_started,3)
                title=Path(filename).stem.replace('_',' ').replace('-',' ').strip().title()
                # Preserve the recognized system layout until the correction UI can safely reflow every score.
                source_mxl=base64.b64encode(mxl.read_bytes()).decode('ascii')
                learning_modes={}; renderer=find_musescore()
                # Prepare the first-shown option now; alternate modes are rendered on demand.
                for mode,suffix in [('all','all-letters')]:
                    stage_started=time.monotonic()
                    converted=out/(mxl.stem+f'-{suffix}.mxl')
                    label_count=convert_mxl(mxl,converted,title=title,clean_layout=False,label_mode=mode)
                    timings['letterConversion']=round(time.monotonic()-stage_started,3)
                    result={"labelCount":label_count,"mxl":base64.b64encode(converted.read_bytes()).decode('ascii'),"pdf":None,"preview":None,"pages":[],"lines":[]}
                    if renderer:
                        stage_started=time.monotonic()
                        rendered=out/(mxl.stem+f'-{suffix}.pdf'); render_pdf(converted,rendered)
                        timings['pdfRendering']=round(time.monotonic()-stage_started,3)
                        result['pdf']=base64.b64encode(rendered.read_bytes()).decode('ascii')
                        stage_started=time.monotonic()
                        pages,lines=render_pages_and_lines(rendered,out/(mxl.stem+f'-{suffix}-images'))
                        timings['previewRendering']=round(time.monotonic()-stage_started,3)
                        result['pages']=[base64.b64encode(p.read_bytes()).decode('ascii') for p in pages]
                        result['lines']=[base64.b64encode(p.read_bytes()).decode('ascii') for p in lines]
                        result['preview']=result['pages'][0] if result['pages'] else None
                    learning_modes[mode]=result
                timings['total']=round(time.monotonic()-total_started,3)
            primary=learning_modes['all']
            if quality_assessment.get('kind') == 'photo':
                quality_assessment['recognizedNotes'] = data['noteCount']
                quality_assessment['recognizedMeasures'] = data['measureCount']
                if data['noteCount'] < 8 or data['measureCount'] < 1:
                    quality_assessment['confidence'] = 'low'
                    quality_assessment['warnings'].insert(0, 'Recognition found too little musical content to trust this result.')
            data.update({"fileName":filename,"engine":"Audiveris","recognitionMode":recognition_profile,"cacheHit":False,"reviewRequired":True,"qualityAssessment":quality_assessment,"validation":validation,"stageTimings":timings,"convertedNoteCount":primary['labelCount'],"letterNoteheadMxl":primary['mxl'],"letterNoteheadPdf":primary['pdf'],"sourceMxl":source_mxl,"learningModes":learning_modes,"issues":[{"measure":"—","voice":"Visual check","from":"?","to":"✓","count":"Compare pitches with the original"}]})
            write_cached_result(cached_path,data)
            return self.send_json(200,data)
        except subprocess.TimeoutExpired: return self.send_json(504,{"error":"Recognition took longer than eight minutes."})
        except Exception as exc: return self.send_json(400,{"error":str(exc)})

if __name__ == '__main__':
    print(f'Letter Notehead service: http://0.0.0.0:{PORT}')
    print('Recognition engine:',find_audiveris() or 'not configured (demo remains available)')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
