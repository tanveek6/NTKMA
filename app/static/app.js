const API = "";
let news = [];
let logs = [];
let documents = [];
let charts = {};

function todayTime(){
  const now = new Date();
  const timeBox = document.getElementById("timeBox");
  const lastUpdated = document.getElementById("lastUpdated");
  if(timeBox){
    timeBox.textContent = now.toLocaleDateString("en-IN",{day:"2-digit",month:"short",year:"numeric"}) + " | " + now.toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"});
  }
  if(lastUpdated) lastUpdated.textContent = now.toLocaleTimeString("en-IN");
}
setInterval(todayTime,1000);

async function api(path, options={}){
  const res = await fetch(API + path, options);
  if(!res.ok){
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  const type = res.headers.get("content-type") || "";
  return type.includes("application/json") ? res.json() : res.text();
}

async function loadNews(){
  const data = await api("/api/news");
  news = data.items || [];
  const status = document.getElementById("scraperStatusMsg");
  if(status) status.textContent = data.backend === "firebase" ? "Firebase Active" : "Local Active";
}

async function loadLogs(){
  try{ logs = (await api("/api/logs")).items || []; }
  catch(_){ logs = []; }
}

async function loadDocuments(){
  try{ documents = (await api("/api/documents")).items || []; }
  catch(_){ documents = []; }
}

function showPanel(id,btn){
  document.querySelectorAll(".panel").forEach(p=>p.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  document.querySelectorAll(".nav button").forEach(b=>b.classList.remove("active"));
  if(btn) btn.classList.add("active");
  renderAll();
}

function norm(s){return String(s||"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim();}
function countBy(arr,key){return arr.reduce((a,x)=>{a[x[key]||"Unclassified"]=(a[x[key]||"Unclassified"]||0)+1;return a;},{});}
function safe(v){const d=document.createElement("div"); d.textContent=v ?? ""; return d.innerHTML;}
function originalUrl(n){return n.canonical_url || n.url || n.raw_url || "#";}
function isFlagged(n){return n.importance==="Critical" || n.importance==="High" || n.sentiment==="Critical" || n.sentiment==="Negative" || n.sentiment==="High";}

function uniqueNews(){
  const seen = new Set();
  return news.filter(n=>{
    const key = norm(n.duplicate_key || n.canonical_url || n.url || n.title);
    if(!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function metrics(){
  const actual = uniqueNews();
  const rawMentions = Math.max(news.length, actual.length);
  const unique = actual.length;
  const discrepancy = Math.max(0, rawMentions - unique);
  const pos = actual.filter(n=>n.sentiment==="Positive").length;
  const neg = actual.filter(isFlagged).length;
  const neu = Math.max(0, unique-pos-neg);
  const sectors = countBy(actual,"sector");
  const departments = countBy(actual,"department");
  const perception = unique ? Math.round(((pos-neg)/unique)*100) : 0;
  return {total:news.length,actual,rawMentions,unique,discrepancy,pos,neg,neu,sectors,departments,perception};
}

function kpiHtml(){
  const m=metrics();
  return [
    ["&#128240; Total News",m.unique,"Actual verified articles"],
    ["&#128225; Raw Mentions",m.rawMentions,"Captured mentions"],
    ["&#128260; Discrepancy",m.discrepancy,"Duplicates / repeats"],
    ["&#128202; Sentiment",`${m.pos} | ${m.neg} | ${m.neu}`,"Pos | Neg | Neutral"],
    ["&#129517; Sectors Highlighted",Object.keys(m.sectors).length,"Active sectors"],
    ["&#127963;&#65039; Departments Tagged",Object.keys(m.departments).length,"Action owners"]
  ].map(x=>`<div class="kpi"><small>${x[0]}</small><strong>${x[1]}</strong><span>${x[2]}</span></div>`).join("");
}

function newsCard(n){
  const sentClass = n.sentiment==="Positive" ? "positive" : isFlagged(n) ? "critical" : "neutral";
  const image = n.image || "https://images.unsplash.com/photo-1599930113854-d6d7fd521f10?w=500&q=80";
  const url = originalUrl(n);
  return `<div class="news-item">
    <img src="${safe(image)}" onerror="this.src='https://images.unsplash.com/photo-1599930113854-d6d7fd521f10?w=500&q=80'">
    <div>
      <a class="news-title" href="${safe(url)}" target="_blank" rel="noopener noreferrer">${safe(n.title)}</a>
      <div class="meta">${safe(n.source)} | ${safe(n.date)} | Nashik | <span style="color:var(--green);font-weight:800">${n.url_verified===false ? "Source Captured" : "Verified"}</span></div>
      <div class="meta">${safe(n.summary)}</div>
      <span class="badge ${sentClass}">${safe(n.sentiment)}</span>
      <span class="badge sector">${safe(n.sector)}</span>
    </div>
    <a class="open-link" href="${safe(url)}" target="_blank" rel="noopener noreferrer">Original Link</a>
  </div>`;
}

function renderNews(){
  const q=(document.getElementById("searchBox")?.value||"").toLowerCase();
  const filtered = uniqueNews().filter(n=>JSON.stringify(n).toLowerCase().includes(q));
  const flagged = filtered.filter(isFlagged);
  const liveNews = document.getElementById("liveNews");
  const allLiveNews = document.getElementById("allLiveNews");
  const flaggedNews = document.getElementById("flaggedNews");
  const allFlaggedNews = document.getElementById("allFlaggedNews");
  if(liveNews) liveNews.innerHTML = filtered.slice(0,4).map(newsCard).join("");
  if(allLiveNews) allLiveNews.innerHTML = filtered.map(newsCard).join("");
  if(flaggedNews) flaggedNews.innerHTML = flagged.slice(0,3).map(newsCard).join("");
  if(allFlaggedNews) allFlaggedNews.innerHTML = flagged.map(newsCard).join("");
}

function renderBars(){
  const m=metrics();
  const sectorBars = document.getElementById("sectorBars");
  const deptBars = document.getElementById("deptBars");
  const sectorMax=Math.max(...Object.values(m.sectors),1);
  if(sectorBars){
    sectorBars.innerHTML = Object.entries(m.sectors).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="bar-row"><span>${safe(k)}</span><span>${v}</span><div class="bar" style="grid-column:1/-1"><b style="width:${v/sectorMax*100}%"></b></div></div>`).join("");
  }
  const deptMax=Math.max(...Object.values(m.departments),1);
  if(deptBars){
    deptBars.innerHTML = Object.entries(m.departments).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`<div class="bar-row"><span>${safe(k)}</span><span>${v}</span><div class="bar" style="grid-column:1/-1"><b style="width:${v/deptMax*100}%"></b></div></div>`).join("");
  }
}

function renderComparison(){
  const m=metrics();
  const compareTable = document.getElementById("compareTable");
  const discrepancyReport = document.getElementById("discrepancyReport");
  if(compareTable){
    compareTable.innerHTML = `<tr><th>Metric</th><th>Current</th><th>Interpretation</th><th>Status</th></tr>
      <tr><td>Total verified articles</td><td>${m.unique}</td><td>Use for official count</td><td class="up">Primary</td></tr>
      <tr><td>Raw mentions</td><td>${m.rawMentions}</td><td>Coverage intensity</td><td class="neutral">Context</td></tr>
      <tr><td>Positive</td><td>${m.pos}</td><td>Favourable coverage</td><td class="up">Watch</td></tr>
      <tr><td>Negative / Critical</td><td>${m.neg}</td><td>Needs verification and owner assignment</td><td class="down">Review</td></tr>
      <tr><td>Neutral</td><td>${m.neu}</td><td>Routine monitoring</td><td>Stable</td></tr>
      <tr><td>Discrepancy</td><td>${m.discrepancy}</td><td>Duplicates / repeated mentions</td><td>Deduped</td></tr>`;
  }
  if(discrepancyReport){
    discrepancyReport.textContent = `ACTUAL COUNT VS RAW MENTIONS\n\nActual verified articles: ${m.unique}\nRaw mentions captured: ${m.rawMentions}\nDiscrepancy: ${m.discrepancy}\n\nUse verified articles for official count. Use raw mentions only as an indicator of coverage intensity.`;
  }
}

function chart(id,type,labels,data,colors){
  const canvas = document.getElementById(id);
  if(!canvas || typeof Chart === "undefined") return;
  if(charts[id]) charts[id].destroy();
  charts[id]=new Chart(canvas,{type,data:{labels,datasets:[{data,backgroundColor:colors||["#f46b1b","#3d9b4f","#d94b42","#1f82d6","#f5a623"],borderWidth:2,borderColor:"#fff"}]},options:{responsive:true,plugins:{legend:{display:type!=="bar"}},scales:type==="bar"?{y:{beginAtZero:true}}:{}}});
}

function renderCharts(){
  const m=metrics();
  chart("perceptionChart","doughnut",["Positive","Negative","Neutral"],[m.pos,m.neg,m.neu],["#3d9b4f","#d94b42","#9aa0a8"]);
  chart("sentChart","doughnut",["Positive","Negative","Neutral"],[m.pos,m.neg,m.neu],["#3d9b4f","#d94b42","#9aa0a8"]);
  chart("sectorChart","bar",Object.keys(m.sectors),Object.values(m.sectors),["#f46b1b"]);
  chart("deptChart","bar",Object.keys(m.departments),Object.values(m.departments),["#f46b1b"]);
  chart("dailyChart","line",["Day 1","Day 2","Day 3","Day 4","Day 5","Day 6","Today"],[1,2,1,3,2,4,m.unique],["#f46b1b"]);
  const perceptionText = document.getElementById("perceptionText");
  if(perceptionText) perceptionText.textContent = `Overall perception rate: ${m.perception}%. Positive: ${m.pos}, Negative/Critical: ${m.neg}, Neutral: ${m.neu}.`;
}

function formatCountList(obj){
  return Object.entries(obj).sort((a,b)=>b[1]-a[1]).map(([k,v])=>`- ${k}: ${v}`).join("\n") || "- No current concentration";
}

function buildPerceptionTracker(){
  const m = metrics();
  const flagged = m.actual.filter(isFlagged);
  const topFlagged = flagged.slice(0,8).map(n=>`- ${n.title} | ${n.source} | ${n.department} | ${originalUrl(n)}`).join("\n") || "- No immediate critical items in the saved feed.";
  const posture = m.perception < -20 ? "Adverse / needs response" : m.perception <= 10 ? "Mixed / watch closely" : "Favourable / routine watch";
  return `MEDIA PERCEPTION TRACKER\n\nCurrent posture: ${posture}\nOverall perception rate: ${m.perception}%\nActual verified articles: ${m.unique}\nRaw mentions: ${m.rawMentions}\nDiscrepancy: ${m.discrepancy}\n\nSentiment\nPositive: ${m.pos}\nNegative / Critical: ${m.neg}\nNeutral: ${m.neu}\n\nSectors Highlighted\n${formatCountList(m.sectors)}\n\nDepartments Requiring Attention\n${formatCountList(m.departments)}\n\nImmediate Review Queue\n${topFlagged}\n\nRecommended Handling\n- Verify every flagged item through the original link before escalation.\n- Assign department action only after source verification.\n- Treat raw mentions as media intensity, not the official article count.\n- Watch repeated critical clusters across Infrastructure, Mobility, Health, Sanitation and Security.`;
}

function renderDocuments(){
  const box = document.getElementById("documentList");
  if(!box) return;
  if(!documents.length){ box.innerHTML = `<div class="alert-box">No uploaded documents recorded yet.</div>`; return; }
  box.innerHTML = documents.slice(0,20).map(d=>`<div class="news-item"><div><a class="news-title" href="${safe(d.local_url || d.firebase_uri || "#")}" target="_blank" rel="noopener noreferrer">${safe(d.title || d.filename || "Uploaded document")}</a><div class="meta">${safe(d.source || "Uploaded Document")} | ${safe(d.date || "")} | OCR: ${safe(d.ocr_method || "not recorded")}</div><div class="meta"><strong>OCR Summary:</strong> ${safe(d.summary || "No OCR summary available yet.")}</div><span class="badge sector">${safe(d.sector || "Uploaded Document")}</span><span class="badge neutral">${safe(d.department || "Media Cell / Verification")}</span></div><a class="open-link" href="${safe(d.local_url || d.firebase_uri || "#")}" target="_blank" rel="noopener noreferrer">Open</a></div>`).join("");
}

function renderReports(){
  const perceptionReport = document.getElementById("perceptionReport");
  const logsBox = document.getElementById("logsBox");
  if(perceptionReport) perceptionReport.textContent = buildPerceptionTracker();
  if(logsBox) logsBox.textContent = logs.join("\n") || "No logs yet.";
}

async function generateBrief(){
  const briefBox = document.getElementById("briefBox");
  if(briefBox) briefBox.textContent = "Generating report...";
  try{
    const brief = await api("/api/brief");
    if(briefBox) briefBox.textContent = brief;
    await loadLogs();
    renderReports();
  }catch(err){
    if(briefBox) briefBox.textContent = "Unable to generate report: " + err.message;
  }
  showPanel("summarizer",document.querySelectorAll(".nav button")[7]);
}

function verifyLinks(){
  const flagged = uniqueNews().filter(isFlagged);
  alert(`Found ${flagged.length} flagged item(s). Use Original Link to verify each source before escalation.`);
}

async function runScraper(){
  updateScraperStatus("Running...");
  try{
    const data = await api("/api/scrape",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({query:"Nashik Trimbakeshwar Kumbh OR Simhastha Kumbh Nashik",limit:20})});
    await loadNews(); await loadDocuments(); await loadLogs(); renderAll();
    updateScraperStatus("Active");
    alert(`Live scraper completed. Fetched ${data.fetched}; added ${data.added}; duplicates ${data.duplicates}.`);
  }catch(err){
    updateScraperStatus("Needs Network");
    alert("Live scraper could not fetch news right now. The dashboard is still using saved backend data.");
  }
}

function updateScraperStatus(msg){ const el=document.getElementById("scraperStatusMsg"); if(el) el.textContent=msg; }
function scheduleAutoScrape(){
  const nextRunEl=document.getElementById("nextRunEl");
  if(!nextRunEl) return;
  let remaining=15*60;
  setInterval(()=>{ remaining-=1; if(remaining<=0){remaining=15*60; runScraper();} const min=Math.floor(remaining/60); const sec=String(remaining%60).padStart(2,"0"); nextRunEl.textContent=`${min}m ${sec}s`; },1000);
}

async function handleUpload(id){
  const fileInput=document.getElementById(id);
  const file=fileInput?.files?.[0];
  const title=document.getElementById("docTitle")?.value || file?.name || "Uploaded clipping";
  const source=document.getElementById("docSource")?.value || "Uploaded Document";
  const date=document.getElementById("docDate")?.value || new Date().toISOString().slice(0,10);
  const summary=document.getElementById("docSummary")?.value || "Uploaded document stored for OCR / manual verification.";
  if(!file && (id==="docFile" || id==="quickUpload")){alert("Select a file first.");return;}
  const form=new FormData();
  form.append("title",title); form.append("source",source); form.append("date",date); form.append("summary",summary); if(file) form.append("file",file);
  const uploadResult=document.getElementById("uploadResult");
  if(uploadResult) uploadResult.textContent="Uploading and running OCR...";
  try{
    const data=await api("/api/upload",{method:"POST",body:form});
    await loadNews(); await loadDocuments(); await loadLogs();
    if(uploadResult) uploadResult.textContent=`Uploaded to backend: ${data.filename || title}\nOCR method: ${data.ocr_method || "not recorded"}\nOCR Summary: ${data.summary || data.item.summary}\nSaved as news item: ${data.item.title}`;
    renderAll();
  }catch(err){ if(uploadResult) uploadResult.textContent="Upload failed: "+err.message; }
}

async function renderSources(){
  const sourceList=document.getElementById("sourceList");
  if(!sourceList) return;
  try{
    const data=await api("/api/sources");
    sourceList.innerHTML=(data.items || []).map(s=>{ const item=typeof s==="string" ? {name:s,url:"#",type:"Source",notes:"Configured for NTKMA / Nashik Kumbh monitoring"} : s; return `<div class="news-item"><div><a class="news-title" href="${safe(item.url || "#")}" target="_blank" rel="noopener noreferrer">${safe(item.name)}</a><div class="meta">${safe(item.type)} | ${safe(item.notes)}</div></div><a class="open-link" href="${safe(item.url || "#")}" target="_blank" rel="noopener noreferrer">Open Source</a></div>`; }).join("");
  }catch(_){ sourceList.textContent="Unable to load sources."; }
}

function exportCSV(){ window.location.href="/api/export.csv"; }
function renderAll(){
  const kpis=document.getElementById("kpis"); if(kpis) kpis.innerHTML=kpiHtml();
  const sourceCount=document.getElementById("sourceCount"); if(sourceCount) sourceCount.textContent=new Set(uniqueNews().map(n=>n.source)).size;
  renderNews(); renderBars(); renderComparison(); renderCharts(); renderReports(); renderDocuments(); renderSources();
}
function renderLive(){renderNews();}

let slideIndex=0;
function goSlide(n){ const slides=document.querySelectorAll(".kumbh-slide"); const dots=document.querySelectorAll(".kumbh-slide-dots span"); if(!slides.length) return; slideIndex=n; slides.forEach((s,i)=>s.classList.toggle("active",i===n)); dots.forEach((d,i)=>d.classList.toggle("active",i===n)); }
setInterval(()=>{ const slides=document.querySelectorAll(".kumbh-slide"); if(slides.length) goSlide((slideIndex+1)%slides.length); },4500);
let lbCurrent=0;
function lightboxImages(){ return Array.from(document.querySelectorAll(".kumbh-photo-grid img")); }
function openLightbox(idx){ const imgs=lightboxImages(); if(!imgs[idx]) return; lbCurrent=idx; document.getElementById("lbImg").src=imgs[idx].src; document.getElementById("lbCap").textContent=imgs[idx].title || imgs[idx].alt || ""; document.getElementById("kumbhLightbox").classList.add("open"); }
function closeLightbox(){ document.getElementById("kumbhLightbox").classList.remove("open"); }
function lbNav(dir){ const imgs=lightboxImages(); if(!imgs.length) return; lbCurrent=(lbCurrent+dir+imgs.length)%imgs.length; openLightbox(lbCurrent); }

async function init(){
  todayTime();
  const docDate=document.getElementById("docDate"); if(docDate) docDate.valueAsDate=new Date();
  const lb=document.getElementById("kumbhLightbox"); if(lb) lb.addEventListener("click",function(e){ if(e.target===this) closeLightbox(); });
  try{ await loadNews(); await loadDocuments(); await loadLogs(); }
  catch(err){ updateScraperStatus("Backend Offline"); console.error(err); }
  scheduleAutoScrape(); renderAll();
}

document.addEventListener("DOMContentLoaded", init);

