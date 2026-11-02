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
  openDialog(d.task.title,`<h2>Overview</h2><p>${escape(d.task.description||'No description provided.')}</p><div class="details-grid">${kv('Task state',d.task.status)}${kv('Scheduling classification',d.dependency.classification)}${kv('Priority',d.task.priority)}${kv('Approval required',d.dependency.approval_required?'Yes':'No')}</div>
    <details open><summary>Assigned worker</summary>${assigned?`${kv('Binding',assigned.worker_id+' · v'+assigned.version)}${kv('Assigned',date(assigned.assigned_at))}${json(worker)}`:'<p class="muted">No explicit worker assignment.</p>'}${assignmentForm}<details><summary>Compare registered operations and requirements</summary>${json(catalog)}</details></details>
    <details open><summary>Dependencies</summary><p class="hint">${escape(d.dependency.reason)}</p>${deps.length?json(deps):'<p class="muted">No prerequisites recorded.</p>'}</details>
    <details open><summary>Configuration</summary>${configForm||(l.assignment?json(l.configuration):'<p class="muted">Configuration becomes available after worker assignment.</p>')}${l.configuration_error?`<p class="notice">${escape(l.configuration_error)}</p>`:''}</details>
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

async function handle(name,id) {
  if (name==='navigate') return navigate(id);
  if (name==='project') {projectFilter=id;return navigate('tasks');}
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
  if(target)guarded(()=>handle(target.dataset.action,target.dataset.id));
});
document.addEventListener('submit',event=>{
  if(!['create-form','plan-form','worker-form','worker-config-form','task-proposal-form'].includes(event.target.id))return;
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
});
$('close-dialog').onclick=()=>$('dialog').close();
$('menu').onclick=()=>{const open=$('sidebar').classList.toggle('open');$('menu').setAttribute('aria-expanded',String(open));};
$('refresh').onclick=()=>guarded(render);
$('navigation').innerHTML=Object.entries(views).map(([name,v])=>`<a href="#${name}"><span class="nav-icon" aria-hidden="true">${v[0]}</span>${v[1]}</a>`).join('');
window.addEventListener('hashchange',()=>{currentView=views[location.hash.slice(1)]?location.hash.slice(1):'dashboard';$('sidebar').classList.remove('open');$('menu').setAttribute('aria-expanded','false');render();});
currentView=views[location.hash.slice(1)]?location.hash.slice(1):'dashboard';render();
