/* Orion's local control room. Every action goes through the existing Python server. */
'use strict';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const views = {
  dashboard: ['◈','Dashboard','COMPANY OVERVIEW','Your work, evidence and decisions in one place.'],
  chat: ['✧','CEO Chat','DIRECT THE COMPANY','Discuss a goal and review proposals before work begins.'],
  projects: ['▦','Projects','PORTFOLIO','Open a project to inspect its tasks and recorded progress.'],
  tasks: ['☷','Task Management','WORKSPACE','Task state, prerequisites and execution evidence.'],
  workers: ['◇','Worker Department','CAPABILITIES','Registered software workers available to Orion.'],
  approvals: ['✓','Approval Centre','CEO DECISIONS','Inspect the exact operation before granting authority.'],
  research: ['⌕','Research Department','EVIDENCE & ANALYSIS','Captured sources, provenance and generated reports.'],
  executions: ['↗','Execution History','AUDIT TRAIL','Actual attempts, outcomes and independent verification.'],
  settings: ['⚙','System Settings','LOCAL CONFIGURATION','Safe provider settings and inference readiness.']
};
let currentView = 'dashboard', projectFilter = '', conversation = null, revision = 0, busy = false;
let health = null;
const fileLibraryState = new Map();
const date = value => value ? new Date(value).toLocaleString() : '—';
const badge = value => `<span class="badge ${escape(value)}">${escape(String(value || 'unknown').replaceAll('_',' '))}</span>`;
const json = value => `<pre class="json">${escape(JSON.stringify(value,null,2))}</pre>`;
const panel = (title, body, note='') => `<section class="panel"><div class="panel-head"><h2>${escape(title)}</h2><small>${escape(note)}</small></div>${body}</section>`;
const empty = (title, text) => `<div class="empty"><strong>${escape(title)}</strong>${escape(text)}</div>`;
const action = (name, id, label, primary=false) => `<button class="button ${primary?'primary':''}" data-action="${name}" data-id="${escape(id)}">${escape(label)}</button>`;
const link = (name, id, label) => `<button class="link-button" data-action="${name}" data-id="${escape(id)}">${escape(label)}</button>`;
const table = (headers, rows) => `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${escape(h)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
const kv = (name, value) => `<p class="kv"><span>${escape(name)}</span>${escape(value ?? '—')}</p>`;

async function api(path, body) {
  const options = body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json','X-Orion-Token':token,'X-Orion-Request':crypto.randomUUID()},body:JSON.stringify(body)};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
function notice(message, error=false) {
  $('notice').className = message ? 'notice'+(error?' error':'') : '';
  $('notice').textContent = message || '';
  document.querySelector('.dialog-error')?.remove();
  if(error && $('dialog').open) {
    const alert=document.createElement('p');alert.className='notice error dialog-error';alert.setAttribute('role','alert');alert.textContent=message;
    $('dialog-body').prepend(alert);
  }
}
function openDialog(title, body) {
  $('dialog-title').textContent = title;
  $('dialog-body').innerHTML = body;
  if (!$('dialog').open) $('dialog').showModal();
}
function pendingNotice(claim) {
  return claim ? '<div class="notice">An inference claim is '+(claim.uncertain?'uncertain':'active')+'. Inspect the prior execution and follow the documented recovery procedure before requesting more inference.</div>' : '';
}

async function dashboard() {
  const d = await api('/api/overview'); health=d;
  const stats = [
    ['Projects',d.counts.projects,'projects','Managed portfolios'],
    ['Total tasks',d.counts.tasks,'tasks','Persistent work records'],
    ['Pending approvals',d.counts.pending_approvals,'approvals','CEO review required'],
    ['Executions',d.counts.executions,'executions',`${d.execution_statuses.succeeded||0} succeeded · ${d.execution_statuses.failed||0} failed`]
  ];
  const recent=d.recent_executions.length ? table(['Task / worker','Outcome','Started'],d.recent_executions.map(x=>`<tr><td>${link('execution',x.id,x.task_title)}<small>${escape(x.worker_id)}</small></td><td>${badge(x.status)}</td><td>${escape(date(x.started_at))}</td></tr>`)) : empty('A clear workspace','Recorded worker attempts will appear here.');
  const activity=d.activity.length ? `<ul class="activity">${d.activity.map(x=>`<li><span class="activity-symbol">↗</span><div>${escape(x.type.replaceAll('_',' '))}<small>${escape(x.task_title)} · ${escape(date(x.timestamp))}</small>${x.execution_id?link('execution',x.execution_id,'Inspect execution'):''}</div></li>`).join('')}</ul>` : empty('No activity recorded','Events will appear as work is configured, approved and executed.');
  return `${pendingNotice(d.inference_claim)}<div class="cards">${stats.map(s=>`<section class="card"><div class="stat-label">${escape(s[0])}<span class="stat-icon">↗</span></div><div class="stat-number">${s[1]}</div><div class="stat-foot">${escape(s[3])}</div><div style="margin-top:12px">${link('navigate',s[2],'View '+s[0].toLowerCase())}</div></section>`).join('')}</div>
    <div class="dashboard-grid"><div>${panel('Recent executions',recent,'Latest 8 attempts')}${panel('From direction to evidence',`<div class="panel-body"><p class="muted">Start with a goal. Review the proposal. Inspect the outcome.</p>${action('navigate','chat','Open CEO Chat',true)} <span class="muted">or</span> ${link('navigate','projects','explore your projects')}</div>`)}</div><div>${panel('System overview',`<div class="panel-body"><div class="health-row"><span>Control plane</span><strong>Local server responding</strong></div><div class="health-row"><span>Provider</span><strong>${escape(d.configuration.provider)} · configured</strong></div><div class="health-row"><span>Model</span><strong>${escape(d.configuration.model)}</strong></div><div class="health-row"><span>Reachability / loaded</span><strong>Not checked</strong></div><div class="health-row"><span>Active executions</span><strong>${d.execution_statuses.running||0}</strong></div><p class="hint">Configuration does not establish model availability.</p>${link('navigate','settings','Inspect provider readiness →')}</div>`)}${panel('Recent activity',activity,'Recorded events')}</div></div>`;
}

function projectProgress(project) {
  if (!project.task_count) return '<p class="hint">No tasks yet · add your first task to begin.</p>';
  return `<div class="progress-track"><progress value="${project.completed_count}" max="${project.task_count}" aria-label="Completed tasks"></progress></div><div class="stat-foot">${project.completed_count} of ${project.task_count} tasks completed · ${Math.round(100*project.completed_count/project.task_count)}%</div>`;
}

async function projects() {
  const items=await api('/api/projects');
  return `<div class="toolbar"><p>${items.length} projects in this workspace</p>${action('new-project','','New project',true)}</div>`+
    (items.length?`<div class="stack-grid">${items.map(p=>`<article class="panel project-card"><div class="toolbar">${badge(p.status)}</div><h2>${link('project',p.id,p.name)}</h2><p>${escape(p.description||'No description provided.')}</p>${projectProgress(p)}<p class="stat-foot">Created ${escape(date(p.created_at))}</p>${action('project',p.id,'Open project →')}</article>`).join('')}</div>`:panel('Projects',empty('Your first project starts here','Create a project to organize tasks and future evidence.')));
}

async function projectDetail(projectId, tab='overview') {
  const [projects,tasks]=await Promise.all([api('/api/projects'),api('/api/tasks?project='+encodeURIComponent(projectId))]);
  const project=projects.find(p=>p.id===projectId);if(!project)throw Error('Project not found.');
  let body='';
  if(tab==='overview') body=`<div class="panel-body">${badge(project.status)}<p>${escape(project.description||'No description provided.')}</p>${projectProgress(project)}<div class="details-grid">${kv('Tasks',tasks.length)}${kv('Created',date(project.created_at))}</div><div class="toolbar">${action('project-tab',projectId,'Open project files',true)}</div></div>`;
  else if(tab==='tasks') body=tasks.length?table(['Task','Worker','State','Priority'],tasks.map(t=>`<tr><td>${link('task',t.id,t.title)}</td><td>${escape(t.worker||'Not assigned')}</td><td>${badge(t.status)}</td><td>${t.priority}</td></tr>`)):empty('No tasks yet','Add a task to this project.');
  else if(tab==='files') body=await projectFilesContent(projectId);
  else if(tab==='research') body=`<div class="panel-body">${link('navigate','research','Open Research Department')}<p class="hint">Research collections and evidence are inspected in the Research Department.</p></div>`;
  else body=`<div class="panel-body">${link('navigate','executions','Open execution history')}<p class="hint">Recorded workspace events and executions are available in the existing activity views.</p></div>`;
  const tabs=['overview','tasks','files','research','activity'];
  openDialog(project.name,`<div class="project-tabs">${tabs.map(t=>`<button class="button ${t===tab?'primary':''}" data-action="project-tab" data-id="${escape(projectId)}" data-tab="${t}">${t==='activity'?'Activity':t[0].toUpperCase()+t.slice(1)}</button>`).join('')}</div><div class="project-section">${body}</div>`);
  if(tab==='files') wireProjectFiles(projectId);
}

async function projectFilesContent(projectId) {
  const state=fileLibraryState.get(projectId)||{search:'',category:'all',folder_id:'',unassigned:false,view:'grid'};fileLibraryState.set(projectId,state);
  const query=new URLSearchParams({project_id:projectId,search:state.search,category:state.category,unassigned:String(state.unassigned)});if(state.folder_id)query.set('folder_id',state.folder_id);
  const [files,folders]=await Promise.all([api('/api/project-files?'+query),api('/api/project-folders?project_id='+encodeURIComponent(projectId))]);
  const viewState=fileLibraryState.get(projectId)||{search:'',category:'all',folder_id:'',unassigned:false,view:'grid'};
  const folderOptions=`<option value="">Project root</option>${folders.map(f=>`<option value="${escape(f.id)}" ${f.id===viewState.folder_id?'selected':''}>${escape(f.name)} (${f.file_count})</option>`).join('')}`;
  const cards=files.length?`<div id="project-file-list" class="file-grid ${state.view==='list'?'file-list':''}">${files.map(f=>fileCard(f,projectId,state.view)).join('')}</div>`:empty('No matching files','Upload files or adjust the search and filters.');
  return `<div class="file-toolbar"><label>Search files<input id="file-search" data-project="${escape(projectId)}" type="search" maxlength="200" placeholder="Filename" value="${escape(state.search)}"></label><label>Category<select id="file-category" data-project="${escape(projectId)}"><option value="all">All files</option><option value="images" ${state.category==='images'?'selected':''}>Images</option><option value="documents" ${state.category==='documents'?'selected':''}>Documents</option><option value="data" ${state.category==='data'?'selected':''}>Data files</option><option value="development" ${state.category==='development'?'selected':''}>Development files</option><option value="archives" ${state.category==='archives'?'selected':''}>Archives</option></select></label><label>Folder<select id="file-folder" data-project="${escape(projectId)}">${folderOptions}</select></label><label class="check-label"><input id="file-unassigned" data-project="${escape(projectId)}" type="checkbox" ${state.unassigned?'checked':''}> Unassigned</label><div class="file-view-actions"><button class="button small" data-action="file-view" data-id="grid">Grid</button><button class="button small" data-action="file-view" data-id="list">List</button><button class="button small" data-action="new-folder" data-id="${escape(projectId)}">New folder</button>${state.folder_id?action('delete-folder',state.folder_id,'Delete selected folder'):''}</div></div>
    <div id="file-drop" class="file-drop" tabindex="0"><strong>Drop files here</strong><span>or choose multiple files · up to 50 MiB each</span><div class="toolbar">${action('file-select',projectId,'Choose files',true)}${action('new-folder',projectId,'New folder')}</div><input id="project-file-input" type="file" multiple hidden accept="${Object.keys(FILE_TYPES_FOR_UI).join(',')}"></div>
    <div id="file-progress" aria-live="polite"></div><div id="file-library-results">${cards}</div><p class="hint">Files stay in this project’s local library. Uploaded content is treated as untrusted data and is never executed or extracted.</p>`;
}

const FILE_TYPES_FOR_UI={'.png':1,'.jpg':1,'.jpeg':1,'.webp':1,'.gif':1,'.pdf':1,'.doc':1,'.docx':1,'.txt':1,'.md':1,'.rtf':1,'.csv':1,'.xls':1,'.xlsx':1,'.json':1,'.xml':1,'.py':1,'.js':1,'.html':1,'.css':1,'.sql':1,'.yaml':1,'.yml':1,'.toml':1,'.zip':1};
function fileCard(file,projectId,view='grid') {
  const category=file.extension.match(/^\.(png|jpe?g|webp|gif)$/)?'image':file.extension==='.zip'?'archive':(['.csv','.xls','.xlsx','.json','.xml'].includes(file.extension)?'data':(['.py','.js','.html','.css','.sql','.yaml','.yml','.toml'].includes(file.extension)?'development':'document'));
  const preview=category==='image'&&file.status==='active'?`<img class="file-thumb" loading="lazy" src="/api/project-file-preview?project_id=${encodeURIComponent(projectId)}&id=${encodeURIComponent(file.id)}" alt="Preview of ${escape(file.display_name)}">`:`<div class="file-icon" aria-hidden="true">${escape(file.extension.slice(1).toUpperCase())}</div>`;
  return `<article class="file-card ${view==='list'?'file-row':''}">${preview}<div class="file-card-main"><button class="link-button file-name" data-action="file-detail" data-id="${escape(file.id)}" data-project="${escape(projectId)}">${escape(file.display_name)}</button><small>${escape(file.detected_mime)} · ${formatBytes(file.size)} · ${escape(date(file.uploaded_at))}</small><small>${file.tasks?.length?`Task: ${escape(file.tasks.map(t=>t.title).join(', '))}`:'Unassigned'} · ${escape(file.import_status.replaceAll('_',' '))} · ${escape(file.status)}</small></div><button class="button small" data-action="file-detail" data-id="${escape(file.id)}" data-project="${escape(projectId)}">Details</button></article>`;
}
function formatBytes(value) { if(value<1024)return value+' B';if(value<1024*1024)return (value/1024).toFixed(1)+' KiB';return (value/1024/1024).toFixed(1)+' MiB'; }
function wireProjectFiles(projectId) {
  const input=$('project-file-input'),drop=$('file-drop');
  if(!input||!drop)return;
  input.addEventListener('change',()=>uploadProjectFiles(projectId,[...input.files]));
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
  drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragging');uploadProjectFiles(projectId,[...event.dataTransfer.files]);});
  drop.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();input.click();}});
}
function uploadProjectFiles(projectId,files) {
  if(!files.length)return;
  const state=fileLibraryState.get(projectId)||{search:'',category:'all',folder_id:'',unassigned:false,view:'grid'};
  const queue=async()=>{
    for(const file of files) {
      if(file.size>50*1024*1024){notice(`${file.name}: exceeds the 50 MiB per-file limit.`,true);continue;}
      $('file-progress').innerHTML=`<div class="upload-status"><span>${escape(file.name)}</span><progress id="upload-progress" max="100" value="0"></progress><span id="upload-percent">0%</span></div>`;
      try {
        const result=await new Promise((resolve,reject)=>{
          const xhr=new XMLHttpRequest();
          xhr.open('POST','/api/project-files?project_id='+encodeURIComponent(projectId));
          xhr.setRequestHeader('Content-Type','application/octet-stream');xhr.setRequestHeader('X-Orion-Token',token);
          xhr.setRequestHeader('X-Orion-Request',crypto.randomUUID());xhr.setRequestHeader('X-Orion-Filename',encodeURIComponent(file.name));
          if(state.folder_id)xhr.setRequestHeader('X-Orion-Folder',encodeURIComponent(state.folder_id));
          xhr.upload.onprogress=e=>{if(e.lengthComputable){const percent=Math.floor(100*e.loaded/e.total);if($('upload-progress'))$('upload-progress').value=percent;if($('upload-percent'))$('upload-percent').textContent=percent+'%';}};
          xhr.onerror=()=>reject(Error('Upload connection failed.'));
          xhr.onload=()=>{let body;try{body=JSON.parse(xhr.responseText);}catch{reject(Error('Server returned an invalid upload response.'));return;}if(xhr.status<200||xhr.status>=300)reject(Error(body.error||'Upload failed.'));else resolve(body);};
          xhr.send(file);
        });
        notice(result.duplicate?`${file.name}: duplicate content already exists as ${result.file.display_name}; no second copy was stored.`:`Uploaded ${file.name}.`);
      } catch(error) { notice(`${file.name}: ${error.message}`,true); }
    }
    await projectDetail(projectId,'files');
  };
  queue();
}
async function fileDetail(projectId,fileId) {
  const [f,tasks,folders]=await Promise.all([api('/api/project-file?project_id='+encodeURIComponent(projectId)+'&id='+encodeURIComponent(fileId)),api('/api/tasks?project='+encodeURIComponent(projectId)),api('/api/project-folders?project_id='+encodeURIComponent(projectId))]);
  let preview='';
  if(f.status==='active'&&/^image\//.test(f.detected_mime)) preview=`<img class="preview-image" src="/api/project-file-preview?project_id=${encodeURIComponent(projectId)}&id=${encodeURIComponent(fileId)}" alt="${escape(f.display_name)}">`;
  else if(f.status==='active'&&['.txt','.md','.rtf','.csv','.json','.xml','.py','.js','.html','.css','.sql','.yaml','.yml','.toml'].includes(f.extension)) {
    const response=await fetch('/api/project-file-preview?project_id='+encodeURIComponent(projectId)+'&id='+encodeURIComponent(fileId));
    if(response.ok){const truncated=response.headers.get('X-Orion-Preview-Truncated')==='true';preview=`<h3>Text preview</h3>${truncated?'<p class="notice">Preview shows the first 512 KiB. Download the file for the complete content.</p>':''}<pre class="json file-preview-text">${escape(await response.text())}</pre>`;}
  }
  const folderOptions=`<option value="">Project root</option>${folders.map(x=>`<option value="${escape(x.id)}" ${x.id===f.folder_id?'selected':''}>${escape(x.name)}</option>`).join('')}`;
  const taskOptions=tasks.map(t=>`<option value="${escape(t.id)}" ${f.tasks?.some(x=>x.id===t.id)?'disabled':''}>${escape(t.title)} · ${escape(t.status)}</option>`).join('');
  const associations=f.tasks?.length?f.tasks.map(t=>`<li>${escape(t.title)}</li>`).join(''):'<li>Unassigned</li>';
  const controls=f.status==='active'?`<form id="file-edit-form" data-project="${escape(projectId)}" data-file="${escape(fileId)}"><div class="form-grid"><label>Display name<input name="display_name" maxlength="255" value="${escape(f.display_name)}" required></label><label>Folder<select name="folder_id">${folderOptions}</select></label></div><label>Description<textarea name="description" maxlength="4000">${escape(f.description)}</textarea></label><button class="button" type="submit">Save file details</button></form>
    <form id="file-attach-form" data-project="${escape(projectId)}" data-file="${escape(fileId)}"><label>Attach to task<select name="task_id" required><option value="">Choose a project task</option>${taskOptions}</select></label><button class="button" type="submit">Attach file</button></form>
    ${f.extension==='.csv'?`<form id="csv-connect-form" data-project="${escape(projectId)}" data-file="${escape(fileId)}"><label>Select task for CSV analysis<select name="task_id" required><option value="">Choose pending project task</option>${tasks.filter(t=>t.status==='pending').map(t=>`<option value="${escape(t.id)}">${escape(t.title)}</option>`).join('')}</select></label><button class="button" type="submit">Connect as CSV worker input</button><p class="hint">Uses the existing 10 MiB CSV input limit and deduplicates by verified SHA-256.</p></form>`:''}
    <div class="toolbar"><a class="button" href="/api/project-file-download?project_id=${encodeURIComponent(projectId)}&id=${encodeURIComponent(fileId)}">Download</a><button class="button danger" data-action="file-delete" data-id="${escape(fileId)}" data-project="${escape(projectId)}">Delete file</button></div>`:`<div class="notice error">This file is quarantined and cannot be previewed, downloaded or attached. Retry deletion to finish local cleanup.</div><button class="button danger" data-action="file-delete" data-id="${escape(fileId)}" data-project="${escape(projectId)}">Retry deletion</button>`;
  openDialog(f.display_name,`${preview}<div class="details-grid">${kv('File type',f.extension+' · '+f.detected_mime)}${kv('Size',formatBytes(f.size))}${kv('Status',f.status)}${kv('Uploaded',date(f.uploaded_at))}${kv('Uploaded by',f.uploaded_by)}${kv('SHA-256',f.sha256)}${kv('Storage path',f.storage_relative_path)}${kv('CSV import',f.import_status)}</div><h3>Associated tasks</h3><ul>${associations}</ul>${controls}`);
}
async function tasks() {
  const [items,projects]=await Promise.all([api('/api/tasks'+(projectFilter?'?project='+encodeURIComponent(projectFilter):'')),api('/api/projects')]);
  const selected=projects.find(p=>p.id===projectFilter);
  const overview=selected?panel(selected.name,`<div class="panel-body">${badge(selected.status)}<p>${escape(selected.description||'No description provided.')}</p>${projectProgress(selected)}</div>`):'';
  const noTasks=selected
    ? empty('This project is ready for its first task','The project description is saved. Add tasks, configure a worker, and review its execution approval to begin work.')+`<div class="panel-body">${action('new-task','','Add first task',true)}<p class="hint">Open a task to assign a registered worker, save its supported configuration, preview the operation and request approval. CEO Chat is available for discussion and plan proposals once its provider is ready.</p></div>`
    : empty('No tasks in this view','Create a task or choose another project.');
  return overview+`<div class="toolbar"><select id="task-project" aria-label="Filter tasks by project"><option value="">All projects</option>${projects.map(p=>`<option value="${escape(p.id)}" ${p.id===projectFilter?'selected':''}>${escape(p.name)}</option>`).join('')}</select><p>${items.length} tasks · readiness is calculated in task details</p>${projects.length?action('new-task','','New task',true):''}</div>`+
    panel('Task workspace',items.length?table(['Task','Worker binding','State','Priority'],items.map(t=>`<tr><td>${link('task',t.id,t.title)}<small>${escape(t.description)}</small></td><td>${escape(t.worker||'Not assigned')}</td><td>${badge(t.status)}</td><td>${t.priority}</td></tr>`)):noTasks);
}
async function workers() {
  const items=await api('/api/workers');
  return `<div class="toolbar"><p>${items.length} registered workers · registration is not a running process</p></div><div class="stack-grid">${items.map(w=>`<article class="panel project-card">${badge('registered')}<h2 style="margin-top:15px">${escape(w.name)}</h2><p>${escape(w.responsibility)}</p>${kv('Type / version',w.identifier+' · v'+w.version)}${kv('Independent verifier',w.required_verifier||'Snapshot validation')}<ul class="worker-capabilities">${w.capabilities.map(c=>`<li>${escape(c)}</li>`).join('')}</ul><details><summary>Input, output and completion conditions</summary>${json(w)}</details></article>`).join('')}</div><p class="hint">Developer, evaluator and manager departments beyond this registry are planned capabilities.</p>`;
}
async function approvals() {
  const items=await api('/api/approvals');
  return panel('Approval requests',items.length?table(['Task / worker','Status','Created',''],items.map(a=>`<tr><td>${escape(a.task_title)}<small>${escape(a.worker_id)}</small></td><td>${badge(a.execution_id?'consumed':a.status)}</td><td>${escape(date(a.created_at))}</td><td>${link('approval',a.id,'Review proposal →')}</td></tr>`)):empty('No approval requests','Requests appear when an operation is proposed through Orion. Assign and configure a worker in task details to preview an operation and request approval.'),'Latest 200 requests');
}
async function research() {
  const data=await api('/api/research');
  const collection=data.collections.length?table(['Research question','Providers','Task state',''],data.collections.map(r=>`<tr><td>${escape(r.configuration.question)}<small>${escape(r.title)}</small></td><td>${escape(r.configuration.providers.join(', '))}</td><td>${badge(r.status)}</td><td>${link('task',r.id,'Inspect task →')}</td></tr>`)):empty('No research configured','Verified research collection tasks will appear here.');
  const synthesis=data.syntheses.length?table(['Synthesis task','Research execution','Task state',''],data.syntheses.map(s=>`<tr><td>${escape(s.title)}</td><td>${link('evidence',s.source_execution,s.source_execution)}</td><td>${badge(s.status)}</td><td>${link('task',s.id,'Inspect analysis history →')}</td></tr>`)):empty('No synthesis configured','AI analysis is a separately approved stage after evidence collection.');
  return `<div class="notice">Collection verification checks structure and provenance. AI analysis requires factual review. Human-reviewed conclusions are not tracked as a separate state yet.</div>${panel('Collected evidence',collection)}${panel('AI synthesis',synthesis)}`;
}
async function executions() {
  const items=await api('/api/executions');
  return panel('Execution history',items.length?table(['Execution / task','Worker','Outcome','Attempt','Time'],items.map(x=>`<tr><td>${link('execution',x.id,x.id)}<small>${escape(x.task_title)}</small></td><td>${escape(x.worker_id)}</td><td>${badge(x.status)}</td><td>${x.attempt}</td><td>${escape(date(x.started_at))}<small>Finished ${escape(date(x.finished_at))}</small></td></tr>`)):empty('No worker attempts','Real execution outcomes and failures will be retained here.'),'Latest 200 attempts');
}
function healthText(s) {
  return s?.service_available===true?'Reachable':s?.service_available===false?'Unavailable':'Not remotely checked';
}
async function settings() {
  const d=await api('/api/overview');health=d;
  return pendingNotice(d.inference_claim)+panel('Provider configuration',`<div class="panel-body"><div class="details-grid">${Object.entries(d.configuration).map(([k,v])=>kv(k.replaceAll('_',' '),v)).join('')}</div><div id="provider-health" class="notice">Configured · remote reachability and loaded state have not been checked.</div>${action('provider-check','','Check provider status')}<p class="hint">This read-only check never loads a model. Hosted configuration does not confirm account entitlement. Configuration editing and inference recovery use the validated CLI procedures.</p></div>`);
}

async function chat() {
  const [list,d]=await Promise.all([api('/api/conversations'),api('/api/overview')]);
  if (!conversation && list.length) conversation=list[0].id;
  let data=conversation?await api('/api/conversation?id='+encodeURIComponent(conversation)):null;
  const pending=d.counts.pending_approvals?`<p class="hint">${d.counts.pending_approvals} pending approval requests. ${link('navigate','approvals','Open Approval Centre')}</p>`:'';
  const messages=data?.messages.length?data.messages.map(m=>`<article class="message ${escape(m.kind)}"><div class="message-label">${m.kind==='model'?'MODEL · '+escape(m.model)+' · '+m.elapsed_seconds+' s':m.kind==='user'?'CEO':'ORION SYSTEM'} · ${escape(date(m.created_at))}</div>${escape(m.content)}</article>`).join(''):empty('What should Orion work on?','Start a conversation, then describe a goal. Use Propose plan to request a structured proposal.');
  return `${pendingNotice(d.inference_claim)}<div class="chat-grid"><aside class="panel chat-sidebar"><h2>Conversations</h2><select id="conversation-select" aria-label="Conversation"><option value="">Select a conversation</option>${list.map(c=>`<option value="${escape(c.id)}" ${c.id===conversation?'selected':''}>${escape(c.title)}</option>`).join('')}</select>${action('new-conversation','','＋ New conversation')}<p class="hint">${escape(d.configuration.provider)}<br>${escape(d.configuration.model)}</p>${pending}</aside><section class="panel chat-main"><div class="panel-head"><h2>${escape(data?.conversation.title||'CEO Chat')}</h2><small>Model output is advisory</small></div><div class="messages" id="messages">${messages}</div><div class="composer"><textarea id="chat-input" maxlength="2000" aria-label="Message" placeholder="Research a topic, discuss an idea, or describe a project…"></textarea><div class="composer-actions"><small id="chat-state" role="status">A proposal requires review before records are created.</small><button class="button" data-action="chat-plan">Propose plan</button><button class="button primary" data-action="chat-send">Send message ↗</button></div></div></section></div>${data?panel('Project context & proposed plans',`<div class="panel-body"><details><summary>Inspect selected project context</summary>${json(data.context)}</details>${data.plans.length?data.plans.map(p=>`<article class="plan-card"><h2>${escape(p.body.title)} ${badge(p.status)}</h2>${json(p.body)}${p.project_id?kv('Created project',p.project_id):''}${p.status==='proposed'?action('plan-review',p.id,'Review plan decision'):''}</article>`).join(''):'<p class="muted">No structured plans in this conversation.</p>'}</div>`):''}`;
}

const renderers={dashboard,projects,tasks,workers,approvals,research,executions,settings,chat};
async function render() {
  const ticket=++revision;
  notice(''); $('content').setAttribute('aria-busy','true');
  const [icon,title,eyebrow,subtitle]=views[currentView];
  $('page-title').textContent=title;$('breadcrumb').textContent=title;
  document.querySelector('.eyebrow').textContent=eyebrow;$('page-subtitle').textContent=subtitle;
  document.querySelectorAll('#navigation a').forEach(a=>a.setAttribute('aria-current',a.hash==='#'+currentView?'page':'false'));
  try {
    const html=await renderers[currentView]();
    if (ticket!==revision) return;
    $('content').innerHTML=html;
    if ($('messages')) $('messages').scrollTop=$('messages').scrollHeight;
  } catch(e) { if(ticket===revision){notice(e.message,true);$('content').innerHTML=empty('This view is unavailable','Refresh after checking the local data.');} }
  finally {if(ticket===revision)$('content').setAttribute('aria-busy','false');}
}
function navigate(name) {
  if (!views[name]) name='dashboard';
  if (location.hash==='#'+name) {currentView=name;render();} else location.hash=name;
}
async function taskDetail(id) {
  const [d,catalog]=await Promise.all([api('/api/task?id='+encodeURIComponent(id)),api('/api/worker-catalog')]);
  const deps=d.dependency.prerequisites;
  const l=d.lifecycle, assigned=l.assignment, worker=catalog.find(w=>w.identifier===assigned?.worker_id);
  const editable=d.task.status==='pending';
  const configured=l.configuration || worker?.defaults || {};
  const timeline={'worker_assigned':'Assigned','research_configured':'Configured','synthesis_configured':'Configured','csv_input_bound':'Configured','approval_requested':'Proposed / awaiting approval','approval_granted':'Approved','approval_rejected':'Rejected','execution_started':'Running','execution_succeeded':'Completed','execution_failed':'Failed','approval_invalidated':'Approval invalidated'};
  const steps=l.events.filter(e=>timeline[e.type]);
  const assignmentForm=editable?`<form id="worker-form" data-id="${escape(id)}"><label>Registered worker<select name="worker_id" required><option value="">Choose a suitable worker</option>${catalog.map(w=>`<option value="${escape(w.identifier)}" ${w.identifier===assigned?.worker_id?'selected':''}>${escape(w.name)} · ${escape(w.identifier)} · v${escape(w.version)}</option>`).join('')}</select></label><p class="hint">Choose by the worker's actual capabilities. Project status produces a record summary; it cannot test a browser or build software.</p><button class="button" type="submit">Assign worker</button></form>`:'';
  const configForm=editable&&assigned?`<form id="worker-config-form" data-id="${escape(id)}" data-assignment="${escape(assigned.event_id)}"><label>Supported configuration (JSON)<textarea name="configuration" class="configuration-input" rows="10" required>${escape(JSON.stringify(configured,null,2))}</textarea></label><p class="hint">${escape(worker.configuration_help)}</p><details><summary>Exact supported defaults and bounds</summary>${json({defaults:worker.defaults,bounds:worker.bounds})}</details>${worker.identifier==='csv-profile'?action('managed-inputs','','Inspect imported CSV input IDs'):''}<button class="button" type="submit">Save configuration</button></form>`:'';
  const attachments=d.files.length?d.files.map(f=>`<article class="plan-card"><button class="link-button" data-action="file-detail" data-id="${escape(f.id)}" data-project="${escape(d.task.project_id)}">${escape(f.display_name)}</button><p>${escape(f.detected_mime)} · ${formatBytes(f.size)} · SHA-256 ${escape(f.sha256)}</p><button class="button small danger" data-action="detach-file" data-id="${escape(f.id)}" data-project="${escape(d.task.project_id)}" data-task="${escape(id)}">Remove task attachment</button></article>`).join(''):'<p class="muted">No project files attached.</p>';
  const fileHistory=d.file_history?.length?`<details><summary>Attachment history</summary><ul>${d.file_history.map(f=>`<li>${escape(f.display_name)} · ${escape(f.status)} · attached ${escape(date(f.attached_at))}${f.removed_at?' · removed '+escape(date(f.removed_at)):''}</li>`).join('')}</ul></details>`:'';
  openDialog(d.task.title,`<h2>Overview</h2><p>${escape(d.task.description||'No description provided.')}</p><div class="details-grid">${kv('Task state',d.task.status)}${kv('Scheduling classification',d.dependency.classification)}${kv('Priority',d.task.priority)}${kv('Approval required',d.dependency.approval_required?'Yes':'No')}</div>
    <details open><summary>Assigned worker</summary>${assigned?`${kv('Binding',assigned.worker_id+' · v'+assigned.version)}${kv('Assigned',date(assigned.assigned_at))}${json(worker)}`:'<p class="muted">No explicit worker assignment.</p>'}${assignmentForm}<details><summary>Compare registered operations and requirements</summary>${json(catalog)}</details></details>
    <details open><summary>Dependencies</summary><p class="hint">${escape(d.dependency.reason)}</p>${deps.length?json(deps):'<p class="muted">No prerequisites recorded.</p>'}</details>
    <details open><summary>Configuration</summary>${configForm||(l.assignment?json(l.configuration):'<p class="muted">Configuration becomes available after worker assignment.</p>')}${l.configuration_error?`<p class="notice">${escape(l.configuration_error)}</p>`:''}</details>
    <details open><summary>Project file attachments</summary>${attachments}${fileHistory}${action('project-files',d.task.project_id,'Browse project files')}</details>
    <p class="notice">${escape(l.execution_gate)}</p><div class="toolbar">${editable&&assigned?action('task-preview',id,'Preview execution proposal',true):''}${l.can_execute?action('task-execute-confirm',id,'Review approved execution'):''}</div>
    <details open><summary>Approval history</summary>${l.approvals.length?l.approvals.map(a=>`<p>${link('approval',a.id,a.id)} ${badge(a.execution_id?'consumed':a.status)} · ${escape(a.worker_id)}</p>`).join(''):'<p class="muted">No requests recorded.</p>'}</details>
    <details open><summary>Execution history, output and verification</summary>${d.history.length?d.history.map(x=>`<article class="plan-card">${link('execution',x.id,'Attempt '+x.attempt+' · '+x.id)} ${badge(x.status)}<p>${escape(x.summary||'Execution in progress')}</p>${x.result?.artifact?action('artifact',x.id,'Inspect output artifact'):''}${x.latest_verification?kv('Independent verification',x.latest_verification.status):''}</article>`).join(''):'<p class="muted">No attempts recorded.</p>'}</details>
    <details><summary>Status timeline from recorded events</summary><ol class="timeline"><li>Created · ${escape(date(d.task.created_at))}</li>${steps.map(e=>`<li>${escape(timeline[e.type])} · ${escape(date(e.timestamp))}${e.execution_id?' · '+escape(e.execution_id):''}</li>`).join('')}</ol></details>`);
}

async function monitorTaskExecution(taskId) {
  let settled=false, telemetryError='';
  const running=api('/api/task-execute',{id:taskId}).finally(()=>{settled=true;});
  openDialog('Execution in progress','<div class="notice">Submitting the approved operation through Orion. Keep this page open to monitor its recorded state.</div><div id="execution-monitor" role="status" aria-live="polite">Waiting for the execution claim…</div>');
  const poll=async()=>{
    while(!settled){
      await new Promise(resolve=>setTimeout(resolve,1000));
      if(settled)break;
      try {
        const d=await api('/api/task?id='+encodeURIComponent(taskId));
        const latest=d.history[d.history.length-1];
        if($('execution-monitor'))$('execution-monitor').textContent=latest?`Attempt ${latest.attempt} · ${latest.id} · ${latest.status}`:`Task ${d.task.status}`;
      } catch(e){telemetryError=e.message;if($('execution-monitor'))$('execution-monitor').textContent='Monitoring interrupted: '+telemetryError+'. The server owns the execution; inspect history before taking further action.';}
    }
  };
  const monitoring=poll();
  try {const run=await running;await executionDetail(run.id);}
  finally {await monitoring;}
}
async function executionDetail(id) {
  const x=await api('/api/execution?id='+encodeURIComponent(id));
  openDialog('Execution detail',`<div class="details-grid">${kv('Execution',x.id)}${kv('Worker / attempt',x.worker_id+' / '+x.attempt)}${kv('Outcome',x.status)}${kv('Started / finished',date(x.started_at)+' / '+date(x.finished_at))}</div>${x.error?`<h2>Recorded failure</h2>${json(x.error)}`:''}<h2>Independent verification history</h2>${x.verifications.length?json(x.verifications):'<p class="muted">No independent verification recorded. Project-status uses the registered snapshot validator.</p>'}${x.result?.artifact?action('artifact',x.id,'Inspect output artifact'):''}${['research-collect','research-synthesize'].includes(x.worker_id)?action('evidence',x.id,'Inspect evidence / analysis'):''}<details><summary>Full recorded result</summary>${json(x)}</details>`);
}
async function evidenceDetail(id) {
  const d=await api('/api/evidence?id='+encodeURIComponent(id));
  let html=`<div class="notice">${escape(d.kind)}. Source references establish provenance, with human review required for factual support.</div><h2>Independent verification</h2>${json(d.verifications)}`;
  if (d.packet) {
    html+=kv('Research question',d.packet.question)+kv('Execution',d.packet.execution_id)+`<h2>Collected sources</h2><ul class="source-list">${d.packet.records.map(r=>{let url='';try{const u=new URL(r.source_url);if(['https:','http:'].includes(u.protocol))url=u.href;}catch{}return `<li><strong>${escape(r.source_id)}</strong><br>${url?`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">${escape(url)}</a>`:''}<details><summary>Captured metadata and evidence</summary>${json(r)}</details></li>`;}).join('')}</ul><details><summary>Providers, limitations and complete packet</summary>${json(d.packet)}</details>`;
  } else html+=`<h2>Approved source projection and selections</h2>${json(d.operation)}<h2>Saved synthesis report</h2>${json(d.report)}`;
  openDialog('Research evidence',html);
}
async function approvalDetail(id) {
  const d=await api('/api/approval?id='+encodeURIComponent(id));
  openDialog('Review approval',`${kv('Task',d.task_title)}${kv('Worker',d.worker_id)}${kv('Request',d.id)}${kv('Eligibility',d.eligibility)}${kv('Fingerprint',d.fingerprint)}${kv('Reason',d.reason)}<h2>Exact proposed operation</h2>${json(d.proposal)}${d.can_decide?`<label>Decision reason<textarea id="approval-reason" maxlength="2000" required></textarea></label><div class="form-actions">${action('approval-reject',d.id,'Review rejection')}${action('approval-approve',d.id,'Review approval',true)}</div>`:'<p class="notice">This request is consumed, stale, unavailable or already decided. It cannot be approved here.</p>'}`);
}

async function createForm(kind) {
  const projects=kind==='project'?[]:await api('/api/projects');
  const fields=kind==='project'?'<label>Project name<input name="name" required maxlength="200"></label>':`<label>Title<input name="title" required maxlength="200"></label><label>Project<select name="project_id" required>${projects.map(p=>`<option value="${escape(p.id)}" ${p.id===projectFilter?'selected':''}>${escape(p.name)}</option>`).join('')}</select></label><label>Priority (0–100)<input name="priority" type="number" min="0" max="100" value="0" required></label>`;
  openDialog('New '+kind,`<form id="create-form" data-kind="${kind}">${fields}<label>Description<textarea name="description" maxlength="4000"></textarea></label><p class="hint">${kind==='task'?'The task will require execution approval. A worker is bound through a supported configuration or execution proposal.':'Create a persistent project in the current local database.'}</p><button class="button primary" type="submit">Create ${kind}</button></form>`);
}

async function handle(name,id,extra={}) {
  if (name==='navigate') return navigate(id);
  if (name==='project') return projectDetail(id);
  if (name==='project-tab') return projectDetail(id,extra.tab||'files');
  if (name==='project-files') return projectDetail(id,'files');
  if (name==='file-select') { $('project-file-input')?.click(); return; }
  if (name==='file-detail') return fileDetail(extra.project||extra.dataset?.project||'',id);
  if (name==='file-view') { const project=$('file-search')?.dataset.project;if(!project)return;const state=fileLibraryState.get(project)||{};state.view=id;fileLibraryState.set(project,state);return projectDetail(project,'files'); }
  if (name==='new-folder') {openDialog('Create project folder',`<form id="folder-form" data-project="${escape(id)}"><label>Folder name<input name="name" maxlength="100" required></label><button class="button primary" type="submit">Create folder</button></form>`);return;}
  if (name==='delete-folder') {const project=$('file-folder')?.dataset.project;if(!window.confirm('Delete this empty project folder?'))return;await api('/api/project-folder-delete',{project_id:project,folder_id:id});const state=fileLibraryState.get(project);if(state)state.folder_id='';return projectDetail(project,'files');}
  if (name==='file-delete') {if(!window.confirm('Delete this project file? Active task links will be detached. Historical CSV inputs used by prior executions are preserved.'))return;await api('/api/project-file-delete',{project_id:extra.project,file_id:id,confirm:id});return projectDetail(extra.project,'files');}
  if (name==='detach-file') {if(!window.confirm('Remove this file from the task? The project file will remain in its library.'))return;await api('/api/task-file-detach',{project_id:extra.project,file_id:id,task_id:extra.task});return taskDetail(extra.task);}
  if (name==='task') return taskDetail(id);
  if (name==='execution') return executionDetail(id);
  if (name==='evidence') return evidenceDetail(id);
  if (name==='approval') return approvalDetail(id);
  if (name==='artifact') {openDialog('Saved output artifact',json(await api('/api/artifact?id='+encodeURIComponent(id))));return;}
  if (name==='managed-inputs') {openDialog('Registered managed CSV inputs',json(await api('/api/inputs')));return;}
  if (name==='task-preview') {
    const d=await api('/api/task-preview?id='+encodeURIComponent(id));
    openDialog('Exact execution proposal',`${kv('Fingerprint',d.fingerprint)}${json(d.proposal)}<h2>Dependency readiness</h2>${json(d.dependency)}${json(d.restrictions)}<form id="task-proposal-form" data-preview="${escape(d.preview_token)}"><label>Why should this execution be authorized?<textarea name="reason" maxlength="2000" required></textarea></label><button class="button primary" type="submit">Submit for CEO approval</button></form>`);return;
  }
  if (name==='task-execute-confirm') {
    const d=await api('/api/task?id='+encodeURIComponent(id));
    if(!d.lifecycle.can_execute)throw Error(d.lifecycle.execution_gate);
    const a=await api('/api/approval?id='+encodeURIComponent(d.lifecycle.approved_id));
    openDialog('Start approved operation',`<div class="notice">Start one attempt of the following approved operation. Orion will recheck dependencies, the approval and the execution/inference claims.</div>${kv('Task',d.task.title)}${kv('Approval',a.id)}${kv('Fingerprint',a.fingerprint)}${json(a.proposal)}${action('task-execute',id,'Execute approved operation',true)}`);return;
  }
  if (name==='task-execute') return monitorTaskExecution(id);
  if (name==='new-project'||name==='new-task') return createForm(name.slice(4));
  if (name==='new-conversation') {
    const projects=await api('/api/projects');
    openDialog('New conversation',`<form id="create-form" data-kind="conversation"><label>Title<input name="title" required maxlength="120" value="New conversation"></label><label>Project context<select name="project_id"><option value="">No project context</option>${projects.map(p=>`<option value="${escape(p.id)}">${escape(p.name)}</option>`).join('')}</select></label><button class="button primary" type="submit">Start conversation</button></form>`);return;
  }
  if (name==='chat-send'||name==='chat-plan') {
    if (!conversation) throw Error('Start or select a conversation first.');
    const text=$('chat-input').value.trim();if(!text)throw Error('Enter a message.');
    $('chat-state').textContent='Orion is processing this request…';
    const d=await api('/api/message',{id:conversation,text,planning:name==='chat-plan'});
    await render();if(d.error)throw Error(d.error);return;
  }
  if (name==='provider-check') {
    const d=await api('/api/status');
    $('provider-health').textContent=`${d.provider} · ${healthText(d)} · model loaded: ${d.loaded===true?'Yes':d.loaded===false?'No':'Not checked'} · ${d.message}`;return;
  }
  if (name==='approval-approve'||name==='approval-reject') {
    const reason=$('approval-reason').value.trim();if(!reason)throw Error('Enter a decision reason.');
    const d=await api('/api/approval-confirmation',{id,reason,decision:name==='approval-approve'?'approved':'rejected'});
    const operation=d.approval;
    openDialog('Confirm exact decision',`<div class="notice">Confirm ${escape(d.decision)} for ${escape(operation.task_title)}. This records your decision; execution is a separate action.</div>${kv('Worker',operation.worker_id)}${kv('Request',operation.id)}${kv('Fingerprint',operation.fingerprint)}${json(operation.proposal)}${kv('Your reason',d.reason)}<button class="button ${d.decision==='approved'?'primary':'danger'}" data-action="approval-confirm" data-id="${escape(d.confirmation)}">Confirm ${escape(d.decision)}</button>`);return;
  }
  if (name==='approval-confirm') {
    await api('/api/approval-decision',{confirmation:id});$('dialog').close();await render();notice('Decision recorded. No task was executed.');return;
  }
  if (name==='plan-review') {
    const d=await api('/api/conversation?id='+encodeURIComponent(conversation));
    const p=d.plans.find(p=>p.id===id);if(!p)throw Error('Plan not found.');
    openDialog('Review plan proposal',`${json(p.body)}<div class="notice">Approving creates a project and its tasks. Each task requires separate execution approval.</div><form id="plan-form" data-id="${escape(p.id)}" data-fingerprint="${escape(p.fingerprint)}"><label>Decision<select name="decision"><option value="rejected">Reject proposal</option><option value="approved">Approve and create project/tasks</option></select></label><label>Reason<input name="reason" required maxlength="2000"></label><button class="button primary">Confirm plan decision</button></form>`);return;
  }
}

async function guarded(work) {
  if (busy) return;
  busy=true;notice('');
  const buttons=[...document.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);
  try {await work();} catch(e){notice(e.message,true);if($('chat-state'))$('chat-state').textContent='Request failed. Your input is retained.';}
  finally {busy=false;document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');
  if(target)guarded(()=>handle(target.dataset.action,target.dataset.id,target.dataset));
});
document.addEventListener('submit',event=>{
  if(!['create-form','plan-form','worker-form','worker-config-form','task-proposal-form','file-edit-form','file-attach-form','csv-connect-form','folder-form'].includes(event.target.id))return;
  event.preventDefault();
  const form=event.target;const data=Object.fromEntries(new FormData(form));
  guarded(async()=>{
    if(form.id==='worker-form') {
      await api('/api/task-assignment',{id:form.dataset.id,worker_id:data.worker_id});
      await taskDetail(form.dataset.id);return;
    }
    if(form.id==='worker-config-form') {
      let configuration;try{configuration=JSON.parse(data.configuration);}catch{throw Error('Enter a valid configuration JSON object.');}
      await api('/api/task-configuration',{id:form.dataset.id,assignment_id:form.dataset.assignment,configuration});
      await taskDetail(form.dataset.id);return;
    }
    if(form.id==='task-proposal-form') {
      const a=await api('/api/task-approval',{preview_token:form.dataset.preview,reason:data.reason});
      await approvalDetail(a.id);return;
    }
    if(form.id==='file-edit-form') {
      await api('/api/project-file-update',{project_id:form.dataset.project,file_id:form.dataset.file,display_name:data.display_name,description:data.description,folder_id:data.folder_id||null,move:true});
      return fileDetail(form.dataset.project,form.dataset.file);
    }
    if(form.id==='file-attach-form') {
      await api('/api/task-file-attach',{project_id:form.dataset.project,file_id:form.dataset.file,task_id:data.task_id});
      return fileDetail(form.dataset.project,form.dataset.file);
    }
    if(form.id==='csv-connect-form') {
      const result=await api('/api/project-file-csv-bind',{project_id:form.dataset.project,file_id:form.dataset.file,task_id:data.task_id});
      notice(`CSV input connected to task. Input ${result.input_id}; SHA-256 ${result.sha256}. Execution still requires review and approval.`);
      return fileDetail(form.dataset.project,form.dataset.file);
    }
    if(form.id==='folder-form') {
      await api('/api/project-folders',{project_id:form.dataset.project,name:data.name});
      return projectDetail(form.dataset.project,'files');
    }
    if(form.id==='plan-form') await api('/api/decision',{...data,id:form.dataset.id,fingerprint:form.dataset.fingerprint});
    else {
      const kind=form.dataset.kind;
      if(kind==='task')data.priority=Number(data.priority);
      const d=await api('/api/'+(kind==='project'?'projects':kind==='task'?'tasks':'conversations'),data);
      if(kind==='conversation')conversation=d.id;
    }
    $('dialog').close();await render();notice('Saved to the local workspace.');
  });
});
document.addEventListener('change',event=>{
  if(event.target.id==='task-project'){projectFilter=event.target.value;render();}
  if(event.target.id==='conversation-select'){conversation=event.target.value||null;render();}
  if(['file-category','file-folder','file-unassigned'].includes(event.target.id)) {
    const project=event.target.dataset.project;const state=fileLibraryState.get(project)||{search:'',category:'all',folder_id:'',unassigned:false,view:'grid'};
    if(event.target.id==='file-category')state.category=event.target.value;
    if(event.target.id==='file-folder')state.folder_id=event.target.value;
    if(event.target.id==='file-unassigned')state.unassigned=event.target.checked;
    fileLibraryState.set(project,state);guarded(()=>projectDetail(project,'files'));
  }
});
let fileSearchTimer;
document.addEventListener('input',event=>{
  if(event.target.id==='file-search') {
    clearTimeout(fileSearchTimer);fileSearchTimer=setTimeout(()=>{const project=event.target.dataset.project;const state=fileLibraryState.get(project)||{category:'all',folder_id:'',unassigned:false,view:'grid'};state.search=event.target.value;fileLibraryState.set(project,state);guarded(()=>projectDetail(project,'files'));},250);
  }
});
$('close-dialog').onclick=()=>$('dialog').close();
$('menu').onclick=()=>{const open=$('sidebar').classList.toggle('open');$('menu').setAttribute('aria-expanded',String(open));};
$('refresh').onclick=()=>guarded(render);
$('navigation').innerHTML=Object.entries(views).map(([name,v])=>`<a href="#${name}"><span class="nav-icon" aria-hidden="true">${v[0]}</span>${v[1]}</a>`).join('');
window.addEventListener('hashchange',()=>{currentView=views[location.hash.slice(1)]?location.hash.slice(1):'dashboard';$('sidebar').classList.remove('open');$('menu').setAttribute('aria-expanded','false');render();});
currentView=views[location.hash.slice(1)]?location.hash.slice(1):'dashboard';render();
