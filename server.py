"""Local prototype server: static app + real Audiveris PDF/image recognition."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from urllib.parse import urlparse
import base64, json, os, shutil, subprocess, tempfile, zipfile
import xml.etree.ElementTree as ET
from engrave import convert_mxl
from render import find_musescore, render_pdf, render_preview

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", os.environ.get("LETTER_NOTEHEAD_PORT", "10000")))
API_TOKEN = os.environ.get("LETTER_NOTEHEAD_API_TOKEN", "").strip()

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
    return {"parts":parts,"noteCount":note_count,"measureCount":len(measure_numbers),"durations":sorted(set(durations))}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(ROOT),**kwargs)
    def send_json(self,status,payload):
        body=json.dumps(payload).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type'); self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS'); self.end_headers()
    def authorized(self):
        return not API_TOKEN or self.headers.get('Authorization','') == 'Bearer '+API_TOKEN
    def do_GET(self):
        if urlparse(self.path).path in {'/','/health','/api/status'}:
            binary=find_audiveris(); renderer=find_musescore(); return self.send_json(200,{"ready":bool(binary),"engine":"Audiveris","configuredPath":binary,"pdfReady":bool(renderer),"renderer":"MuseScore Studio","rendererPath":renderer})
        return self.send_json(404,{"error":"Not found"})
    def do_POST(self):
        if urlparse(self.path).path != '/api/recognize': return self.send_json(404,{"error":"Not found"})
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
            if Path(filename).suffix.lower() not in {'.pdf','.png','.jpg','.jpeg','.tif','.tiff'}: raise ValueError('Use a PDF, PNG, JPG, or TIFF file.')
            with tempfile.TemporaryDirectory(prefix='letter-notehead-') as td:
                source=Path(td)/filename; source.write_bytes(item.get_payload(decode=True)); out=Path(td)/'output'; out.mkdir()
                command=[binary,'-batch','-transcribe','-export','-output',str(out),'--',str(source)]
                run=subprocess.run(command,capture_output=True,text=True,timeout=480)
                # Audiveris writes book outputs in a score-named subfolder
                # beneath the configured output directory.
                mxl=next(out.rglob('*.mxl'),None)
                if run.returncode or not mxl:
                    diagnostic=(run.stderr or run.stdout or 'No diagnostic output').strip()[-6000:]
                    print(f'Audiveris failed ({run.returncode}) for {filename}:\n{diagnostic}',flush=True)
                    raise RuntimeError('Recognition did not produce a score. Try a clearer, straight-on image.')
                data=parse_musicxml(mxl)
                title=Path(filename).stem.replace('_',' ').replace('-',' ').strip().title()
                # Preserve the recognized system layout until the correction UI can safely reflow every score.
                learning_modes={}; renderer=find_musescore()
                for mode,suffix in [('all','all-letters'),('guide','fewer-hints'),('none','standard')]:
                    converted=out/(mxl.stem+f'-{suffix}.mxl')
                    label_count=convert_mxl(mxl,converted,title=title,clean_layout=False,label_mode=mode)
                    result={"labelCount":label_count,"mxl":base64.b64encode(converted.read_bytes()).decode('ascii'),"pdf":None,"preview":None}
                    if renderer:
                        rendered=out/(mxl.stem+f'-{suffix}.pdf'); render_pdf(converted,rendered)
                        result['pdf']=base64.b64encode(rendered.read_bytes()).decode('ascii')
                        preview=out/(mxl.stem+f'-{suffix}.png'); render_preview(rendered,preview)
                        result['preview']=base64.b64encode(preview.read_bytes()).decode('ascii')
                    learning_modes[mode]=result
            primary=learning_modes['all']
            data.update({"fileName":filename,"engine":"Audiveris","reviewRequired":True,"convertedNoteCount":primary['labelCount'],"letterNoteheadMxl":primary['mxl'],"letterNoteheadPdf":primary['pdf'],"learningModes":learning_modes,"issues":[{"measure":"—","voice":"Visual check","from":"?","to":"✓","count":"Compare pitches with the original"}]})
            return self.send_json(200,data)
        except subprocess.TimeoutExpired: return self.send_json(504,{"error":"Recognition took longer than eight minutes."})
        except Exception as exc: return self.send_json(400,{"error":str(exc)})

if __name__ == '__main__':
    print(f'Letter Notehead service: http://0.0.0.0:{PORT}')
    print('Recognition engine:',find_audiveris() or 'not configured (demo remains available)')
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
