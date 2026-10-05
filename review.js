const API_TOKEN=window.LETTERSCORE_REVIEW_CONFIG?.apiToken||'';
const auth=()=>API_TOKEN?{Authorization:'Bearer '+API_TOKEN}:{};
const categories={extraNote:'Extra notes',missingNote:'Missing notes',wrongPitch:'Wrong pitches',accidental:'Accidentals',rhythm:'Rhythm errors',chord:'Chord errors',rest:'Rest errors',layout:'Layout / other'};
let file=null,mode='fast',jobId=null,result=null,startTime=0,duration=0,timer=null,page=0,zoom=1,selectedCategory='extraNote',marks=[];
const $=selector=>document.querySelector(selector);
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function toast(message){const node=$('#toast');node.textContent=message;node.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),2400)}
function formatTime(ms){const seconds=Math.round(ms/1000);return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`}
async function json(response,context){const text=await response.text();try{return JSON.parse(text)}catch(error){throw new Error(`${context} returned an unreadable response (${response.status}).`)}}

$('#scoreFile').onchange=event=>{
  file=event.target.files[0]||null;result=null;marks=[];
  $('#fileName').textContent=file?.name||'No file selected';$('#runTest').disabled=!file;
  if(!file)return;
  $('#originalTitle').textContent=file.name;
  const url=URL.createObjectURL(file),isPdf=file.type==='application/pdf'||/\.pdf$/i.test(file.name);
  const fastButton=$('[data-mode="fast"]'),bestButton=$('[data-mode="best"]');
  bestButton.disabled=isPdf;fastButton.innerHTML=isPdf?'◎ Optimized PDF':'⚡ Fast';
  if(isPdf){mode='fast';document.querySelectorAll('[data-mode]').forEach(item=>item.classList.toggle('selected',item===fastButton))}
  $('#originalImage').style.display=isPdf?'none':'block';$('#originalPdf').style.display=isPdf?'block':'none';
  if(isPdf)$('#originalPdf').src=url;else $('#originalImage').src=url;
};
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>{mode=button.dataset.mode;document.querySelectorAll('[data-mode]').forEach(item=>item.classList.toggle('selected',item===button))});

$('#runTest').onclick=async()=>{
  if(!file)return;marks=[];result=null;page=0;startTime=Date.now();
  $('#statusCard').hidden=false;$('#workspace').hidden=true;$('#reviewPanel').hidden=true;$('#runTest').disabled=true;$('#cancelTest').hidden=false;
  $('#statusTitle').textContent='Uploading score';$('#statusText').textContent='Sending the source to LetterScore…';$('#progressBar').style.width='12%';
  timer=setInterval(()=>{$('#elapsed').textContent=formatTime(Date.now()-startTime)},1000);
  try{
    const body=new FormData();body.append('score',file);body.append('recognitionMode',mode);
    const response=await fetch('/api/recognize-async',{method:'POST',headers:auth(),body});const submitted=await json(response,'Upload');
    if(!response.ok)throw new Error(submitted.error||'Recognition could not be started.');jobId=submitted.jobId;
    $('#statusTitle').textContent=`${file.type==='application/pdf'||/\.pdf$/i.test(file.name)?'Optimized PDF':mode==='best'?'Best Accuracy':'Fast'} recognition`;$('#statusText').textContent='Reading staves, notes, rhythm, and measures…';$('#progressBar').style.width='32%';
    while(true){
      await wait(4000);const check=await fetch('/api/jobs/'+encodeURIComponent(jobId),{headers:auth()});const state=await json(check,'Job status');
      if(!check.ok)throw new Error(state.error||'The recognition job could not be found.');
      if(state.status==='complete'){result=state.result;break}if(state.status==='failed')throw new Error(state.error||'Recognition failed.');if(state.status==='cancelled')throw new Error('Recognition was cancelled.');
      const seconds=(Date.now()-startTime)/1000;$('#progressBar').style.width=Math.min(88,32+seconds/8)+'%';
    }
    duration=Date.now()-startTime;clearInterval(timer);jobId=null;$('#progressBar').style.width='100%';$('#statusTitle').textContent='Recognition complete';$('#statusText').textContent='Mark every difference you find on the converted score.';$('#cancelTest').hidden=true;$('#runTest').disabled=false;
    showResult();
  }catch(error){clearInterval(timer);jobId=null;$('#runTest').disabled=false;$('#cancelTest').hidden=true;$('#statusTitle').textContent='Test failed';$('#statusText').textContent=error.message;$('#progressBar').style.width='100%';toast(error.message)}
};

$('#cancelTest').onclick=async()=>{if(!jobId)return;const response=await fetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`,{method:'POST',headers:auth()});if(response.ok){clearInterval(timer);jobId=null;$('#cancelTest').hidden=true;$('#runTest').disabled=false;$('#statusTitle').textContent='Recognition cancelled';$('#statusText').textContent='Choose Run recognition test when you are ready to try again.'}else toast('The job could not be cancelled')};

function pages(){return result?.learningModes?.all?.pages||[]}
function showResult(){
  $('#workspace').hidden=false;$('#reviewPanel').hidden=false;$('#resultTitle').textContent=(result.fileName||file.name).replace(/\.[^.]+$/,'');
  $('#statMode').textContent=result.recognitionMode==='pdf-optimized-350'?'Optimized PDF':mode==='best'?'Best Accuracy':'Fast';$('#statTime').textContent=formatTime(duration);$('#statNotes').textContent=result.noteCount??'—';
  $('#statMeasures').textContent=result.measureCount??'—';$('#statSuspects').textContent=result.validation?.suspectMeasureCount??'—';
  const labels={preprocessing:'Preprocessing',recognition:'Recognition',scoreAnalysis:'Score check',letterConversion:'Letter conversion',pdfRendering:'PDF rendering',previewRendering:'Preview rendering',total:'Server total'};
  $('#stageTimings').innerHTML=Object.entries(result.stageTimings||{}).map(([key,value])=>`<span>${labels[key]||key}</span><strong>${Number(value).toFixed(1)}s</strong>`).join('');
  const quality=result.qualityAssessment;$('#qualityBox').innerHTML=quality?`<strong>${(quality.confidence||'medium').toUpperCase()} CONFIDENCE</strong><br>${(quality.warnings||[]).join('<br>')}`:'Document source · visual review still recommended';
  page=0;zoom=1;renderPage();updateStats();
}
function renderPage(){
  const available=pages(),source=available[page]||result?.learningModes?.all?.preview;
  if(source)$('#resultImage').src='data:image/png;base64,'+source;
  $('#pageCounter').textContent=`Page ${page+1} of ${Math.max(1,available.length)}`;$('#previousPage').disabled=page===0;$('#nextPage').disabled=page>=available.length-1;
  $('#zoomValue').textContent=Math.round(zoom*100)+'%';$('#scoreLayer').style.width=(zoom*100)+'%';renderMarkers();
}
$('#previousPage').onclick=()=>{if(page>0){page--;renderPage()}};$('#nextPage').onclick=()=>{if(page<pages().length-1){page++;renderPage()}};
document.querySelectorAll('[data-zoom]').forEach(button=>button.onclick=()=>{zoom=Math.max(.5,Math.min(3,zoom+(button.dataset.zoom==='in'?.25:-.25)));renderPage()});

$('#categories').onclick=event=>{const button=event.target.closest('[data-category]');if(!button)return;selectedCategory=button.dataset.category;document.querySelectorAll('[data-category]').forEach(item=>item.classList.toggle('selected',item===button))};
$('#scoreLayer').onclick=event=>{
  if(event.target.closest('.marker')||!result)return;const rect=$('#resultImage').getBoundingClientRect();
  const x=(event.clientX-rect.left)/rect.width*100,y=(event.clientY-rect.top)/rect.height*100;
  if(x<0||x>100||y<0||y>100)return;
  marks.push({id:Date.now()+Math.random(),category:selectedCategory,page:page+1,measure:$('#measureNumber').value.trim()||null,x:+x.toFixed(2),y:+y.toFixed(2)});renderMarkers();updateStats();
};
function renderMarkers(){
  $('#markers').innerHTML=marks.filter(mark=>mark.page===page+1).map((mark,index)=>`<button class="marker ${mark.category}" data-id="${mark.id}" style="left:${mark.x}%;top:${mark.y}%" title="${categories[mark.category]}${mark.measure?' · measure '+mark.measure:''}">${index+1}</button>`).join('');
  document.querySelectorAll('.marker').forEach(marker=>marker.onclick=event=>{event.stopPropagation();marks=marks.filter(mark=>String(mark.id)!==marker.dataset.id);renderMarkers();updateStats()});
}
function counts(){return Object.fromEntries(Object.keys(categories).map(key=>[key,marks.filter(mark=>mark.category===key).length]))}
function accuracy(){const notes=Number(result?.noteCount)||0;return notes?Math.max(0,(1-marks.length/notes)*100):null}
function updateStats(){
  $('#statErrors').textContent=marks.length;const score=accuracy();$('#statAccuracy').textContent=score===null?'—':score.toFixed(1)+'%';
  const totals=counts();$('#breakdown').innerHTML=Object.entries(totals).filter(([,value])=>value).map(([key,value])=>`<span>${categories[key]}: ${value}</span>`).join('')||'<span>No errors marked yet</span>';
}
function report(){return {app:'LetterScore Test Lab',version:2,fileName:file?.name,sourceType:file?.type||'',recognitionMode:result?.recognitionMode||mode,processingMilliseconds:duration,processingTime:formatTime(duration),serverStageTimings:result?.stageTimings||null,rhythmCheck:result?.validation||null,recognizedNotes:result?.noteCount??null,recognizedMeasures:result?.measureCount??null,pages:pages().length,confidence:result?.qualityAssessment?.confidence||null,totalErrors:marks.length,estimatedNoteAccuracy:accuracy(),errorCounts:counts(),errors:marks,notes:$('#testNotes').value.trim(),testedAt:new Date().toISOString()}}
$('#saveTest').onclick=()=>{if(!result)return;const history=JSON.parse(localStorage.getItem('letterScoreBenchmarks')||'[]');history.unshift(report());localStorage.setItem('letterScoreBenchmarks',JSON.stringify(history.slice(0,30)));renderHistory();toast('Test saved for comparison')};
$('#exportReport').onclick=()=>{if(!result)return;const blob=new Blob([JSON.stringify(report(),null,2)],{type:'application/json'}),link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`LetterScore-${mode}-${file.name.replace(/\.[^.]+$/,'')}-report.json`;link.click();URL.revokeObjectURL(link.href);toast('Report downloaded')};
function renderHistory(){const history=JSON.parse(localStorage.getItem('letterScoreBenchmarks')||'[]'),body=$('#historyTable tbody');$('#historyEmpty').hidden=history.length>0;$('#historyTable').hidden=!history.length;body.innerHTML=history.map(test=>`<tr><td>${test.fileName||'Score'}</td><td>${test.recognitionMode==='pdf-optimized-350'?'Optimized PDF':test.recognitionMode==='best'?'Best':'Fast'}</td><td>${test.processingTime}</td><td>${test.totalErrors}</td><td>${test.estimatedNoteAccuracy==null?'—':test.estimatedNoteAccuracy.toFixed(1)+'%'}</td><td>${new Date(test.testedAt).toLocaleDateString()}</td></tr>`).join('')}
$('#clearHistory').onclick=()=>{if(confirm('Clear all saved LetterScore benchmarks from this browser?')){localStorage.removeItem('letterScoreBenchmarks');renderHistory()}};
renderHistory();
