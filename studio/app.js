'use strict';
const $ = selector => document.querySelector(selector);
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const options = (entries, selected) => Object.entries(entries).map(([key, label]) => `<option value="${escapeText(key)}" ${String(selected) === key ? 'selected' : ''}>${escapeText(label)}</option>`).join('');
const styles = {podcast:'Premium podcast', business:'Business education', value:'Value-driven', cinematic:'Cinematic story', egyptian:'Egyptian education', fashion:'Fashion campaign', workshop:'Founder workshop', gaming:'Gaming & entertainment', minimal:'Minimal professional'};
const platforms = {shorts:'YouTube Shorts · 9:16', reels:'Instagram Reels · 9:16', tiktok:'TikTok · 9:16', square:'Square · 1:1', landscape:'Landscape · 16:9'};
const reviews = {pending:'Pending review', approved:'Approved', rejected:'Rejected'};
const statuses = {queued:'Queued', processing:'Processing', review:'In review', failed:'Needs attention'};
const names = {projects:'Project library', desk:'Review desk', exports:'Export center'};
const tabNames = {details:'Clip details', captions:'Transcript & captions', settings:'Render settings', review:'Review & delivery'};
const state = {csrf:'', model:false, projects:[], project:null, clipId:null, view:'projects', tab:'details', filter:'all', query:'', page:0, busy:false, version:0};
let noticeTimer;

function clock(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  const m = Math.floor(s / 60);
  return (m > 59 ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}` : m) + ':' + String(s % 60).padStart(2, '0');
}
function meta(items) {
  return `<div class="meta">${items.filter(Boolean).map(v => `<span>${escapeText(v)}</span>`).join('')}</div>`;
}
function badge(label, tone='') { return `<span class="badge ${tone}">${escapeText(label)}</span>`; }
function notice(message, error=false) {
  const node = $('#notice');
  node.textContent = message;
  node.className = error ? 'bad' : '';
  node.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { node.hidden = true; }, error ? 8000 : 3500);
}
async function api(url, body) {
  const response = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json', 'X-ClipOps-CSRF':state.csrf}, body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function current() { return (state.project?.candidates || []).find(c => c.id === state.clipId); }
function projectUrl(action) { return `/api/projects/${state.project.id}/${action}`; }
function mediaUrl(kind, clip=current()) {
  const base = `/media/${state.project.id}/`;
  return kind === 'source' ? base + 'source' : base + clip.id + '/' + kind;
}
function notifyError(error) {
  const box = $('#dialog[open] .error-banner');
  if (box) box.textContent = error.message;
  else notice(error.message, true);
}
function openDialog(title, html) {
  $('#dialog-title').textContent = title;
  $('#dialog-body').innerHTML = `<p role="alert" class="error-banner"></p>${html}`;
  if (!$('#dialog').open) $('#dialog').showModal();
}
function closeDialog() { $('#dialog').close(); }
function formField(label, control, wide=false) { return `<label class="field ${wide ? 'wide' : ''}">${label}${control}</label>`; }
function button(action, label, cls='', disabled=false) { return `<button type="button" class="button ${cls}" data-action="${action}" ${disabled ? 'disabled' : ''}>${label}</button>`; }
function titleBar(text, subtitle, buttons='') {
  return `<div class="heading"><div><h1>${escapeText(text)}</h1>${subtitle}</div><div class="actions">${buttons}</div></div>`;
}
function empty(title, message, action='') {
  return `<div class="empty"><h3>${escapeText(title)}</h3><p>${escapeText(message)}</p>${action}</div>`;
}
function setNav() {
  $('#breadcrumb').textContent = names[state.view];
  document.title = `${names[state.view]} · ClipOps Studio`;
  for (const link of document.querySelectorAll('[data-view]')) {
    if (link.dataset.view === state.view) link.setAttribute('aria-current','page');
    else link.removeAttribute('aria-current');
    if (link.dataset.view !== 'projects') link.href = `#${link.dataset.view}/${state.project?.id || ''}`;
  }
  $('#project-links').innerHTML = state.projects.map(p => `<a class="${p.id === state.project?.id ? 'selected' : ''}" href="#desk/${p.id}">${escapeText(p.name)}</a>`).join('');
}
function setClip(project, newId) {
  if (state.project?.id !== project.id) {
    state.tab = 'details'; state.query = ''; state.page = 0; state.filter = 'all';
  }
  state.project = project;
  const preferred = newId || state.clipId;
  state.clipId = project.candidates.find(c => c.id === preferred)?.id || project.candidates[0]?.id || null;
}
async function route() {
  const version = ++state.version;
  let [view, id] = location.hash.slice(1).split('/');
  if (!names[view]) view = state.projects.length ? 'desk' : 'projects';
  state.view = view;
  if (view !== 'projects') {
    id ||= state.project?.id || state.projects[0]?.id;
    if (id) {
      if (!/^[a-f0-9]{32}$/.test(id)) throw new Error('Invalid project link. Choose a project from the library.');
      const project = await api(`/api/projects/${id}`);
      if (version !== state.version) return;
      setClip(project);
    }
  }
  draw();
}
async function refresh() {
  const version = ++state.version;
  const projectId = state.project?.id;
  const [projects, project] = await Promise.all([api('/api/projects'), projectId ? api(`/api/projects/${projectId}`) : Promise.resolve(null)]);
  if (version !== state.version) return;
  state.projects = projects;
  if (project) setClip(project);
  draw();
}
function library() {
  const projects = state.projects;
  if (!projects.length) return titleBar('Project library', '') + `<section class="panel empty-studio">${empty('Start a project', 'Import authorized footage and a timestamped transcript, or use a local speech model.', button('import','Import project','primary'))}</section>`;
  return titleBar('Project library',meta([`${projects.length} local project${projects.length === 1 ? '' : 's'}`])) + `<section class="panel"><div class="panel-head"><h2>All projects</h2></div><div class="library-table">${projects.map(p => `<div class="list-row"><div><a class="project-link" href="#desk/${p.id}">${escapeText(p.name)}</a><small>${escapeText([p.source.name, platforms[p.platform]].filter(Boolean).join(' · '))}</small></div>${badge(statuses[p.status] || p.status, p.status === 'failed' ? 'bad' : '')}</div>`).join('')}</div></section>`;
}
function downloads(clip) {
  return ['export','srt','vtt'].map(type => `<a class="download" href="${mediaUrl(type, clip)}" download>${type === 'export' ? '↓ MP4' : type.toUpperCase()}</a>`).join('');
}
function exportsPage() {
  const p = state.project;
  const deliverable = p.candidates.filter(c => c.rendered && c.qc?.passed && c.review === 'approved');
  return titleBar('Export center', meta([p.name, `${deliverable.length} approved for delivery`])) + `<section class="panel"><div class="panel-head"><h2>Approved clips</h2></div>${deliverable.length ? `<div class="export-list">${deliverable.map(c => `<div class="list-row"><div><strong dir="auto">${escapeText(c.title)}</strong><small>${clock(c.start)}–${clock(c.end)} · ${escapeText(c.editor || '')}</small></div><div class="actions">${downloads(c)}</div></div>`).join('')}</div>` : empty('No approved exports', 'Review a rendered clip and confirm its rights to unlock delivery.', `<a class="button" href="#desk/${p.id}">Open review desk</a>`)}</section>`;
}
function projectMeta(p) {
  const src = p.source;
  return meta([statuses[p.status] || p.status, src.duration ? clock(src.duration) + ' source' : '', src.dimensions?.join(' × '), src.name]);
}
function progress(p) {
  if (!p.busy && p.status !== 'processing') return '';
  const stage = typeof p.stage === 'string' ? p.stage.replaceAll('_',' ') : 'Processing';
  let value = p.progress;
  if (value && typeof value === 'object') value = Number(value.completed ?? value.done) / Number(value.total);
  const measured = typeof value === 'number' && Number.isFinite(value);
  return `<div class="progress" role="status"><progress ${measured ? `value="${Math.min(100, value)}" max="100"` : ''}></progress>${escapeText(stage)}</div>`;
}
function candidateRows() {
  const rows = state.project.candidates.map((c,i) => ({c, rank:i + 1})).filter(({c}) => state.filter === 'all' || c.review === state.filter);
  if (!rows.length) return empty('No matching candidates', state.project.candidates.length ? 'Choose another review filter.' : 'The queue fills when transcript analysis finds suitable material.');
  return rows.map(({c,rank}) => `<button type="button" class="candidate ${c.id === state.clipId ? 'selected' : ''}" data-clip="${c.id}" aria-pressed="${c.id === state.clipId}"><span class="rank">${rank}</span><span><strong dir="auto">${escapeText(c.title || c.preview)}</strong><small><span>${clock(c.start)}–${clock(c.end)}</span><span>·</span><span>${escapeText(reviews[c.review] || 'Pending review')}</span></small></span><span class="score" title="Editorial ranking points" aria-label="${escapeText(c.score)} editorial points">${escapeText(c.score)} <s>pts</s></span></button>`).join('');
}
function monitor() {
  const c = current(), p = state.project;
  const rendered = Boolean(c?.rendered);
  const length = c ? (rendered ? c.render?.duration ?? c.end - c.start : c.end - c.start) : p.source.duration;
  const title = c?.title || p.source.name;
  const platform = rendered ? (platforms[p.platform] || p.platform).split(' · ')[0] : 'Original footage';
  return `<section class="monitor" aria-label="Video preview"><div class="monitor-head"><span>${rendered ? 'Rendered preview' : 'Source preview'}</span><span class="mono">${escapeText(platform)}</span></div><div class="screen"><video id="video" preload="auto" playsinline aria-label="${escapeText(title)}" src="${mediaUrl(rendered ? 'preview' : 'source')}?v=${state.version}"></video></div><div class="transport"><button class="icon-button" data-action="play" aria-label="Play preview" id="play-toggle">▶</button><input id="scrub" type="range" min="0" max="${Number(length) || 0}" step="0.05" value="0" aria-label="Preview timeline"><span class="mono"><time id="elapsed">0:00</time> / ${clock(length)}</span><button class="icon-button" data-action="full" aria-label="Full screen preview">⛶</button></div><div class="monitor-foot"><strong dir="auto">${escapeText(title)}</strong><span>${c ? `${clock(c.start)}–${clock(c.end)}` : 'Full source'}</span></div></section>`;
}
function desk() {
  const p = state.project;
  const disabled = p.busy;
  const actions = p.candidates.length ? button('batch','Render batch','dark',disabled) : button('resume',p.status === 'failed' || p.status === 'processing' ? 'Resume processing' : 'Analyze source','dark',disabled);
  return titleBar(p.name, projectMeta(p), actions) + (p.error ? `<div role="alert" class="error-banner">${escapeText(p.error)}</div>` : '') + progress(p) + `<div class="studio-grid">${monitor()}<section class="panel queue"><div class="panel-head"><h2>Candidates <span class="count">${p.candidates.length}</span></h2><select class="compact" id="filter" aria-label="Filter candidates">${options({all:'All decisions', ...reviews}, state.filter)}</select></div><div class="candidate-list" id="candidates">${candidateRows()}</div></section></div><section class="panel inspector"><div class="tabs" role="group" aria-label="Inspector views">${Object.entries(tabNames).map(([k,v]) => `<button data-tab="${k}" aria-pressed="${k === state.tab}">${v}</button>`).join('')}</div><div class="tab-body" id="tab-body"></div></section>`;
}
function details() {
  const c = current();
  if (!c) return empty('No clip selected','Select a candidate once analysis finishes.');
  return `<div class="detail-grid"><form id="details-form"><div class="form-grid">${formField('Clip title', `<input name="title" required maxlength="160" value="${escapeText(c.title)}" dir="auto">`, true)}${formField('Start (source seconds)',`<input name="start" type="number" step="0.01" min="0" required value="${Number(c.start)}">`)}${formField('End (source seconds)',`<input name="end" type="number" step="0.01" min="0.01" required value="${Number(c.end)}">`)}${formField('Description',`<textarea name="description" rows="2" dir="auto">${escapeText(c.description)}</textarea>`,true)}${formField('Call to action',`<input name="cta" value="${escapeText(c.cta)}" dir="auto">`,true)}</div><div class="form-footer"><button class="button dark" ${state.project.busy ? 'disabled' : ''}>Save clip edits</button>${button('cut-dialog','Review pause and filler cuts','',state.project.busy)}${button('render-one','Render this clip','',state.project.busy)}</div></form><aside><h3>Selection rationale</h3><p class="hint">${c.selection_edited ? 'Original selection score' : 'Editorial score'} · ${escapeText(c.score)} points</p>${c.render_error ? `<p class="error-banner">${escapeText(c.render_error)}</p>` : ''}${c.render?.framing_reason ? `<p class="hint">${escapeText(c.render.framing_reason)}</p>` : ''}<ul class="rationale">${(Array.isArray(c.rationale) ? c.rationale : [c.rationale]).filter(Boolean).map(reason => `<li>${escapeText(reason)}</li>`).join('')}</ul></aside></div>`;
}
function transcriptList() {
  const all = state.project.segments;
  const query = state.query.toLocaleLowerCase();
  const hits = all.map((segment,i) => ({segment,i})).filter(({segment}) => String(segment.text).toLocaleLowerCase().includes(query));
  const size = 16;
  const last = Math.max(0,Math.ceil(hits.length / size) - 1);
  state.page = Math.min(last, state.page);
  const rows = hits.slice(state.page * size, (state.page + 1) * size);
  return `<p class="hint">${hits.length} ${query ? 'matching' : 'timestamped'} cue${hits.length === 1 ? '' : 's'}</p>${rows.map(({segment:s,i}) => `<div class="cue"><button class="link" data-seek="${i}" title="Play source from this cue"><time>${clock(s.start)}</time></button><p dir="auto">${escapeText(s.speaker ? s.speaker + ' · ' : '')}${escapeText(s.text)}</p><button class="link" data-edit-cue="${i}" aria-label="Edit cue at ${clock(s.start)}">Edit</button></div>`).join('')}${!hits.length ? empty('No cues found', query ? 'Try another search term.' : 'Import or transcribe the source to edit timed captions.') : ''}${last > 0 ? `<div class="pages">${button('previous','Previous','',state.page === 0)}<small>Page ${state.page + 1} of ${last + 1}</small>${button('next','Next','',state.page === last)}</div>` : ''}`;
}
function captions() {
  return `<div class="transcript-tools"><h3>Source transcript</h3><input id="search" class="search" type="search" placeholder="Search transcript" aria-label="Search transcript" value="${escapeText(state.query)}"></div><div id="transcript-list">${transcriptList()}</div>`;
}
function settings() {
  const p = state.project, brand = p.brand || {};
  const fonts = Object.fromEntries(['DejaVu Sans','DejaVu Serif','Liberation Sans','Noto Sans Arabic'].map(f => [f,f]));
  return `<form id="settings-form"><div class="form-grid">${formField('Editing style',`<select name="style">${options(styles,p.style)}</select>`)}${formField('Export format',`<select name="platform">${options(platforms,p.platform)}</select>`)}${formField('Canvas resolution',`<select name="resolution">${options({720:'720p',1080:'1080p',2160:'4K · source-supported'},p.resolution || 1080)}</select>`)}${formField('Framing',`<select name="framing">${options({contain:'Keep the full frame',crop:'Center crop',faces:'Face-guided crop',speaker:'Follow labeled speakers',split:'Two-speaker layout'},p.framing || 'contain')}</select>`)}${formField('Caption font',`<select name="font"><option value="">Style default</option>${options(fonts,brand.font)}</select>`)}${formField('Brand accent',`<input name="accent" placeholder="#A4DC66" maxlength="7" pattern="#[0-9A-Fa-f]{6}" value="${escapeText(brand.accent)}">`)}${formField('Caption text color',`<input name="text" placeholder="Style default" maxlength="7" pattern="#[0-9A-Fa-f]{6}" value="${escapeText(brand.text)}">`)}${formField('Fill color',`<input name="background" placeholder="Style default" maxlength="7" pattern="#[0-9A-Fa-f]{6}" value="${escapeText(brand.background)}">`)}${formField('Speaker positions',`<input name="positions" placeholder='{"Host":0.28,"Guest":0.72}' value="${escapeText(Object.keys(p.speaker_positions || {}).length ? JSON.stringify(p.speaker_positions) : '')}"><small class="hint">Use transcript speaker labels and horizontal positions from 0 to 1.</small>`,true)}<label class="check"><input type="checkbox" name="cleanup" ${p.cleanup ? 'checked' : ''}> Reduce background noise</label><label class="check"><input type="checkbox" name="push_in" ${p.push_in ? 'checked' : ''}> Add a gentle push-in</label></div><div class="form-footer"><button class="button dark" ${p.busy ? 'disabled' : ''}>Save render settings</button><small class="hint">Changed settings require a new render and review.</small></div></form><div class="form-footer">${button('purge','Delete local project','danger',p.busy)}</div>`;
}
function review() {
  const c = current();
  if (!c) return empty('No clip selected','Select a candidate to begin editorial review.');
  const passed = c.qc?.passed === true;
  const checks = c.qc?.checks || {};
  const failed = Array.isArray(checks) ? checks.filter(v => v?.passed === false).map(v => v.name || v.id) : Object.entries(checks).filter(([,v]) => v === false || v?.passed === false).map(([k]) => k);
  return `<div class="review-block"><div class="inline">${badge(reviews[c.review] || reviews.pending, c.review === 'approved' ? 'good' : c.review === 'rejected' ? 'bad' : '')}${badge(passed ? 'Technical QC passed' : c.qc ? 'Technical QC needs attention' : 'Awaiting render QC', passed ? 'good' : 'warn')}</div>${failed.length ? `<p class="hint">Flagged checks · ${escapeText(failed.join(', '))}</p>` : ''}<p class="hint">Check the story, subject framing, caption accuracy, lip sync and asset permissions before approval.</p><form id="review-form" class="review-block">${formField('Editor',`<input name="editor" maxlength="100" placeholder="Editor name" required value="${escapeText(c.editor)}">`)}<label class="check"><input type="checkbox" name="rights"> I have reviewed this exact render and confirm editorial approval and media rights.</label><div class="actions"><button class="button" name="decision" value="assigned">Assign editor</button><button class="button danger" name="decision" value="rejected">Reject clip</button><button class="button primary" name="decision" value="approved" ${!passed || !c.rendered || state.project.busy ? 'disabled' : ''}>Approve for delivery</button></div></form>${c.review === 'approved' && passed && c.rendered ? `<div class="actions">${downloads(c)}</div>` : ''}</div>`;
}
function drawTab() {
  const area = $('#tab-body');
  if (!area) return;
  for (const tab of document.querySelectorAll('[data-tab]')) tab.setAttribute('aria-pressed', String(tab.dataset.tab === state.tab));
  area.innerHTML = ({details,captions,settings,review})[state.tab]();
}
function draw() {
  setNav();
  const main = $('#main');
  main.setAttribute('aria-busy', 'false');
  if (state.view === 'projects') main.innerHTML = library();
  else if (!state.project) main.innerHTML = titleBar(names[state.view], '') + `<section class="panel empty-studio">${empty('Choose a project','Import footage or select a project in the library.',`<a href="#projects" class="button">Project library</a>`)}</section>`;
  else if (state.view === 'exports') main.innerHTML = exportsPage();
  else { main.innerHTML = desk(); bindVideo(); drawTab(); }
}
function bindVideo(sourceCue=null) {
  const video = $('#video');
  if (!video) return;
  const c = current();
  const start = sourceCue === null ? (c?.rendered ? 0 : c?.start || 0) : 0;
  const end = sourceCue === null ? (c?.rendered ? c.render?.duration ?? c.end - c.start : c?.end || state.project.source.duration) : state.project.source.duration;
  const seek = sourceCue === null ? start : sourceCue;
  const slider = $('#scrub');
  slider.max = end - start;
  const play = $('#play-toggle');
  const toggle = () => {
    play.textContent = video.paused ? '▶' : 'Ⅱ';
    play.setAttribute('aria-label', video.paused ? 'Play preview' : 'Pause preview');
  };
  video.onloadedmetadata = () => { if (seek > 0) video.currentTime = seek; };
  video.ontimeupdate = () => {
    if (video.currentTime > end && !video.paused) { video.pause(); video.currentTime = end; }
    $('#elapsed').textContent = clock(video.currentTime - start);
    slider.value = Math.max(0,video.currentTime - start);
  };
  video.onplay = toggle; video.onpause = toggle; video.onended = toggle;
  play.onclick = () => {
    if (video.paused) {
      if (video.currentTime >= end - 0.05 || video.currentTime < start) video.currentTime = start;
      video.play().catch(notifyError);
    } else video.pause();
  };
  slider.oninput = () => { video.currentTime = start + Number(slider.value); };
}
function importDialog() {
  openDialog('Import project', `<form id="import-form"><div class="form-grid">${formField('Project name','<input name="name" maxlength="140" placeholder="Use source filename">',true)}${formField('Source video','<input name="video" type="file" accept=".mp4,.mov,.mkv,.webm" required><small class="hint">MP4, MOV, MKV or WebM. Up to 6 GiB per import.</small>',true)}${formField('Timestamped transcript',`<input name="transcript" type="file" accept=".json,application/json" ${state.model ? '' : 'required'}><small class="hint">${state.model ? 'Optional. A local speech model is available.' : 'Import a JSON transcript with start, end and text for each cue.'}</small>`,true)}${formField('Editing style',`<select name="style">${options(styles,'podcast')}</select>`)}${formField('Export format',`<select name="platform">${options(platforms,'shorts')}</select>`)}${formField('Initial renders','<input type="number" min="0" max="30" name="count" value="5" required><small class="hint">Use zero to rank candidates first.</small>',true)}<label class="check wide"><input type="checkbox" name="rights" required> I have permission to process this footage and transcript locally.</label><progress class="upload-progress wide" id="upload-progress" max="100" value="0" hidden></progress></div><div class="form-footer"><button class="button primary">Import & process</button></div></form>`);
}
async function upload(form) {
  const file = form.video.files[0];
  if (file.size > 6 * 1024**3) throw new Error('Video exceeds the 6 GiB limit.');
  const transcript = form.transcript.files[0];
  if (transcript && transcript.size > 16 * 1024**2) throw new Error('The transcript exceeds 16 MiB.');
  const spec = {filename:file.name, mime:file.type, name:form.elements.namedItem('name').value, rights:form.rights.checked,
    transcript:transcript ? JSON.parse(await transcript.text()) : null, style:form.elements.namedItem('style').value,
    platform:form.platform.value, render_count:Number(form.count.value)};
  const metadata = new TextEncoder().encode(JSON.stringify(spec));
  const progressBar = $('#upload-progress'); progressBar.hidden = false;
  const result = await new Promise((resolve,reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST','/api/import'); xhr.responseType = 'json';
    xhr.setRequestHeader('Content-Type','application/octet-stream'); xhr.setRequestHeader('X-ClipOps-CSRF',state.csrf);
    xhr.setRequestHeader('X-ClipOps-Metadata-Length',String(metadata.byteLength));
    xhr.upload.onprogress = ev => { if (ev.lengthComputable) progressBar.value = 100 * ev.loaded / ev.total; };
    xhr.onerror = () => reject(new Error('The local upload was interrupted.'));
    xhr.onload = () => xhr.status === 201 ? resolve(xhr.response) : reject(new Error(xhr.response?.error || `Import failed (${xhr.status})`));
    xhr.send(new Blob([metadata,file]));
  });
  closeDialog(); state.projects = await api('/api/projects'); location.hash = `desk/${result.id}`;
  notice(result.message || 'Footage imported. Processing locally.');
}
function batchDialog() {
  const candidates = state.project.candidates;
  openDialog('Render batch', `<form id="batch-form"><p class="hint">Choose the clips to render with the current project settings.</p><div class="batch-list">${candidates.map(c => `<label class="check"><input type="checkbox" name="ids" value="${c.id}" ${c.id === state.clipId ? 'checked' : ''}><span dir="auto">${escapeText(c.title)}</span></label>`).join('')}</div><div class="form-footer"><button class="button primary">Render selected clips</button></div></form>`);
}
function cueDialog(index) {
  const s = state.project.segments[index];
  openDialog('Edit caption',`<form id="cue-form" data-index="${index}"><div class="form-grid">${formField('Start (source seconds)',`<input type="number" step="0.001" name="start" required min="0" value="${Number(s.start)}">`)}${formField('End (source seconds)',`<input type="number" step="0.001" name="end" required min="0.001" value="${Number(s.end)}">`)}${formField('Caption text',`<textarea rows="3" name="text" dir="auto" required>${escapeText(s.text)}</textarea>`,true)}</div><div class="form-footer"><button class="button primary">Save caption</button></div></form>`);
}
async function cutDialog() {
  const c = current();
  const suggestions = await api(projectUrl(c.id + '/cuts'));
  const ranges = (c.remove_ranges || []).map(pair => pair.join(', ')).join('\n');
  const rows = suggestions.map((cut, i) => `<div class="cut-suggestion"><span><b>${cut.start.toFixed(3)} – ${cut.end.toFixed(3)} s</b><br><small>${escapeText(cut.reason)}</small></span><button class="button" type="button" data-cut-append="${i}" data-start="${cut.start}" data-end="${cut.end}">Add interval</button></div>`).join('');
  openDialog('Review cuts', `<form id="cuts-form"><p class="hint">Listen at each interval before applying it. Keep breaths or pauses that carry meaning.</p>${rows || '<p class="hint">No pauses or isolated filler were suggested in this selection.</p>'}${formField('Reviewed source intervals', `<textarea name="cuts" rows="4" placeholder="12.400, 13.200">${escapeText(ranges)}</textarea><small class="hint">Enter one start, end pair per line, in source seconds. A blank list keeps the entire selection.</small>`)}<div class="form-footer"><button class="button primary">Save reviewed cuts</button></div></form>`);
}
async function editRequest(data, message) {
  await api(projectUrl('edit'), data); if ($('#dialog').open) closeDialog(); await refresh(); notice(message);
}
async function renderRequest(ids=null) {
  await api(projectUrl('render'), {render_count:ids?.length || 5, clip_ids:ids});
  if ($('#dialog').open) closeDialog(); await refresh(); notice('Added to the local render queue.');
}
async function onSubmit(form, submitter) {
  const data = Object.fromEntries(new FormData(form));
  switch (form.id) {
    case 'import-form': return upload(form);
    case 'details-form': return editRequest({candidate_id:current().id,title:data.title,start:Number(data.start),end:Number(data.end),description:data.description,cta:data.cta},'Clip edits saved.');
    case 'settings-form': {
      const brand = {};
      for (const key of ['font','accent','text','background']) if (data[key]) brand[key] = data[key];
      const speaker_positions = data.positions ? JSON.parse(data.positions) : {};
      return editRequest({style:data.style,platform:data.platform,resolution:Number(data.resolution),framing:data.framing,brand,
        speaker_positions, cleanup:form.cleanup.checked, push_in:form.push_in.checked},'Render settings saved.');
    }
    case 'cuts-form': {
      const ranges = data.cuts.trim() ? data.cuts.trim().split(/\n+/).map(line => {
        const parts = line.split(',').map(part => part.trim());
        if (parts.length !== 2 || parts.some(part => !part || !Number.isFinite(Number(part)))) {
          throw new Error('Enter each interval as two numbers separated by a comma.');
        }
        return parts.map(Number);
      }) : [];
      return editRequest({candidate_id:current().id,remove_ranges:ranges},'Reviewed cuts saved.');
    }
    case 'cue-form': {
      const index = Number(form.dataset.index), segments = state.project.segments.slice();
      const previous = segments[index];
      if (data.text !== previous.text || Number(data.start) !== previous.start || Number(data.end) !== previous.end) {
        const {words, ...other} = previous;
        segments[index] = {...other,start:Number(data.start),end:Number(data.end),text:data.text};
      }
      return editRequest({segments},'Caption saved.');
    }
    case 'review-form': {
      const decision = submitter?.value;
      if (decision === 'approved' && !form.rights.checked) throw new Error('Confirm editorial review and media rights before approval.');
      await api(projectUrl('review'),{clip_id:current().id,decision,editor:data.editor,rights:form.rights.checked});
      await refresh(); notice(decision === 'assigned' ? 'Editor assigned.' : `Clip ${decision}.`); return;
    }
    case 'batch-form': {
      const ids = new FormData(form).getAll('ids');
      if (!ids.length) throw new Error('Choose at least one candidate.');
      return renderRequest(ids);
    }
    case 'purge-form': {
      await api(projectUrl('purge'),{confirm_name:data.confirm_name});
      closeDialog(); state.project = null; state.clipId = null; state.projects = await api('/api/projects'); location.hash = 'projects'; notice('Local project deleted.'); return;
    }
  }
}
document.addEventListener('submit',async event => {
  event.preventDefault(); if (state.busy) return;
  state.busy = true; const form = event.target, submitter = event.submitter;
  if (submitter) submitter.disabled = true;
  try { await onSubmit(form,submitter); } catch(error) { notifyError(error); }
  finally { state.busy = false; if (submitter) submitter.disabled = false; }
});
document.addEventListener('click', async event => {
  const node = event.target.closest('button'); if (!node || node.disabled) return;
  try {
    if (node.dataset.clip) { state.clipId = node.dataset.clip; draw(); return; }
    if (node.dataset.tab) { state.tab = node.dataset.tab; drawTab(); return; }
    if (node.dataset.cutAppend !== undefined) {
      const field = $('#cuts-form textarea'), range = node.dataset.start + ', ' + node.dataset.end;
      if (!field.value.split('\n').includes(range)) field.value = [field.value.trim(), range].filter(Boolean).join('\n');
      return;
    }
    if (node.dataset.editCue !== undefined) { cueDialog(Number(node.dataset.editCue)); return; }
    if (node.dataset.seek !== undefined) {
      const cue = state.project.segments[Number(node.dataset.seek)];
      const video = $('#video');
      video.src = mediaUrl('source');
      bindVideo(cue.start);
      $('.monitor-head span').textContent = 'Source preview';
      $('.monitor-head .mono').textContent = 'Original footage';
      $('.monitor-foot strong').textContent = state.project.source.name;
      $('.monitor-foot span').textContent = 'Full source';
      $('#elapsed').parentElement.lastChild.textContent = ' / ' + clock(state.project.source.duration);
      video.play().catch(notifyError); return;
    }
    switch (node.dataset.action) {
      case 'close': closeDialog(); break;
      case 'import': importDialog(); break;
      case 'batch': batchDialog(); break;
      case 'cut-dialog': await cutDialog(); break;
      case 'resume': await renderRequest(); break;
      case 'render-one': await renderRequest([current().id]); break;
      case 'previous': case 'next': state.page += node.dataset.action === 'next' ? 1 : -1; $('#transcript-list').innerHTML = transcriptList(); break;
      case 'full': if (document.fullscreenElement) await document.exitFullscreen(); else { const video = $('#video'); video.controls = true; await video.requestFullscreen(); } break;
      case 'purge': openDialog('Delete local project', `<form id="purge-form"><p class="hint">This removes the project, private source copy, transcript and all renders from local storage.</p><br>${formField(`Type <strong>${escapeText(state.project.name)}</strong> to confirm`,`<input required name="confirm_name" autocomplete="off">`)}<div class="form-footer"><button class="button danger">Delete project</button></div></form>`); break;
    }
  } catch(error) { notifyError(error); }
});
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement && $('#video')) $('#video').controls = false; });
document.addEventListener('input', event => {
  if (event.target.id === 'search') { state.query = event.target.value; state.page = 0; $('#transcript-list').innerHTML = transcriptList(); }
});
document.addEventListener('change', event => {
  if (event.target.id === 'filter') { state.filter = event.target.value; $('#candidates').innerHTML = candidateRows(); }
});
window.addEventListener('hashchange',() => route().catch(notifyError));
async function boot() {
  const session = await api('/api/session'); state.csrf = session.csrf; state.model = session.local_model;
  state.projects = await api('/api/projects'); await route();
  setInterval(async () => {
    const p = state.project;
    if (!p || (!p.busy && p.status !== 'processing') || state.view !== 'desk' || state.busy || $('#dialog').open || document.hidden) return;
    // A finishing render must not replace a transcript edit in progress.
    if (document.activeElement?.matches('input:not([type="range"]), textarea, select')) return;
    try {
      const updated = await api(`/api/projects/${p.id}`);
      if (state.project?.id !== p.id || state.busy) return;
      if (JSON.stringify([p.busy,p.status,p.stage,p.progress,p.error]) !== JSON.stringify([updated.busy,updated.status,updated.stage,updated.progress,updated.error])) {
        setClip(updated); draw();
      }
    } catch(error) { notice(error.message,true); }
  }, 1300);
}
boot().catch(error => { $('#main').innerHTML = empty('Workspace unavailable', error.message); $('#main').setAttribute('aria-busy','false'); });
