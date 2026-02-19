
const API='http://localhost:8000';
const token=localStorage.getItem('bf_token');
const headers={'Authorization':`Bearer ${token}`,'Content-Type':'application/json'};

let _repoId=null;
let _repoData=null;   // full repo + commits
let _isOwner=false;
let _isStarred=false;
let _myUsername=null;

function signOut(){localStorage.removeItem('bf_token');localStorage.removeItem('bf_user');location.href='index.html';}

function switchTab(tab, btn){
  document.querySelectorAll('.tab-content').forEach(el=>el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el=>el.classList.remove('active'));
  document.getElementById('tab-'+tab).classList.add('active');
  btn.classList.add('active');
  // Lazy-load tree iframe
  if(tab==='tree' && _repoId){
    const iframe=document.getElementById('tree-iframe');
    if(!iframe.src) iframe.src=`project_tree.html?project=${_repoId}&embed=1`;
  }
}

/* ── Helpers ─────────────────────────────────────────────────── */
function timeAgo(ts){
  if(!ts) return '';
  const s=Math.floor((Date.now()-new Date(ts))/1000);
  if(s<60) return `${s}s ago`;
  if(s<3600) return `${Math.floor(s/60)}m ago`;
  if(s<86400) return `${Math.floor(s/3600)}h ago`;
  return `${Math.floor(s/86400)}d ago`;
}
function truncate(s,n){return s&&s.length>n?s.slice(0,n)+'…':s||'';}
function showStatus(id,msg,type){
  const el=document.getElementById(id);if(!el)return;
  el.className='status-line '+type;el.textContent=msg;el.style.display='block';
  if(type!=='info') setTimeout(()=>{el.style.display='none';},5000);
}
function moodEmoji(mood){
  const map={'EDM / Club Banger':'⚡','Trap / Hip-Hop':'🎤','Lo-fi Chill':'☕','Synthwave':'🌃','Deep House':'🌙','Drum and Bass':'🥁','Ambient':'🌊','Phonk':'💀','Calm Piano':'🎹','Acoustic Guitar':'🎸','Jazz':'🎷','Blues':'🎺','Orchestral':'🎻','R&B / Soul':'🎵','Epic Cinematic':'🏛️','Metal':'🤘','Indie Rock':'🎙️','Afrobeats':'🥁','Meditation':'🧘','Nature Sounds':'🌿','Sleep Drone':'😴','Bossa Nova':'🌴','8-Bit Game':'🕹️','Middle Eastern':'🎎'};
  return (map[mood]||'🎵')+' '+mood;
}

/* ── Load current user ────────────────────────────────────────── */
async function loadMe(){
  if(!token) return;
  try{
    const r=await fetch(`${API}/auth/me`,{headers});
    if(r.ok){const d=await r.json();_myUsername=d.username;}
  }catch{}
}

/* ── Main load ───────────────────────────────────────────────── */
async function loadRepo(){
  const params=new URLSearchParams(location.search);
  _repoId=params.get('id');
  if(!_repoId){
    document.getElementById('repo-header-area').innerHTML='<p style="color:var(--red);padding:40px;">No repository ID in URL. Use ?id=<repo_id></p>';
    return;
  }
  try{
    const r=await fetch(`${API}/projects/${_repoId}`,{headers});
    if(!r.ok) throw new Error('Repository not found');
    _repoData=await r.json();
    document.title=`${_repoData.name} — Melodyfy`;
    renderHeader();
    renderCommits();
    populateCommentPicker();
  }catch(e){
    document.getElementById('repo-header-area').innerHTML=`<div style="padding:60px;text-align:center;color:var(--red);">Error: ${e.message}</div>`;
  }
}

/* ── Render header ────────────────────────────────────────────── */
function renderHeader(){
  const r=_repoData;
  const latestCommit=r.commits&&r.commits[0];
  const latestBpm=latestCommit?.bpm;
  const latestKey=latestCommit?.key;
  const latestMood=latestCommit?.mood||(r.commits?.find(c=>c.mood))?.mood;

  // Check ownership
  try{const u=JSON.parse(localStorage.getItem('bf_user')||'{}');_isOwner=(u.username===r.owner);}catch{}

  let forkedBadge='';
  if(r.forked_from){
    forkedBadge=`<span class="tag tag-fork">🍴 forked</span>`;
  }

  document.getElementById('repo-header-area').innerHTML=`
    <div class="repo-header fade-in">
      <div class="repo-header-main">
        <div class="breadcrumb">
          <span>👤</span>
          <a href="/ui/index.html">${r.owner||'unknown'}</a>
          <span class="breadcrumb-sep">/</span>
          <span>${r.name}</span>
          ${forkedBadge}
        </div>
        <div class="repo-desc">${r.description||'<em style="color:var(--text-muted)">No description provided.</em>'}</div>
        <div class="repo-meta-tags">
          <span class="tag ${r.is_public?'tag-vis':'tag-private'}">${r.is_public?'🌐 public':'🔒 private'}</span>
          ${latestMood?`<span class="tag tag-mood">${moodEmoji(latestMood)}</span>`:''}
          ${latestBpm?`<span class="tag tag-bpm">♩ ${Math.round(latestBpm)} BPM</span>`:''}
          ${latestKey?`<span class="tag tag-key">🎼 ${latestKey}</span>`:''}
        </div>
        <div class="repo-stats">
          <span class="repo-stat">⭐ <strong id="star-count">${r.star_count||0}</strong> stars</span>
          <span class="repo-stat">▶ ${r.play_count||0} plays</span>
          <span class="repo-stat">📝 ${r.commit_count||r.commits?.length||0} commits</span>
          <span class="repo-stat">🕒 updated ${timeAgo(r.updated_at)}</span>
        </div>
      </div>
      <div class="repo-actions">
        <button class="btn btn-star" id="star-btn" onclick="toggleStar()">⭐ Star</button>
        <button class="btn btn-fork" onclick="forkRepo()">🍴 Fork</button>
        <a href="studio.html?repo_id=${r.id}" class="btn btn-green">🎵 Open in Studio</a>
      </div>
    </div>`;

  document.getElementById('tab-commits-label').textContent=`Commits (${r.commit_count||r.commits?.length||0})`;
  setTimeout(()=>document.querySelector('.repo-header.fade-in')?.classList.add('visible'),50);
}

/* ── Render commits ───────────────────────────────────────────── */
function renderCommits(){
  const commits=_repoData?.commits||[];
  const area=document.getElementById('commits-area');

  if(!commits.length){
    area.innerHTML=`<div class="empty-state">
      <div class="emoji">📭</div>
      <p>No commits yet</p>
      <p style="font-size:13px;margin-bottom:20px;">Generate a beat in the Studio and commit it here.</p>
      <a href="studio.html?repo_id=${_repoId}" class="btn btn-green">🎵 Open Studio</a>
    </div>`;
    return;
  }

  const latest=commits[0];
  const audioSrc=`${API}${latest.audio_url}`;

  let html=`
    <div class="featured-player fade-in">
      <div class="featured-label">Latest Commit — <span style="font-family:monospace;color:var(--blue);">${latest.hash}</span></div>
      <div class="featured-title">${latest.message||'Beat update'}</div>
      <div class="featured-meta">
        ${latest.mood?`<span>${moodEmoji(latest.mood)}</span>`:''}
        ${latest.bpm?`<span>♩ ${Math.round(latest.bpm)} BPM</span>`:''}
        ${latest.key?`<span>🎼 ${latest.key}</span>`:''}
        ${latest.duration?`<span>⏱ ${Number(latest.duration).toFixed(1)}s</span>`:''}
        <span>by <strong>${latest.author||'—'}</strong></span>
        <span>${timeAgo(latest.created_at)}</span>
      </div>
      <audio controls src="${audioSrc}" preload="none" onplay="bumpPlay()"></audio>
    </div>

    <div class="commit-list">`;

  commits.forEach((c,i)=>{
    const isRoot=!c.parent_id;
    const src=`${API}${c.audio_url}`;
    const rollbackUrl=`studio.html?restore_beat=${encodeURIComponent(c.audio_url)}&parent_hash=${encodeURIComponent(c.hash)}&repo_id=${_repoId}`;
    html+=`
      <div class="commit-row fade-in" style="animation-delay:${i*30}ms">
        <div class="commit-dot${isRoot?' root':''}">🎵</div>
        <div class="commit-body">
          <div class="commit-row-top">
            <a class="commit-hash" href="project_tree.html?project=${_repoId}" title="View in tree">${c.hash}</a>
            <span class="commit-msg">${c.message||'Beat update'}</span>
            <div class="commit-actions">
              <a href="${rollbackUrl}" class="btn btn-ghost btn-xs" title="Restore this version in Studio">↩ Restore</a>
              <a href="studio.html?parent_hash=${encodeURIComponent(c.hash)}&repo_id=${_repoId}" class="btn btn-ghost btn-xs" title="Branch from this commit">🌿 Branch</a>
            </div>
          </div>
          <div class="commit-bottom">
            ${c.mood?`<span>${moodEmoji(c.mood)}</span>`:''}
            ${c.bpm?`<span class="tag tag-bpm" style="font-size:11px;">♩ ${Math.round(c.bpm)} BPM</span>`:''}
            ${c.key?`<span class="tag tag-key" style="font-size:11px;">🎼 ${c.key}</span>`:''}
            ${c.energy!=null?`<span>⚡ energy ${Number(c.energy).toFixed(2)}</span>`:''}
            <span>👤 <strong>${c.author||'—'}</strong></span>
            <span>🕒 ${timeAgo(c.created_at)}</span>
            ${isRoot?'<span style="color:var(--green-accent);font-weight:600;">root</span>':''}
          </div>
          <div class="commit-audio-row">
            <audio controls src="${src}" preload="none" style="width:100%;height:28px;"></audio>
          </div>
        </div>
      </div>`;
  });

  html+='</div>';
  area.innerHTML=html;

  // Animate
  setTimeout(()=>{
    area.querySelectorAll('.fade-in').forEach((el,i)=>setTimeout(()=>el.classList.add('visible'),i*40));
  },50);
}

/* ── Star / Fork ──────────────────────────────────────────────── */
async function toggleStar(){
  if(!token){alert('Sign in to star repositories.');return;}
  const btn=document.getElementById('star-btn');
  const countEl=document.getElementById('star-count');
  try{
    if(_isStarred){
      await fetch(`${API}/projects/${_repoId}/star`,{method:'DELETE',headers});
      _isStarred=false;
      btn.textContent='⭐ Star';
      btn.style.background='';
      countEl.textContent=Math.max(0,(parseInt(countEl.textContent)||0)-1);
    } else {
      const r=await fetch(`${API}/projects/${_repoId}/star`,{method:'POST',headers});
      if(r.ok){const d=await r.json();_isStarred=true;btn.textContent='⭐ Unstar';btn.style.background='rgba(227,179,65,.3)';countEl.textContent=d.star_count||((parseInt(countEl.textContent)||0)+1);}
    }
  }catch(e){alert('Star failed: '+e.message);}
}

async function forkRepo(){
  if(!token){alert('Sign in to fork repositories.');return;}
  if(!confirm(`Fork "${_repoData?.name}" into your account?`)) return;
  try{
    const r=await fetch(`${API}/projects/${_repoId}/fork`,{method:'POST',headers});
    if(r.ok){
      const d=await r.json();
      if(confirm(`✓ Forked as "${d.name}"! Open it?`))
        location.href=`repo.html?id=${d.id}`;
    } else {
      const e=await r.json(); alert('Fork failed: '+(e.detail||r.status));
    }
  }catch(e){alert('Fork error: '+e.message);}
}

function bumpPlay(){
  fetch(`${API}/projects/${_repoId}/play`,{method:'POST'}).catch(()=>{});
}

/* ── Comments ─────────────────────────────────────────────────── */
function populateCommentPicker(){
  const commits=_repoData?.commits||[];
  const sel=document.getElementById('comment-commit-select');
  commits.forEach(c=>{
    const o=document.createElement('option');
    o.value=c.id;
    o.textContent=`${c.hash} — ${truncate(c.message||'Beat update',40)}`;
    sel.appendChild(o);
  });
  // Pre-select latest if available
  if(commits.length){
    sel.value=commits[0].id;
    loadComments(commits[0].id);
  }
}

async function loadComments(commitId){
  if(!commitId) return;
  const area=document.getElementById('comments-list-area');
  const inputArea=document.getElementById('comment-input-area');
  area.innerHTML='<div style="padding:20px;text-align:center;color:var(--text-muted);" class="loading-pulse">Loading comments…</div>';
  if(token) inputArea.style.display='block'; else inputArea.style.display='none';
  try{
    const r=await fetch(`${API}/projects/${_repoId}/commits/${commitId}/comments`,{headers});
    if(!r.ok) throw new Error(r.status);
    const comments=await r.json();
    renderComments(comments, commitId);
  }catch(e){
    area.innerHTML=`<div style="padding:20px;color:var(--red);">Error loading comments: ${e.message}</div>`;
  }
}

function renderComments(comments, commitId){
  const area=document.getElementById('comments-list-area');
  document.getElementById('tab-comments-label').textContent=`Comments (${comments.length})`;
  if(!comments.length){
    area.innerHTML='<div class="no-comments">No comments yet. Be the first to leave one!</div>';
    return;
  }
  area.innerHTML=`<div class="comment-list">${
    comments.map(c=>{
      const canDel=_myUsername&&c.author===_myUsername;
      return `<div class="comment-card fade-in">
        <div class="comment-header">
          <div class="collab-avatar">${(c.author||'?')[0].toUpperCase()}</div>
          <span class="comment-author">${c.author||'Unknown'}</span>
          <span class="comment-dot">•</span>
          <span>${timeAgo(c.created_at)}</span>
          ${canDel?`<button class="comment-del" onclick="deleteComment('${c.id}','${commitId}')">🗑</button>`:''}
        </div>
        <div class="comment-body">${escHtml(c.body)}</div>
      </div>`;
    }).join('')
  }</div>`;
  setTimeout(()=>area.querySelectorAll('.fade-in').forEach(el=>el.classList.add('visible')),50);
}

async function submitComment(){
  const sel=document.getElementById('comment-commit-select');
  const commitId=sel.value;
  if(!commitId){alert('Select a commit first.');return;}
  const body=document.getElementById('comment-body').value.trim();
  if(!body){showStatus('comment-status','Comment cannot be empty.','err');return;}
  showStatus('comment-status','Posting…','info');
  try{
    const r=await fetch(`${API}/projects/${_repoId}/commits/${commitId}/comments`,{
      method:'POST',headers,body:JSON.stringify({body})
    });
    if(!r.ok){const e=await r.json();throw new Error(e.detail||'Failed');}
    document.getElementById('comment-body').value='';
    document.getElementById('comment-status').style.display='none';
    await loadComments(commitId);
  }catch(e){showStatus('comment-status','✗ '+e.message,'err');}
}

async function deleteComment(commentId, commitId){
  if(!confirm('Delete this comment?')) return;
  try{
    const r=await fetch(`${API}/comments/${commentId}`,{method:'DELETE',headers});
    if(!r.ok){const e=await r.json();throw new Error(e.detail||'Failed');}
    await loadComments(commitId);
  }catch(e){alert('Delete failed: '+e.message);}
}

function escHtml(s){
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Boot ────────────────────────────────────────────────────── */
Promise.all([loadMe(), loadRepo()]);
