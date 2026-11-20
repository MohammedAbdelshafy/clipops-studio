'use strict';
const $ = selector => document.querySelector(selector);
const escapeText = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
const options = (entries, selected) => Object.entries(entries).map(([key, label]) => `<option value="${escapeText(key)}" ${String(selected) === key ? 'selected' : ''}>${escapeText(label)}</option>`).join('');
const styles = {podcast:'Premium podcast', business:'Business education', value:'Value-driven', cinematic:'Cinematic story', egyptian:'Egyptian education', fashion:'Fashion campaign', workshop:'Founder workshop', gaming:'Gaming & entertainment', minimal:'Minimal professional'};
const platforms = {shorts:'YouTube Shorts · 9:16', reels:'Instagram Reels · 9:16', tiktok:'TikTok · 9:16', square:'Square · 1:1', landscape:'Landscape · 16:9'};
const reviews = {pending:'Pending review', approved:'Approved', rejected:'Rejected'};
const statuses = {queued:'Queued', processing:'Processing', review:'In review', failed:'Needs attention'};
const names = {projects:'Project library', desk:'Review desk', exports:'Export center'};
const tabNames = {details:'Clip details', captions:'Transcript & captions', creative:'Creative review', settings:'Render settings', review:'Review & delivery'};
const ambientPreference = (() => {
  try { return localStorage.getItem('clipops-ambient-video') !== 'off'; }
  catch { return true; }
})();
const state = {csrf:'', model:false, projects:[], project:null, clipId:null, view:'projects', tab:'details', filter:'all', query:'', page:0, busy:false, version:0, ambient:ambientPreference, creative:null, proposal:null, moments:null, momentQuery:'', visual:null};
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
  else notice(error.message + ' · See Free fallbacks in the top bar.', true);
}
function openDialog(title, html) {
  $('#dialog-title').textContent = title;
  $('#dialog-body').innerHTML = `<p role="alert" class="error-banner"></p>${html}`;
  if (!$('#dialog').open) $('#dialog').showModal();
}
function closeDialog() { $('#dialog').close(); }
async function showFreeFallbacks() {
  const payload = await api('/api/fallbacks');
  if (!Array.isArray(payload.routes)) throw new Error('Fallback directory unavailable.');
  const groups = {intake:'Large video intake', speech:'Transcription', editing:'Editing', assets:'Artwork', distribution:'Publishing'};
  const body = Object.entries(groups).map(([category,label]) => {
    const entries = payload.routes.filter(r => r.workflow === category).map(r => {
      const title = typeof r.url === 'string' && r.url.startsWith('https://')
        ? '<a href="' + escapeText(r.url) + '" target="_blank" rel="noopener noreferrer">' + escapeText(r.title) + '</a>'
        : '<strong>' + escapeText(r.title) + '</strong>';
      const status = r.mode === 'local_optional' ? (r.available_here ? 'Configured here' : 'Needs local setup')
        : r.mode === 'manual_external' ? 'External, manual only' : 'Built into ClipOps';
      return '<div class="fallback-entry"><div>' + title + '<span>' + escapeText(status) + '</span></div><p>' + escapeText(r.description) + '</p></div>';
    }).join('');
    return '<section class="fallback-group"><h3>' + escapeText(label) + '</h3>' + entries + '</section>';
  }).join('');
  openDialog('Free fallback tools', '<p class="hint">Choose an offline or manually opened tool when an optional API is unavailable. Nothing automatically receives your footage.</p><div class="fallback-groups">' + body + '</div><p class="hint">' + escapeText(payload.policy) + '</p>');
}
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
    state.tab = 'details'; state.query = ''; state.page = 0; state.filter = 'all'; state.creative = null; state.proposal = null; state.moments = null; state.momentQuery = ''; state.visual = null;
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
  const hero = `<section class="library-hero" aria-labelledby="studio-hero-title">
    <div class="library-hero-copy"><p class="hero-eyebrow">CLIPOPS STUDIO / PRIVATE CREATIVE WORKSPACE</p>
    <h2 id="studio-hero-title">One recording. A whole story to tell.</h2>
    <p>Bring your footage into the edit room, discover moments worth sharing, and review each frame before delivery.</p>
    <div class="hero-actions">${button('import','Import new footage','primary')}<span>Local-first · Review-led · No automatic publishing</span></div></div>
    <div class="hero-reels" aria-hidden="true"><div class="reel-card reel-left"><span>01</span><i></i></div><div class="reel-card reel-center"><span>02</span><i></i><b>PLAY / REVIEW</b></div><div class="reel-card reel-right"><span>03</span><i></i></div></div>
  </section>`;
  const heading = titleBar('Project library', meta([projects.length ? `${projects.length} local project${projects.length === 1 ? '' : 's'}` : 'Your local production workspace']));
  if (!projects.length) return heading + hero + `<section class="panel empty-studio">${empty('Start a project', 'Import authorized footage and a timestamped transcript, or use a local speech model.', button('import','Import project','primary'))}</section>`;
  return heading + hero + `<section class="panel"><div class="panel-head"><h2>All projects</h2></div><div class="library-table">${projects.map(p => `<div class="list-row"><div><a class="project-link" href="#desk/${p.id}">${escapeText(p.name)}</a><small>${escapeText([p.source.name, platforms[p.platform]].filter(Boolean).join(' · '))}</small></div>${badge(statuses[p.status] || p.status, p.status === 'failed' ? 'bad' : '')}</div>`).join('')}</div></section>`;
}
function downloads(clip) {
  return ['export','srt','vtt'].map(type => `<a class="download" href="${mediaUrl(type, clip)}" download>${type === 'export' ? '↓ MP4' : type.toUpperCase()}</a>`).join('');
}
function exportsPage() {
  const p = state.project;
  const deliverable = p.candidates.filter(c => c.rendered && c.qc?.passed && c.review === 'approved');
  return titleBar('Export center', meta([p.name, `${deliverable.length} approved for delivery`])) + `<section class="panel"><div class="panel-head"><h2>Approved clips</h2>${deliverable.length ? `<a class="button dark" href="/api/projects/${p.id}/approved-delivery.zip" download="approved-clips.zip">↓ Download approved batch ZIP</a>` : ''}</div>${deliverable.length ? `<div class="export-list">${deliverable.map(c => `<div class="list-row"><div><strong dir="auto">${escapeText(c.title)}</strong><small>${clock(c.start)}–${clock(c.end)} · ${escapeText(c.editor || '')}</small></div><div class="actions">${downloads(c)}</div></div>`).join('')}</div>` : empty('No approved exports', 'Review a rendered clip and confirm its rights to unlock delivery.', `<a class="button" href="#desk/${p.id}">Open review desk</a>`)}</section>`;
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
  const rendered = Boolean(c?.rendered && !state.sourceView);
  const length = c && rendered ? c.render?.duration ?? c.end - c.start : p.source.duration;
  const title = c?.title || p.source.name;
  const platform = rendered ? (platforms[p.platform] || p.platform).split(' · ')[0] : 'Original footage';
  return `<section class="monitor" aria-label="Video preview"><div class="monitor-head"><span>${rendered ? 'Rendered preview' : 'Source preview'}</span><span class="mono">${escapeText(platform)}</span></div><div class="cinema-stage"><div class="screen"><video id="video" preload="${rendered ? 'auto' : 'metadata'}" playsinline aria-label="${escapeText(title)}" src="${mediaUrl(rendered ? 'preview' : 'source')}?v=${state.version}"></video></div></div><div class="transport"><button class="icon-button" data-action="play" aria-label="Play preview" id="play-toggle">▶</button><input id="scrub" type="range" min="0" max="${Number(length) || 0}" step="0.001" value="0" aria-label="Preview timeline"><span class="mono"><time id="elapsed">0:00</time> / ${clock(length)}</span><button class="icon-button" data-action="full" aria-label="Full screen preview">⛶</button></div><div class="monitor-actions"><button type="button" class="button ambient-switch" data-action="ambient" aria-label="Toggle cinematic video backdrop" aria-pressed="false">Ambient video: Off</button>
    ${c?.rendered ? button('compare',rendered ? 'View source' : 'View render') : ''}
    ${c && !rendered ? button('mark-in','Set In')+button('mark-out','Set Out') : ''}
    ${!p.proxy_ready ? button('proxy','Build browser preview','',p.busy) : ''}
  </div><div class="monitor-foot"><strong dir="auto">${escapeText(title)}</strong><span>${c ? `${clock(c.start)}–${clock(c.end)}` : 'Full source'}</span></div></section>`;
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
  return `<div class="detail-grid"><form id="details-form"><div class="form-grid">${formField('Clip title', `<input name="title" required maxlength="160" value="${escapeText(c.title)}" dir="auto">`, true)}${formField('Start (source seconds)',`<input name="start" type="number" step="0.001" min="0" required value="${Number(c.start)}">`)}${formField('End (source seconds)',`<input name="end" type="number" step="0.001" min="0.01" required value="${Number(c.end)}">`)}${formField('Description',`<textarea name="description" rows="2" dir="auto">${escapeText(c.description)}</textarea>`,true)}${formField('Call to action',`<input name="cta" value="${escapeText(c.cta)}" dir="auto">`,true)}</div><div class="form-footer"><button class="button dark" ${state.project.busy ? 'disabled' : ''}>Save clip edits</button>${button('cut-dialog','Review pause and filler cuts','',state.project.busy)}${button('punch-dialog','Edit punch-ins','',state.project.busy)}${button('render-one','Render this clip','',state.project.busy)}</div></form><aside><h3>Selection rationale</h3><p class="hint">${c.selection_edited ? 'Original selection score' : 'Editorial score'} · ${escapeText(c.score)} points</p>${c.render_error ? `<p class="error-banner">${escapeText(c.render_error)}</p>` : ''}${c.render?.framing_reason ? `<p class="hint">${escapeText(c.render.framing_reason)}</p>` : ''}<ul class="rationale">${(Array.isArray(c.rationale) ? c.rationale : [c.rationale]).filter(Boolean).map(reason => `<li>${escapeText(reason)}</li>`).join('')}</ul>${(state.project.edits || []).some(e => e.candidate === c.id) ? `<details><summary>Selection edit history</summary><ul class="rationale">${state.project.edits.filter(e => e.candidate === c.id).slice(-6).reverse().map(e => `<li>${escapeText(new Date(e.at).toLocaleString())} · ${escapeText(e.fields.map(x => x.replaceAll('_',' ')).join(', '))}</li>`).join('')}</ul></details>` : ''}</aside></div>`;
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
function creativeReview() {
  const c = current(), p = state.project;
  if (!c) return empty('No clip selected', 'Select a candidate to review its source material.');
  const pack = state.creative?.candidate_id === c.id ? state.creative : null;
  const proposal = state.proposal?.candidate_id === c.id ? state.proposal : null;
  const hook = pack?.hook_source;
  const quotes = (pack?.quote_bank || []).map(q => '<li><strong>'+clock(q.start)+'–'+clock(q.end)+'</strong> · <span dir="auto">'+escapeText(q.verbatim)+'</span>'+(q.speaker ? ' <small>('+escapeText(q.speaker)+')</small>' : '')+'</li>').join('');
  const warnings = (pack?.warnings || []).map(w => '<li>'+escapeText(w)+'</li>').join('');
  const momentMatches = (state.moments?.matches || []).map((m,i) =>
    '<li><strong>'+clock(m.start)+'–'+clock(m.end)+'</strong> · <span dir="auto">'+escapeText(m.verbatim)+'</span>'
    + '<p class="hint">Matched: '+escapeText(m.matched_terms.join(', '))+' · source token match '+escapeText(m.match_score)+'/100 (not viral score)'+'</p>'
    + '<div class="actions">'+button('moment-seek','Play source').replace('data-action="moment-seek"','data-action="moment-seek" data-moment="'+i+'"')
    +button('moment-preview','Preview clip boundaries','dark',p.busy).replace('data-action="moment-preview"','data-action="moment-preview" data-moment="'+i+'"')+'</div></li>').join('');
  const visual = state.visual?.candidate_id === c.id ? state.visual : null;
  const sceneList = (visual?.scene_boundaries || []).map(t => '<li>'+clock(t)+' · <span class="hint">Frame-change suggestion only</span></li>').join('');
  return '<div class="review-block"><h3>Source-grounded creative review</h3>'
    + '<p class="hint">Offline, editable suggestions only. No cloud AI, automatic edits or publishing.</p>'
    + button('creative-refresh', pack ? 'Refresh source analysis' : 'Analyze this clip', 'dark', p.busy)
    + '<form id="moment-form" class="review-block"><label class="field wide">Find moments by subject or exact quote'
    + '<input name="query" maxlength="220" minlength="2" required placeholder="e.g. biggest customer mistake / غلطة العميل" dir="auto" value="'+escapeText(state.momentQuery)+'">'
    + '<small class="hint">Offline word/phrase matching of real transcript only; no visual/sentiment AI or invented dialogue.</small></label>'
    + '<button class="button dark" type="submit" '+(p.busy ? 'disabled' : '')+'>Find source moments</button></form>'
    + (state.moments ? '<section class="panel"><h3>Found source moments</h3>'
      + (momentMatches ? '<ul class="rationale">'+momentMatches+'</ul>' : '<p class="hint">No matching contiguous moments; try a different source word.</p>')
      + '</section>' : '')
    + button('visual-refresh','Analyze visual scene changes','dark',p.busy)
    + (visual ? '<section class="panel"><h3>Visual transitions in selected clip</h3>'
      + (sceneList ? '<ul class="rationale">'+sceneList+'</ul>' : '<p class="hint">No strong frame changes detected at sampled rate.</p>')
      + '<p class="hint">'+escapeText(visual.warning)+'</p></section>' : '')
    + (pack ? '<section class="panel"><h3>Suggested opening hook</h3><p dir="auto">'
      + (hook ? escapeText(hook.verbatim) : 'No complete source quote found; choose a hook manually.')+'</p>'
      + (hook ? '<small class="hint">Source: '+clock(hook.start)+'–'+clock(hook.end)+'. Editorial suggestion only.</small>' : '')
      + '<h3>Verbatim quote bank</h3>'+(quotes ? '<ul class="rationale">'+quotes+'</ul>' : '<p class="hint">No suitable quotes found.</p>')
      + '<h3>Manual editorial checks</h3>'+(warnings ? '<ul class="rationale">'+warnings+'</ul>' : '<p class="hint">Still review story, facts, audio and caption quality.</p>')
      + (pack.possible_profanity.length ? '<p class="hint">Review words: '+escapeText(pack.possible_profanity.join(', '))+'</p>' : '')
      + '</section>' : '')
    + '<form id="creative-form"><label class="field wide">Preview an edit instruction'
    + '<textarea rows="3" name="instruction" maxlength="1000" required placeholder="start 00:05; end 00:38; title: A useful lesson"></textarea>'
    + '<small class="hint">Supported: start, end, title:, cta:, remove X to Y. Separate commands with semicolons. Structured editing, not generative AI.</small></label>'
    + '<div class="form-footer"><button class="button dark" type="submit" '+(p.busy ? 'disabled' : '')+'>Preview safe edit</button></div></form>'
    + (proposal ? '<section class="panel"><h3>Edit preview — not applied</h3><pre class="hint">'+escapeText(JSON.stringify(proposal.proposed_updates,null,2))+'</pre>'
      + '<p class="hint">Edits require rerendering and review before delivery.</p>'
      + button('apply-proposal','Apply reviewed edits','primary',p.busy)+'</section>' : '')
    + '</div>';
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
  area.innerHTML = ({details,captions,creative:creativeReview,settings,review})[state.tab]();
}
/* ClipOps 3D depth: UI-only, no media manipulation and no network. */
const DEPTH_QUERY = '(min-width: 901px) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)';
let depthEnabled = true;
try { depthEnabled = localStorage.getItem('clipops-depth-motion') !== 'off'; }
catch { /* Private mode works without persistent settings. */ }

function depthAllowed() {
  return window.matchMedia(DEPTH_QUERY).matches && !navigator.connection?.saveData;
}
function syncDepth() {
  const active = Boolean(depthEnabled && depthAllowed() && !document.hidden);
  document.documentElement.classList.toggle('depth-on', active);
  const toggle = document.querySelector('[data-action="depth"]');
  if (toggle) {
    toggle.disabled = !depthAllowed();
    toggle.setAttribute('aria-pressed', String(active));
    toggle.setAttribute('aria-label', active ? 'Disable 3D depth motion' : 'Enable 3D depth motion');
    toggle.title = !depthAllowed()
      ? '3D depth is disabled for touch, compact screens, data saving, or reduced-motion preferences.'
      : 'Decorative depth only. Original footage, timing and exports are unchanged.';
  }
}
let depthFrame = null, pendingDepth = null;
document.addEventListener('pointermove', event => {
  if (!document.documentElement.classList.contains('depth-on') || !(event.target instanceof Element)) return;
  const hero = event.target.closest('.library-hero');
  if (!hero) return;
  pendingDepth = {hero, x:event.clientX, y:event.clientY};
  if (depthFrame !== null) return;
  depthFrame = requestAnimationFrame(() => {
    depthFrame = null;
    const point = pendingDepth;
    if (!point || !point.hero.isConnected) return;
    const bounds = point.hero.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const x = Math.max(-1, Math.min(1, 2 * (point.x - bounds.left) / bounds.width - 1));
    const y = Math.max(-1, Math.min(1, 2 * (point.y - bounds.top) / bounds.height - 1));
    point.hero.style.setProperty('--depth-ry', (x * 7).toFixed(2) + 'deg');
    point.hero.style.setProperty('--depth-rx', (-y * 4).toFixed(2) + 'deg');
  });
}, {passive:true});
document.addEventListener('pointerout', event => {
  if (!(event.target instanceof Element)) return;
  const hero = event.target.closest('.library-hero');
  if (hero && (!event.relatedTarget || !hero.contains(event.relatedTarget))) {
    pendingDepth = null;
    if (depthFrame !== null) cancelAnimationFrame(depthFrame);
    depthFrame = null;
    hero.style.removeProperty('--depth-rx');
    hero.style.removeProperty('--depth-ry');
  }
});

function motionAllowed() {
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches &&
    !window.matchMedia('(max-width: 640px)').matches && !navigator.connection?.saveData;
}
function needsWebmReview(video) {
  // Preview only: the approved delivery always stays high-quality H.264/AAC MP4.
  return !video.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"') &&
    Boolean(video.canPlayType('video/webm; codecs="vp8, opus"'));
}
function syncAmbient() {
  const stage = document.querySelector('.cinema-stage');
  if (!stage) return;
  const clip = current();
  const enabled = Boolean(state.ambient && clip?.rendered && !state.sourceView && motionAllowed());
  const background = stage.querySelector('.ambient-preview');
  if (!enabled && background) { background.pause(); background.remove(); }
  if (enabled && !background) {
    const video = document.createElement('video');
    video.className = 'ambient-preview';
    video.src = document.querySelector('#video')?.src || (mediaUrl('preview',clip) + '?v=' + state.version);
    video.muted = true;
    video.loop = true;
    video.autoplay = true;
    video.playsInline = true;
    video.preload = 'none';
    video.setAttribute('aria-hidden','true');
    video.tabIndex = -1;
    video.disablePictureInPicture = true;
    stage.prepend(video);
    video.play().catch(() => {}); // Cosmetic playback must never block editing.
  }
  stage.classList.toggle('ambient-on',enabled);
  const toggle = stage.closest('.monitor').querySelector('[data-action="ambient"]');
  toggle.disabled = !clip?.rendered || !motionAllowed() || Boolean(state.sourceView);
  toggle.setAttribute('aria-pressed',String(enabled));
  toggle.textContent = 'Ambient video: ' + (enabled ? 'On' : 'Off');
  toggle.title = !clip?.rendered ? 'Render a clip to preview its ambient background.' :
    !motionAllowed() ? 'Ambient motion is disabled on compact screens or by reduced-motion/data-saver preferences.' : '';
}
function draw() {
  setNav();
  const main = $('#main');
  main.setAttribute('aria-busy', 'false');
  if (state.view === 'projects') main.innerHTML = library();
  else if (!state.project) main.innerHTML = titleBar(names[state.view], '') + `<section class="panel empty-studio">${empty('Choose a project','Import footage or select a project in the library.',`<a href="#projects" class="button">Project library</a>`)}</section>`;
  else if (state.view === 'exports') main.innerHTML = exportsPage();
  else { main.innerHTML = desk(); bindVideo(); drawTab(); syncAmbient(); }
}
function bindVideo(requestedTime=null, fullSource=false) {
  const video = $('#video');
  if (!video) return;
  const c = current();
  const rendered = c?.rendered && !state.sourceView && !fullSource;
  if (rendered && needsWebmReview(video)) {
    video.src = mediaUrl('webm', c) + '?v=' + state.version;
  }
  const start = 0;
  const end = rendered ? c.render?.duration ?? c.end - c.start : state.project.source.duration;
  const seek = requestedTime ?? (rendered ? 0 : (c?.start || 0));
  const slider = $('#scrub');
  slider.max = end - start;
  const play = $('#play-toggle');
  const toggle = () => {
    play.textContent = video.paused ? '▶' : 'Ⅱ';
    play.setAttribute('aria-label', video.paused ? 'Play preview' : 'Pause preview');
  };
  const seekWhenReady = () => {
    if (requestedTime !== null || seek > 0) video.currentTime = Math.max(0, Math.min(seek, end));
  };
  video.onloadedmetadata = seekWhenReady;
  if (video.readyState > 0) seekWhenReady();
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
  slider.onkeydown = ev => {
    if (rendered || !c || !['i','o'].includes(ev.key.toLowerCase())) return;
    ev.preventDefault();
    markTime(ev.key.toLowerCase() === 'i' ? 'start' : 'end', video.currentTime);
  };
}

function markTime(field, time) {
  if (state.tab !== 'details') {
    state.tab = 'details';
    drawTab();
  }
  const input = $(`#details-form [name="${field}"]`);
  input.value = time.toFixed(3);
  input.focus();
}

function mapPlayhead(clip, seconds, toSource) {
  let elapsed = 0;
  for (const [start,end] of clip.render?.retained_source_ranges || [[clip.start,clip.end]]) {
    if (toSource && seconds <= elapsed + end - start) return start + Math.max(0,seconds-elapsed);
    if (!toSource && seconds <= end) return elapsed + Math.max(0,seconds-start);
    elapsed += end-start;
  }
  return toSource ? clip.end : elapsed;
}
async function importDialog() {
  const local = state.session.local_sources ? await api('/api/local-sources') : [];
  const onDisk = local.length ? formField('Open from the configured source folder',
    `<select id="local-source" name="local"><option value="">Upload a video instead</option>
      ${local.map(name => `<option value="${escapeText(name)}">${escapeText(name)}</option>`).join('')}</select>
      <small class="hint">Direct access leaves the original in place.</small>`,true) : '';
  openDialog('Import project', `<form id="import-form"><div class="form-grid">
    ${formField('Project name','<input name="name" maxlength="140" placeholder="Use source filename">',true)}
    ${onDisk}
    ${formField('Source video','<input name="video" type="file" accept=".mp4,.mov,.mkv,.webm"><small class="hint">MP4, MOV, MKV or WebM. Resumable uploads up to 20 GiB.</small>',true)}
    ${formField('Timestamped transcript',`<input name="transcript" type="file" accept=".json,application/json"><small class="hint">${state.model ? 'Optional. Local speech recognition is available.' : 'New projects need a timed JSON transcript. To resume, select the same video.'}</small>`,true)}
    ${formField('Editing style',`<select name="style">${options(styles,'podcast')}</select>`)}
    ${formField('Export format',`<select name="platform">${options(platforms,'shorts')}</select>`)}
    ${formField('Initial renders','<input type="number" min="0" max="30" name="count" value="5" required><small class="hint">Use zero to rank candidates first.</small>',true)}
    <label class="check wide"><input type="checkbox" name="rights" required> I have permission to process this footage and transcript locally.</label>
    <div id="upload-status" class="wide" aria-live="polite" role="status" hidden>
      <progress class="upload-progress" id="upload-progress" max="100" value="0" aria-label="Committed upload progress"></progress>
      <span id="upload-message" class="hint"></span>
    </div>
  </div><div class="form-footer">
    <button class="button" type="button" data-action="pause-upload" hidden>Pause upload</button>
    <button class="button danger" type="button" data-action="cancel-upload" hidden>Cancel upload</button>
    <button class="button primary">Import & process</button>
  </div></form>`);
}

async function sha256(buffer) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', buffer));
}

const hexDigest = value => Array.from(value, x => x.toString(16).padStart(2,'0')).join('');

async function verifyPrefix(form, file, offset, receipt) {
  if (!Number.isSafeInteger(offset) || offset < 0 || offset > file.size) throw new Error('Invalid saved upload offset.');
  const step = state.session.chunk_bytes;
  let chain = new Uint8Array(32);
  for (let start = 0; start < offset; start += step) {
    reportUpload(form,start,offset,'Checking the previously uploaded portion…');
    const block = await file.slice(start,Math.min(offset,start+step)).arrayBuffer();
    const record = new Uint8Array(72);
    record.set(chain);
    new DataView(record.buffer).setBigUint64(32, BigInt(block.byteLength));
    record.set(await sha256(block),40);
    chain = await sha256(record.buffer);
  }
  if (hexDigest(chain) !== receipt) throw new Error('The selected file differs from the saved upload. Choose the original file to resume.');
}

async function fileKey(file) {
  const chunk = 65536;
  const head = file.slice(0, chunk);
  const tail = file.slice(Math.max(file.size - chunk, 0));
  const sample = new Blob([file.name, '?', String(file.size), '?', String(file.lastModified), head, tail]);
  return 'clipops-upload-' + hexDigest(await sha256(await sample.arrayBuffer()));
}

async function uploadCall(path, method, init={}) {
  const response = await fetch(path, {...init, method,
    headers:{'X-ClipOps-CSRF':state.csrf,'Tus-Resumable':'1.0.0',...init.headers}});
  if (!response.ok) {
    const info = await response.json().catch(() => ({}));
    throw Object.assign(new Error(info.error || `Upload request failed (${response.status}).`),{status:response.status});
  }
  return response;
}

function reportUpload(form, bytes, total, text) {
  const progress = form.querySelector('#upload-status');
  progress.hidden = false;
  progress.querySelector('progress').value = 100 * bytes / total;
  progress.querySelector('#upload-message').textContent = text;
}

async function uploadSpec(form, filename, mime) {
  const transcript = form.transcript.files[0];
  if (transcript?.size > 15 * 1024**2) throw new Error('Choose a transcript under 15 MiB.');
  return {filename, mime, name:form.elements.namedItem('name').value, rights:form.rights.checked,
    transcript:transcript ? JSON.parse(await transcript.text()) : null, style:form.elements.namedItem('style').value,
    platform:form.platform.value, render_count:Number(form.count.value)};
}

async function upload(form) {
  const local = form.elements.namedItem('local')?.value;
  let result;
  if (local) {
    result = await api('/api/import-local', await uploadSpec(form,local,'application/octet-stream'));
  } else {
    const file = form.video.files[0];
    if (!file?.size) throw new Error('Choose a source video.');
    if (file.size > state.session.upload_limit) throw new Error('This video exceeds the workspace upload limit.');
    const storage = await fileKey(file);
    let id = localStorage.getItem(storage), offset = 0;
    const controller = new AbortController(), signal = controller.signal;
    if (id) {
      try {
        const reply = await uploadCall('/api/uploads/'+id,'HEAD',{signal});
        if (Number(reply.headers.get('Upload-Length')) !== file.size) throw new Error('The saved upload is for another file.');
        offset = Number(reply.headers.get('Upload-Offset'));
        if (offset) await verifyPrefix(form,file,offset,reply.headers.get('Upload-Receipt'));
      } catch (error) {
        if (![404,410].includes(error.status)) throw error;
        localStorage.removeItem(storage);
        id = null;
      }
    }
    if (!id) {
      const spec = await uploadSpec(form,file.name,file.type);
      id = crypto.randomUUID().replaceAll('-','');
      localStorage.setItem(storage,id);
      await uploadCall('/api/uploads','POST',{signal,headers:{'Content-Type':'application/json'},
        body:JSON.stringify({id, size:file.size,metadata:spec})});
    }
    const path = '/api/uploads/'+id;
    state.transfer = {controller,path,storage,active:true};
    const pause = form.querySelector('[data-action="pause-upload"]');
    const cancel = form.querySelector('[data-action="cancel-upload"]');
    pause.hidden = cancel.hidden = false;
    const size = state.session.chunk_bytes;
    let failures = 0;
    try {
      while (offset < file.size) {
        const mib = Math.floor(offset/1024**2), total = Math.ceil(file.size/1024**2);
        reportUpload(form,offset,file.size,`${mib} of ${total} MiB confirmed`);
        const block = await file.slice(offset,offset+size).arrayBuffer();
        const sum = btoa(String.fromCharCode(...await sha256(block)));
        try {
          const reply = await uploadCall(path,'PATCH',{signal, headers:{
            'Content-Type':'application/offset+octet-stream','Upload-Offset':String(offset),
            'Upload-Checksum':'sha256 '+sum},body:block});
          const next = Number(reply.headers.get('Upload-Offset'));
          if (next !== offset + block.byteLength) throw new Error('The server returned an unexpected checkpoint.');
          offset = next;
          failures = 0;
        } catch (error) {
          if (signal.aborted) throw error;
          if (error.status && ![409,429,460,500,502,503,504].includes(error.status)) throw error;
          if (++failures > 5) throw new Error('Upload paused after repeated errors. Select the same video to resume.');
          await new Promise(resolve => setTimeout(resolve, Math.min(4000, 250 * 2 ** failures)));
          const saved = await uploadCall(path,'HEAD',{signal});
          offset = Number(saved.headers.get('Upload-Offset'));
        }
      }
      pause.hidden = cancel.hidden = true;
      reportUpload(form,file.size,file.size,'Verifying the source and opening the project…');
      result = await api(path+'/complete',{});
      localStorage.removeItem(storage);
      state.transfer = null;
    } catch (error) {
      state.transfer.active = false;
      pause.hidden = true;
      if (signal.aborted) {
        reportUpload(form,offset,file.size,'Paused. Select the same video to resume.');
        return;
      }
      throw error;
    }
  }
  closeDialog(); state.projects = await api('/api/projects'); location.hash = `desk/${result.id}`;
  notice(result.message || 'Footage imported. Processing locally.');
}

async function cancelUpload() {
  const transfer = state.transfer;
  if (!transfer) return;
  transfer.controller.abort();
  for (let attempt = 0; attempt < 5; attempt++) {
    try {
      await uploadCall(transfer.path,'DELETE');
      if (state.transfer === transfer) state.transfer = null;
      localStorage.removeItem(transfer.storage);
      closeDialog();
      notice('Upload cancelled.');
      return;
    } catch (error) {
      if (error.status !== 409 || attempt === 4) throw error;
      await new Promise(resolve => setTimeout(resolve, 300 * (attempt + 1)));
    }
  }
}
function batchDialog() {
  const candidates = state.project.candidates;
  openDialog('Render batch', `<form id="batch-form"><p class="hint">Choose the clips to render with the current project settings.</p><div class="batch-list">${candidates.map(c => `<label class="check"><input type="checkbox" name="ids" value="${c.id}" ${c.id === state.clipId ? 'checked' : ''}><span dir="auto">${escapeText(c.title)}</span></label>`).join('')}</div><div class="form-footer"><button class="button primary">Render selected clips</button></div></form>`);
}
function cueDialog(index) {
  const s = state.project.segments[index];
  openDialog('Edit caption',`<form id="cue-form" data-index="${index}"><div class="form-grid">${formField('Start (source seconds)',`<input type="number" step="0.001" name="start" required min="0" value="${Number(s.start)}">`)}${formField('End (source seconds)',`<input type="number" step="0.001" name="end" required min="0.001" value="${Number(s.end)}">`)}${formField('Speaker',`<input name="speaker" maxlength="80" dir="auto" value="${escapeText(s.speaker)}">`,true)}${formField('Caption text',`<textarea rows="3" name="text" dir="auto" required>${escapeText(s.text)}</textarea>`,true)}</div><div class="form-footer"><button class="button primary">Save caption</button></div></form>`);
}
function punchDialog() {
  const c = current();
  const values = (c.punch_ins || []).map(z => [z.start,z.end,z.scale].join(', ')).join('\n');
  openDialog('Edit punch-ins', `<form id="punch-form">${formField('Timed punch-ins',`<textarea name="punches" rows="5" placeholder="12.400, 15.000, 1.08">${escapeText(values)}</textarea><small class="hint">One start, end, zoom triplet per line in source seconds. Choose 1.02–1.18×, within one retained interval.</small>`)}<div class="form-footer"><button class="button primary">Save punch-ins</button></div></form>`);
}
function intervals(text, count) {
  return text.trim() ? text.trim().split(/\n+/).map(line => {
    const parts = line.split(',').map(part => part.trim());
    if (parts.length !== count || parts.some(part => !part || !Number.isFinite(Number(part)))) {
      throw new Error(`Use ${count} numbers separated by commas on each line.`);
    }
    return parts.map(Number);
  }) : [];
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
    case 'moment-form': {
      state.momentQuery = String(data.query || '');
      state.moments = await api(projectUrl('search-moments'), {query:state.momentQuery});
      drawTab(); notice('Matched the local transcript. Review source before changing cuts.'); return;
    }
    case 'creative-form': {
      state.proposal = await api(projectUrl('propose'),{candidate_id:current().id,instruction:data.instruction});
      drawTab(); notice('Edit preview ready. Nothing has been applied.'); return;
    }
    case 'settings-form': {
      const brand = {};
      for (const key of ['font','accent','text','background']) if (data[key]) brand[key] = data[key];
      const speaker_positions = data.positions ? JSON.parse(data.positions) : {};
      return editRequest({style:data.style,platform:data.platform,resolution:Number(data.resolution),framing:data.framing,brand,
        speaker_positions, cleanup:form.cleanup.checked, push_in:form.push_in.checked},'Render settings saved.');
    }
    case 'cuts-form':
      return editRequest({candidate_id:current().id,remove_ranges:intervals(data.cuts,2)},'Reviewed cuts saved.');
    case 'punch-form': {
      const punches = intervals(data.punches,3).map(([start,end,scale]) => ({start,end,scale}));
      return editRequest({candidate_id:current().id,punch_ins:punches},'Punch-ins saved.');
    }
    case 'cue-form': {
      const index = Number(form.dataset.index), segments = state.project.segments.slice();
      const previous = segments[index];
      if (data.text !== previous.text || Number(data.start) !== previous.start || Number(data.end) !== previous.end) {
        const {words, ...other} = previous;
        segments[index] = {...other,start:Number(data.start),end:Number(data.end),text:data.text};
      }
      if (data.speaker?.trim() !== (previous.speaker || '')) {
        const {speaker,...cue} = segments[index];
        segments[index] = data.speaker.trim() ? {...cue,speaker:data.speaker.trim()} : cue;
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
    if (node.dataset.clip) { state.clipId = node.dataset.clip; state.sourceView = false; state.creative = null; state.proposal = null; state.visual = null; state.moments = null; draw(); return; }
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
      state.sourceView = true;
      syncAmbient();
      bindVideo(cue.start,true);
      $('.monitor-head span').textContent = 'Source preview';
      $('.monitor-head .mono').textContent = 'Original footage';
      $('.monitor-foot strong').textContent = state.project.source.name;
      $('.monitor-foot span').textContent = 'Full source';
      $('#elapsed').parentElement.lastChild.textContent = ' / ' + clock(state.project.source.duration);
      video.play().catch(notifyError); return;
    }
    switch (node.dataset.action) {
      case 'depth':
        if (!depthAllowed()) break;
        depthEnabled = !depthEnabled;
        try { localStorage.setItem('clipops-depth-motion', depthEnabled ? 'on' : 'off'); }
        catch { /* Preference stays in memory only. */ }
        syncDepth();
        break;
      case 'fallbacks': await showFreeFallbacks(); break;
      case 'ambient':
        state.ambient = !state.ambient;
        try { localStorage.setItem('clipops-ambient-video',state.ambient ? 'on' : 'off'); }
        catch { /* Studio works without browser storage. */ }
        syncAmbient();
        break;
      case 'close':
        if (state.transfer?.active) state.transfer.controller.abort();
        closeDialog(); break;
      case 'import': await importDialog(); break;
      case 'pause-upload': state.transfer?.controller.abort(); break;
      case 'cancel-upload': await cancelUpload(); break;
      case 'batch': batchDialog(); break;
      case 'cut-dialog': await cutDialog(); break;
      case 'punch-dialog': punchDialog(); break;
      case 'moment-seek': {
        const m = state.moments?.matches?.[Number(node.dataset.moment)];
        if (!m) throw new Error('Source moment is no longer available. Search again.');
        state.sourceView = true;
        draw(); bindVideo(m.start); syncAmbient();
        $('#video').play().catch(notifyError); break;
      }
      case 'moment-preview': {
        const m = state.moments?.matches?.[Number(node.dataset.moment)], c = current();
        if (!m || !c || state.project.busy) throw new Error('Select a moment and a candidate to review.');
        state.proposal = await api(projectUrl('propose'),{candidate_id:c.id,
          instruction:'start '+m.start.toFixed(3)+'; end '+m.end.toFixed(3)});
        drawTab(); notice('Candidate boundary preview ready. Nothing applied.'); break;
      }
      case 'visual-refresh': {
        const c = current(); if (!c || state.project.busy) break;
        state.visual = await api(projectUrl(c.id + '/visual'));
        drawTab(); notice('Local visual analysis complete. No cuts were made.'); break;
      }
      case 'creative-refresh': {
        const c = current(); if (!c || state.project.busy) break;
        state.creative = await api(projectUrl(c.id + '/creative'));
        drawTab(); break;
      }
      case 'apply-proposal': {
        const p = state.proposal, c = current();
        if (!p || !c || p.candidate_id !== c.id || state.project.busy) throw new Error('Preview the current candidate before applying edits.');
        await editRequest({candidate_id:c.id, ...p.proposed_updates},'Reviewed edits saved. Rerender before approval.');
        state.proposal = null; state.creative = null; drawTab(); break;
      }
      case 'compare': {
        const seconds = mapPlayhead(current(),$('#video').currentTime,!state.sourceView);
        state.sourceView = !state.sourceView;
        draw();
        bindVideo(seconds);
        break;
      }
      case 'mark-in': case 'mark-out':
        markTime(node.dataset.action === 'mark-in' ? 'start' : 'end', $('#video').currentTime);
        break;
      case 'proxy':
        await api(projectUrl('proxy'),{});
        await refresh();
        notice('Browser preview added to the local queue.');
        break;
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
window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',syncAmbient);
window.matchMedia(DEPTH_QUERY).addEventListener('change',syncDepth);
document.addEventListener('visibilitychange',syncDepth);
syncDepth();
window.matchMedia('(max-width: 640px)').addEventListener('change',syncAmbient);
document.addEventListener('visibilitychange', () => {
  const background = document.querySelector('.ambient-preview');
  if (!background) return;
  if (document.hidden) background.pause();
  else if (motionAllowed()) background.play().catch(() => {});
});
async function boot() {
  const session = await api('/api/session'); state.csrf = session.csrf; state.model = session.local_model; state.session = session;
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
