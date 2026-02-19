
(function(){
  const t=localStorage.getItem('bf_token');
  if(!t){location.href='index.html';return;}
  try{const p=JSON.parse(atob(t.split('.')[1]));if(p.exp&&p.exp<Date.now()/1000){localStorage.removeItem('bf_token');location.href='index.html';}}
  catch(e){localStorage.removeItem('bf_token');location.href='index.html';}
})();


const API='http://localhost:8000';
const token=localStorage.getItem('bf_token');
const headers={'Authorization':`Bearer ${token}`};
let _currentFile=null; // blob URL or filename of last generated beat
let _currentFilename=null;
let _analysisData=null;

function signOut(){ localStorage.removeItem('bf_token');localStorage.removeItem('bf_user');location.href='index.html'; }
function showStatus(id,msg,type='info'){ const el=document.getElementById(id); el.textContent=msg; el.className=`status-bar ${type}`; el.style.display='block'; setTimeout(()=>{el.style.display='none';},5000); }

/* ── Load user repos for selector ────────────────────────────── */
async function loadRepos(){
  try{
    const r=await fetch(`${API}/projects`,{headers:{...headers,'Content-Type':'application/json'}});
    const d=await r.json();
    const repos=d.repositories||d||[];
    const sel=document.getElementById('repo-select');
    repos.forEach(repo=>{
      const o=document.createElement('option');
      o.value=repo.id; o.textContent=repo.name;
      sel.appendChild(o);
    });
    // Check URL for repo_id
    const params=new URLSearchParams(location.search);
    if(params.get('repo_id')) sel.value=params.get('repo_id');
    // Pre-fill commit message for rollback/branch
    if(params.get('parent_hash')){
      const msg=document.getElementById('commit-msg');
      if(msg&&!msg.value) msg.value=`Rollback to ${params.get('parent_hash')}`;
    }
  }catch(e){console.error(e);}
}
loadRepos();

/* ── Rollback: restore a previous commit's audio on load ─────── */
(function handleRestoreBeat(){
  const params=new URLSearchParams(location.search);
  const restoreBeat=params.get('restore_beat');
  if(!restoreBeat) return;
  // restore_beat is like /audio/filename.wav
  const filename=restoreBeat.split('/').pop();
  _currentFilename=filename;
  _currentFile=`${API}${restoreBeat}`;
  // Show the audio in the session selector and label
  const sel=document.getElementById('session-beat-select');
  if(sel){ const o=document.createElement('option');o.value=filename;o.textContent=`↩ Restored: ${filename}`;o.selected=true;sel.appendChild(o); }
  const lbl=document.getElementById('current-audio-label');
  if(lbl){ lbl.textContent=`↩ Restored: ${filename}`;lbl.style.display='block'; }
  // Add a beat card for it so the player is visible
  setTimeout(()=>addBeatCard(filename,'↩ Restored version',`${API}${restoreBeat}`),200);
  // Show restore banner
  const banner=document.createElement('div');
  banner.style.cssText='position:fixed;top:64px;left:50%;transform:translateX(-50%);z-index:999;background:rgba(35,134,54,.9);color:#fff;padding:10px 24px;border-radius:8px;font-size:14px;font-weight:600;box-shadow:0 4px 24px rgba(0,0,0,.5);';
  banner.textContent=`↩ Restored version from commit ${params.get('parent_hash')||'previous'}`;
  document.body.appendChild(banner);
  setTimeout(()=>banner.remove(),5000);
})();

/* ── Waveform drawing ─────────────────────────────────────────── */
function drawWaveform(canvas, peaks){
  const ctx=canvas.getContext('2d');
  const w=canvas.width, h=canvas.height;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle='#111111';
  ctx.fillRect(0,0,w,h);
  const barW=Math.max(2,Math.floor(w/peaks.length)-1);
  peaks.forEach((p,i)=>{
    const barH=Math.max(2,(p||0)*h*0.9);
    const x=i*(barW+1);
    const g=ctx.createLinearGradient(0,h/2-barH/2,0,h/2+barH/2);
    g.addColorStop(0,'#39d353'); g.addColorStop(1,'#0e4429');
    ctx.fillStyle=g;
    ctx.beginPath();
    ctx.roundRect(x,h/2-barH/2,barW,barH,1);
    ctx.fill();
  });
}

function makeFakePeaks(n=80){ return Array.from({length:n},()=>0.1+Math.random()*0.85); }

/* ── Add beat card to UI ──────────────────────────────────────── */
function addBeatCard(filename, beatName, audioUrl){
  _currentFile=audioUrl;
  _currentFilename=filename;
  // populate session-beat dropdown
  const sel=document.getElementById('session-beat-select');
  if(sel){
    // remove duplicate if already exists
    const existing=[...sel.options].find(o=>o.value===filename);
    if(!existing){ const o=document.createElement('option'); o.value=filename; o.textContent=beatName||filename; sel.appendChild(o); }
    sel.value=filename;
  }
  // update label
  const lbl=document.getElementById('current-audio-label');
  if(lbl){ lbl.textContent='✓ '+( beatName||filename); lbl.style.display='block'; }
  const container=document.getElementById('beats-list');
  const id='beat-'+Date.now();
  const div=document.createElement('div');
  div.className='beat-card fade-in';
  div.id=id;
  div.innerHTML=`
    <div class="beat-card-header">
      <span class="beat-card-name">🎵 ${beatName}</span>
      <span class="tag">${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="beat-card-body">
      <canvas class="waveform-canvas" id="wf-${id}" width="600" height="56"></canvas>
      <audio id="audio-${id}" src="${audioUrl}" style="display:none;"></audio>
      <div class="beat-actions">
        <button class="btn btn-green" onclick="togglePlay('${id}')">▶ Play</button>
        <a class="btn btn-ghost" href="${audioUrl}" download="${filename}" style="font-size:13px;">⬇ Download</a>
        <button class="btn btn-blue" onclick="setCurrentAndSave('${filename}','${audioUrl}')">💾 Save</button>
      </div>
    </div>`;
  container.insertBefore(div, container.firstChild);
  setTimeout(()=>div.classList.add('visible'),50);
  // draw fake waveform; real one comes from analyze
  const canvas=div.querySelector(`#wf-${id}`);
  drawWaveform(canvas, makeFakePeaks(80));
}

let _playing={};
function togglePlay(id){
  const audio=document.getElementById(`audio-${id}`);
  const btn=document.querySelector(`#${id} .btn-green`);
  if(!audio) return;
  if(_playing[id]){ audio.pause(); btn.textContent='▶ Play'; _playing[id]=false; }
  else { audio.play(); btn.textContent='⏸ Pause'; _playing[id]=true; audio.onended=()=>{btn.textContent='▶ Play';_playing[id]=false;}; }
}

function setCurrentAndSave(filename, audioUrl){
  _currentFile=audioUrl; _currentFilename=filename;
  showStatus('save-status','Beat selected. Fill in the form above and commit!','info');
}

/* ── Mood suggestion data ────────────────────────────────────── */
const MOOD_DATA = {
  'EDM / Club Banger':  { prompt: 'energetic EDM beat with heavy bass drops, synthesizers, and pulsing drums, club music',                  bpm: 128, key: 'A minor',  keyReason: 'A minor creates dark floor tension — the classic key for hard-hitting club builds and drops.' },
  'Trap / Hip-Hop':     { prompt: 'dark trap beat with 808 bass, hi-hats, and atmospheric pads, hip hop production',                       bpm: 140, key: 'F# minor', keyReason: 'F# minor is brooding and menacing — the go-to minor key for trap’s cold, cinematic 808 energy.' },
  'Lo-fi Chill':        { prompt: 'lo-fi hip hop beat with vinyl crackle, mellow chords, relaxed drums, chill study music',                  bpm: 85,  key: 'F major',  keyReason: 'F major is warm and nostalgic — its slightly dark brightness perfectly captures lo-fi’s fuzzy comfort.' },
  'Synthwave':          { prompt: 'synthwave retro 80s electronic music with lush synthesizers, driving beat, nostalgic neon vibes',          bpm: 100, key: 'E minor',  keyReason: 'E minor has a yearning, haunted quality — the signature tonal feel of retro 80s neon soundscapes.' },
  'Deep House':         { prompt: 'deep house music with groovy bassline, smooth synthesizers, four-on-the-floor drums, midnight dance floor', bpm: 122, key: 'G minor',  keyReason: 'G minor is soulful and deep — its modal warmth drives the hypnotic, after-midnight groove of deep house.' },
  'Drum and Bass':      { prompt: 'fast drum and bass with rapid breakbeats, heavy sub-bass, aggressive energy',                              bpm: 174, key: 'D minor',  keyReason: 'D minor is tense and urgent — its sharp energy accelerates naturally alongside fast breakbeats.' },
  'Ambient':            { prompt: 'ambient atmospheric music with evolving synthesizer pads, ethereal textures, slow floating soundscape',     bpm: 60,  key: 'C major',  keyReason: 'C major is tonally neutral and open — no sharps or flats to distract; pure sound and space.' },
  'Phonk':              { prompt: 'phonk music with memphis rap samples, dark twisted bass, aggressive drums, drifting energy',               bpm: 130, key: 'D minor',  keyReason: 'D minor’s raw darkness perfectly mirrors phonk’s twisted Memphis grit and aggressive drift.' },
  'Calm Piano':         { prompt: 'calm solo piano music, emotional and introspective, soft dynamics, gentle melody',                         bpm: 70,  key: 'C major',  keyReason: 'C major (all white keys) keeps things clean and emotionally transparent — ideal for introspective piano.' },
  'Acoustic Guitar':    { prompt: 'fingerpicked acoustic guitar, warm and intimate, folk style, gentle arpeggios',                            bpm: 80,  key: 'G major',  keyReason: 'G major resonates with open guitar strings — warm, natural ring that makes acoustic arpeggios sing.' },
  'Jazz':               { prompt: 'smooth jazz with saxophone lead, soft piano chords, upright bass, brushed drums, late night bar vibe',    bpm: 110, key: 'Bb major', keyReason: 'B♭ major is the “jazz key” — trumpets, saxophones, and clarinets are all tuned to feel most comfortable here.' },
  'Blues':              { prompt: 'soulful blues guitar with electric guitar riffs, steady rhythm, emotional and raw, Delta blues feel',      bpm: 90,  key: 'E blues',  keyReason: 'E blues scale on guitar is played on open strings — raw, vocal bends that howl with authentic Delta soul.' },
  'Orchestral':         { prompt: 'cinematic orchestral music with strings, brass, and dramatic crescendos, epic film score feeling',         bpm: 80,  key: 'D minor',  keyReason: 'D minor is the quintessential cinematic key — rich, noble, and tragic, used in countless film scores.' },
  'R&B / Soul':         { prompt: 'modern R&B soul music with warm chord progressions, smooth bass, subtle drums, emotional vocals bed',      bpm: 90,  key: 'Ab major', keyReason: 'A♭ major is lush and smooth — beloved by soul, gospel, and R&B arrangers for its rich chord voicings.' },
  'Epic Cinematic':     { prompt: 'epic cinematic orchestral battle music with massive drums, brass fanfare, intense strings, heroic',         bpm: 90,  key: 'D minor',  keyReason: 'D minor’s grand, powerful character anchors epic battle themes — brass and strings peak in this register.' },
  'Metal':              { prompt: 'heavy metal music with distorted electric guitars, fast double kick drums, aggressive energy',               bpm: 160, key: 'E minor',  keyReason: 'E minor uses heavy open-string power chords — the natural territory for drop-tuned aggressive riffs.' },
  'Indie Rock':         { prompt: 'indie rock with jangly guitars, energetic drums, catchy melody, stadium anthemic feel',                    bpm: 130, key: 'D major',  keyReason: 'D major is bright and anthemic — jangly chords and capo-friendly shapes drive indie’s stadium energy.' },
  'Afrobeats':          { prompt: 'afrobeats music with percussion, talking drums, bright guitar riffs, danceable groove, West African rhythm',bpm: 100, key: 'F major',  keyReason: 'F major is uplifting and bright with a rhythmic bounce — the warmth of West African groove fits perfectly.' },
  'Meditation':         { prompt: 'peaceful meditation music with singing bowls, soft pads, nature ambience, slow breathing rhythm',           bpm: 50,  key: 'C major',  keyReason: 'C major is the most neutral tonal center — effortless to the ear, guiding the mind inward without tension.' },
  'Nature Sounds':      { prompt: 'gentle acoustic music blended with nature sounds, birds, stream, forest atmosphere, peaceful',              bpm: 60,  key: 'G major',  keyReason: 'G major is bright and pastoral — evokes rolling hills and open sky; acoustic instruments ring naturally here.' },
  'Sleep Drone':        { prompt: 'slow droning ambient music, very soft, hypnotic, warm bass tones, for sleep and relaxation',               bpm: 40,  key: 'C major',  keyReason: 'C major provides the simplest, most drift-inducing tonal anchor — nothing to snag attention as you fall asleep.' },
  'Bossa Nova':         { prompt: 'bossa nova Brazilian jazz with nylon string guitar, light percussion, romantic and breezy',                 bpm: 130, key: 'D minor',  keyReason: 'D minor’s breezy melancholy suits bossa’s romantic tension — lush maj7 and min9 extensions bloom naturally here.' },
  '8-Bit Game':         { prompt: 'retro video game chiptune music with 8-bit synth melodies, catchy loop, upbeat pixel adventure mood',      bpm: 140, key: 'C major',  keyReason: 'C major (all white keys) was the default scale for early game chips — clean, loopable, and universally catchy.' },
  'Middle Eastern':     { prompt: 'Middle Eastern music with oud, darbuka drums, haunting scales, traditional yet modern fusion',              bpm: 90,  key: 'D Hijaz',  keyReason: 'The Hijaz scale (raised 2nd degree) is the tonal hallmark of Arabic, Turkish, and Flamenco music.' },
};

function onMoodChange(mood){
  const data = MOOD_DATA[mood];
  const promptEl  = document.getElementById('prompt-input');
  const bpmEl     = document.getElementById('bpm-input');
  const keyEl     = document.getElementById('key-input');
  const hintEl    = document.getElementById('prompt-hint');
  if(data){
    promptEl.value = data.prompt;
    bpmEl.value    = data.bpm;
    keyEl.value    = data.key;
    hintEl.style.display = 'block';
    // Fire BPM hint
    onBpmHint(data.bpm);
    // Try to parse key string → sync root+scale selects
    // e.g. "F# minor", "A major", "C# minor"
    if(data.key){
      const parts = data.key.trim().split(/\s+/);
      const rawRoot = parts[0] || '';
      // normalise ASCII # → ♯
      const normRoot = rawRoot.replace('#','♯').replace('b','♭');
      const scaleWord = parts.slice(1).join(' ').toLowerCase();
      const rootSel  = document.getElementById('key-root');
      const scaleSel = document.getElementById('key-scale');
      if(rootSel){
        const opt = Array.from(rootSel.options).find(o=>o.value===normRoot);
        if(opt) rootSel.value = normRoot;
      }
      if(scaleSel){
        const scaleMap = { 'major':'major','minor':'minor','minor (natural)':'minor' };
        const mapped = scaleMap[scaleWord] || scaleWord;
        const opt = Array.from(scaleSel.options).find(o=>o.value===mapped);
        if(opt) scaleSel.value = mapped; else scaleSel.value='';
      }
      onKeyScaleChange(data.keyReason);
    }
    // Flash the fields so the user notices they were updated
    [promptEl, bpmEl].forEach(el=>{
      el.style.borderColor='var(--blue)';
      setTimeout(()=>{ el.style.borderColor=''; }, 1200);
    });
  } else {
    hintEl.style.display = 'none';
  }
}

/* ── BPM hint ─────────────────────────── */
const BPM_ZONES = [
  { max:55,  icon:'🌙', label:'Sleep / Drone',       detail:'Ultra-slow pulse. Best for sleep music, ambient drones, meditation.' },
  { max:70,  icon:'🧘', label:'Meditation / Ambient', detail:'Calm, breathing-pace feel. Great for ambient, new-age, deep focus.' },
  { max:85,  icon:'☕',     label:'Lo-fi / Ballad',       detail:'Laid-back groove. Perfect for lo-fi hip-hop, soul ballads, bossa nova.' },
  { max:95,  icon:'🎹', label:'Blues / R\u0026B',         detail:'Slow-to-mid groove. Ideal for blues, classic R\u0026B, gospel.' },
  { max:110, icon:'🎺', label:'Jazz / Funk',           detail:'Swinging mid-tempo. Sweet spot for jazz, funk, neo-soul.' },
  { max:120, icon:'🎉', label:'Pop / Hip-Hop',         detail:'Strong pop & hip-hop range. Feels natural and radio-ready.' },
  { max:128, icon:'🎸', label:'Indie / Rock',          detail:'Rock backbeat territory. Works great for indie, alternative, pop-rock.' },
  { max:135, icon:'🔥', label:'House / Dance Pop',     detail:'Classic house BPM. Peak dancefloor energy for house, garage, dance pop.' },
  { max:145, icon:'⚡',     label:'Techno / Trance',       detail:'Driving energy. Peak zone for techno, trance, EDM bangers.' },
  { max:160, icon:'💥', label:'Drum and Bass / Jungle', detail:'DnB territory. Fast rolling bass and breakbeats.' },
  { max:180, icon:'🤘', label:'Metal / Punk / Hardstyle', detail:'Aggressive, high-energy. Metal double-kicks, punk thrash, hardstyle.' },
  { max:999, icon:'🚀', label:'Extreme / Blast-Beat',  detail:'Extreme metal / speedcore. Intense, near-inhuman tempos.' },
];

function onBpmHint(val){
  const bpm = parseInt(val);
  const el = document.getElementById('bpm-hint');
  if(!el) return;
  if(!bpm || bpm < 20){
    el.textContent = ''; el.classList.remove('active'); return;
  }
  const zone = BPM_ZONES.find(z => bpm <= z.max) || BPM_ZONES[BPM_ZONES.length-1];
  el.innerHTML = `${zone.icon} <strong>${bpm} BPM</strong> — best for <strong>${zone.label}</strong><br><span style="color:var(--text-muted);">${zone.detail}</span>`;
  el.classList.add('active');
  // Sync to transport scrubber if open
  const trBpm = document.getElementById('tr-bpm');
  if(trBpm) onTrBpmChange(bpm);
}
/* ── Key / Scale picker ────────────────────────────── */
const SCALE_DESC = {
  'major':              'Bright, happy, resolved. Most common scale in western music.',
  'minor':              'Darker, emotional, introspective. Natural minor (Aeolian mode).',
  'pentatonic major':   'Open, folk-like, universally pleasing. 5 notes — hard to go wrong.',
  'pentatonic minor':   'Bluesy, soulful, rock guitar staple. Works over virtually any genre.',
  'blues':              'Pentatonic minor + blue note. Raw expressiveness, bends and grit.',
  'dorian':             'Minor-ish with a raised 6th — jazzy, funky, not as dark as pure minor.',
  'phrygian':           'Very dark, Spanish / flamenco flavour. Lowered 2nd creates tension.',
  'lydian':             'Dreamy, floating, otherworldly. Raised 4th makes it sound cinematic.',
  'mixolydian':         'Major scale with a flat 7 — bluesy, rock, dominant feel.',
  'locrian':            'Extremely tense and unresolved. Good for dissonance and horror.',
  'harmonic minor':     'Classical, Middle-Eastern tension. Raised 7th creates strong leading tone.',
  'melodic minor':      'Jazz favourite. Smooth ascending with raised 6 and 7.',
  'phrygian dominant':  'Exotic, flamenco, Middle Eastern. Harmonic minor\u2019s 5th mode.',
  'lydian dominant':    'Jazz/fusion. Bright like Lydian but with a dominant flat-7 twist.',
  'whole tone':         'Dreamlike, ambiguous, no tonal centre. Debussy, jazz impressionism.',
  'diminished':         'Maximum tension. Symmetrical 8-note scale. Sci-fi, horror, bebop.',
  'chromatic':          'All 12 semitones — atonal or passing-note runs.',
};

function onKeyScaleChange(moodHint){
  const root  = document.getElementById('key-root').value;
  const scale = document.getElementById('key-scale').value;
  const combined = [root, scale].filter(Boolean).join(' ');
  document.getElementById('key-input').value = combined;
  const hintEl = document.getElementById('key-scale-hint');
  if(!hintEl) return;
  const desc = SCALE_DESC[scale];
  let html = '';
  if(combined && desc){
    html = `♩ <strong>${combined}</strong> — ${desc}`;
  } else if(combined){
    html = `♩ Prompt will use "${combined}"`;
  }
  if(moodHint){
    html += `<span class="mood-key-reason">&#127925; ${moodHint}</span>`;
  }
  hintEl.innerHTML = html;
}

const TIMESIG_INFO = {
  '4/4':  { feel:'4 beats per bar — the most common feel in pop, rock, EDM, hip-hop.', subdiv:'Quarter note beat' },
  '3/4':  { feel:'3 beats per bar — waltz, classical, folk.', subdiv:'Quarter note beat, counted 1-2-3' },
  '6/8':  { feel:'6 eighth-notes per bar — compound feel, two groups of 3. Irish folk, shuffle, blues.', subdiv:'Eighth note beat' },
  '2/4':  { feel:'2 beats per bar — march, polka, upbeat and driving.', subdiv:'Quarter note beat' },
  '5/4':  { feel:'5 beats per bar — odd, forward-pushing feel. Progressive, jazz fusion.', subdiv:'Quarter note beat, counted 1-2-3-4-5' },
  '7/8':  { feel:'7 eighth-notes per bar — asymmetric, Balkan-influenced, irregular groove.', subdiv:'Eighth note beat' },
  '7/4':  { feel:'7 beats per bar — spacious odd meter. Tool, King Crimson, prog rock.', subdiv:'Quarter note beat, counted 1-2-3-4-5-6-7' },
  '12/8': { feel:'12 eighth-notes per bar — slow triplet shuffle. Blues ballads, gospel, soul.', subdiv:'Eighth note beat, 4 groups of 3' },
  '9/8':  { feel:'9 eighth-notes per bar — compound triple. Celtic, jazz.', subdiv:'Eighth note beat, 3 groups of 3' },
};

/* ── BPM Drag-Scrubber ─────────────────────────────── */
(function(){
  const SENSITIVITY = 0.6; // px per BPM step
  let _dragging = false, _startX = 0, _startBpm = 120;

  function _clamp(v){ return Math.max(20, Math.min(300, Math.round(v))); }

  function _applyBpm(val){
    const v = _clamp(val);
    document.getElementById('tr-bpm').value = v;
    document.getElementById('bpm-scrub').textContent = v;
    document.getElementById('bpm-range').value = v;
    onTrBpmChange(v);
  }

  window._bpmRangeInput = function(val){ _applyBpm(parseInt(val)); };

  window._bpmReset = function(){
    const orig = SE.originalBpm || 120;
    _applyBpm(orig);
  };

  window._bpmInputCommit = function(){
    const inp = document.getElementById('tr-bpm');
    const v = _clamp(parseInt(inp.value) || 120);
    inp.value = v;
    document.getElementById('bpm-scrub').textContent = v;
    document.getElementById('bpm-range').value = v;
    inp.classList.remove('active');
    onTrBpmChange(v);
  };

  document.addEventListener('DOMContentLoaded', function(){
    const scrub = document.getElementById('bpm-scrub');
    const inp   = document.getElementById('tr-bpm');
    if(!scrub) return;

    // Double-click → switch to text input
    scrub.addEventListener('dblclick', function(){
      inp.value = scrub.textContent;
      inp.classList.add('active');
      inp.focus(); inp.select();
    });

    // Drag scrub
    scrub.addEventListener('mousedown', function(e){
      if(e.detail >= 2) return; // ignore double-click mousedown
      e.preventDefault();
      _dragging = true;
      _startX = e.clientX;
      _startBpm = parseInt(scrub.textContent) || 120;
      scrub.classList.add('dragging');
      document.body.style.cursor = 'ew-resize';
    });

    // Touch support
    scrub.addEventListener('touchstart', function(e){
      _dragging = true;
      _startX = e.touches[0].clientX;
      _startBpm = parseInt(scrub.textContent) || 120;
      scrub.classList.add('dragging');
    }, {passive:true});

    document.addEventListener('mousemove', function(e){
      if(!_dragging) return;
      const delta = (e.clientX - _startX) / SENSITIVITY;
      _applyBpm(_startBpm + delta);
    });

    document.addEventListener('touchmove', function(e){
      if(!_dragging) return;
      const delta = (e.touches[0].clientX - _startX) / SENSITIVITY;
      _applyBpm(_startBpm + delta);
    }, {passive:true});

    function _endDrag(){
      if(!_dragging) return;
      _dragging = false;
      scrub.classList.remove('dragging');
      document.body.style.cursor = '';
    }
    document.addEventListener('mouseup', _endDrag);
    document.addEventListener('touchend', _endDrag);
  });
})();

/* ── Bidirectional transport ↔ generator form sync ─ */
function onTrBpmChange(val){
  const newBpm = parseInt(val) || 120;
  const newRatio = newBpm / SE.originalBpm;
  // Keep scrubber display + range in sync regardless of how this was called
  const scrub = document.getElementById('bpm-scrub');
  const range = document.getElementById('bpm-range');
  if(scrub && scrub.textContent != newBpm) scrub.textContent = newBpm;
  if(range && parseInt(range.value) !== newBpm) range.value = newBpm;
  document.getElementById('tr-bpm').value = newBpm;
  // Grey out reset button when already at original tempo
  const resetBtn = document.getElementById('bpm-reset-btn');
  if(resetBtn) resetBtn.classList.toggle('at-original', newBpm === SE.originalBpm);

  if(SE.playing){
    // Reanchor startedAt so position tracking stays accurate after rate change:
    // audioPos = (now - oldStartedAt) * oldRatio → must equal (now - newStartedAt) * newRatio
    const now = SE.audioCtx.currentTime;
    const audioPos = (now - SE.startedAt) * SE.playbackRatio;
    SE.startedAt = now - audioPos / newRatio;

    // Update live sources' playbackRate — no restart needed
    SE.sources.forEach(src => { if(src) src.playbackRate.value = newRatio; });

    // Recalculate end timer
    clearTimeout(SE._endTimer);
    const wallDuration = SE.duration / newRatio;
    const wallElapsed = now - SE.startedAt;
    const remaining = wallDuration - wallElapsed;
    if(remaining > 0){
      SE._endTimer = setTimeout(() => {
        if(SE.looping){ stemStop(); SE.playbackRatio = newRatio; _stemPlay(0); }
        else { stemStop(); }
      }, remaining * 1000 + 50);
    }
  }

  SE.playbackRatio = newRatio;
  drawRuler();

  // Pitch shift readout: semitones = 12 * log2(ratio)
  const cents = Math.round(1200 * Math.log2(newRatio));
  const semitones = (cents / 100).toFixed(1);
  const pitchEl = document.getElementById('tr-pitch-shift');
  if(pitchEl){
    pitchEl.textContent = semitones === '0.0' ? '' : (semitones > 0 ? `+${semitones} st` : `${semitones} st`);
    pitchEl.style.color = semitones === '0.0' ? '' : (cents > 0 ? '#fbbf24' : '#60a5fa');
  }

  // Keep generator form in sync
  const formBpm = document.getElementById('bpm-input');
  if(formBpm && formBpm.value !== val) formBpm.value = val;
}

function onTrTimesigChange(val){
  drawRuler();
  // Keep generator form select in sync
  const formTs = document.getElementById('timesig-input');
  if(formTs && formTs.value !== val) formTs.value = val;
  // Update hint
  const info = TIMESIG_INFO[val];
  const hint = document.getElementById('timesig-hint');
  if(info && hint) hint.innerHTML = `<strong>${val}</strong> — ${info.feel}<br><span style="color:var(--text-muted);">${info.subdiv}</span>`;
}

function onTimeSigChange(val){
  const hint = document.getElementById('timesig-hint');
  const info = TIMESIG_INFO[val];
  if(info && hint){
    hint.innerHTML = `<strong>${val}</strong> — ${info.feel}<br><span style="color:var(--text-muted);">${info.subdiv}</span>`;
  } else if(hint){
    hint.innerHTML = '';
  }
  // Sync to transport bar if stem editor is open
  const trTs = document.getElementById('tr-timesig');
  if(trTs) trTs.value = val;
  drawRuler();
}

/* ── Generate beat ────────────────────────────────────────────── */
async function generateBeat(){
  const prompt=document.getElementById('prompt-input').value.trim();
  if(!prompt){ alert('Please enter a prompt first!'); return; }
  const mood=document.getElementById('mood-select').value;
  const bpm=document.getElementById('bpm-input').value;
  const key=document.getElementById('key-input').value.trim();
  const duration=parseInt(document.getElementById('dur-input').value)||10;
  const timesig=document.getElementById('timesig-input').value;

  // Build enriched prompt
  let fullPrompt=prompt;
  if(bpm&&!fullPrompt.match(/\d+\s*bpm/i)) fullPrompt+=` ${bpm} BPM`;
  if(key&&!fullPrompt.toLowerCase().includes(key.toLowerCase())) fullPrompt+=` in ${key}`;
  if(timesig&&timesig!=='4/4'&&!fullPrompt.includes(timesig)) fullPrompt+=` ${timesig} time signature`;
  if(mood&&!fullPrompt.toLowerCase().includes(mood.toLowerCase())) fullPrompt+=` ${mood}`;

  const progWrap=document.getElementById('gen-progress');
  const progBar=document.getElementById('progress-bar');
  const progLabel=document.getElementById('progress-label');
  const genBtn=document.getElementById('gen-btn');

  genBtn.disabled=true;
  progWrap.style.display='block';
  progBar.style.width='5%';
  progLabel.textContent='Starting generation…';

  // Get project repo (optional)
  const repoId=document.getElementById('repo-select').value||null;
  const beatName=fullPrompt.slice(0,40)||'Generated beat';

  try{
    // Use tracked generation with SSE
    const taskRes=await fetch(`${API}/generate/tracked`,{
      method:'POST',
      headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify({name:beatName, prompt:fullPrompt, duration_seconds:duration, repo_id:repoId||undefined})
    });
    if(!taskRes.ok){ const e=await taskRes.json(); throw new Error(e.detail||'Generation failed'); }
    const {task_id}=await taskRes.json();

    // SSE progress
    await new Promise((resolve,reject)=>{
      const es=new EventSource(`${API}/sse/progress/${task_id}`);
      es.onmessage=ev=>{
        try{
          const d=JSON.parse(ev.data);
          if(d.progress!=null) progBar.style.width=`${Math.min(99,d.progress)}%`;
          if(d.message) progLabel.textContent=d.message;
          if(d.status==='done'){
            progBar.style.width='100%';
            progLabel.textContent='✓ Done!';
            es.close();
            const filename=d.filename||d.audio_url||`beat_${task_id}.wav`;
            const audioUrl=d.audio_url?`${API}${d.audio_url}`:`${API}/audio/${filename}`;
            setTimeout(()=>{ progWrap.style.display='none'; addBeatCard(filename,beatName,audioUrl); resolve(); },400);
          }
          if(d.status==='error'){ es.close(); reject(new Error(d.message||'Generation failed')); }
        }catch{}
      };
      es.onerror=()=>{ es.close(); reject(new Error('SSE connection lost')); };
      // Fallback timeout
      setTimeout(()=>{ if(es.readyState!==EventSource.CLOSED){ es.close(); reject(new Error('Generation timed out')); }},120000);
    });
  }catch(e){
    progWrap.style.display='none';
    showStatus('gen-status','✗ '+e.message,'err');
  }finally{
    genBtn.disabled=false;
  }
}

/* ── Hum to Beat ──────────────────────────────────────────────── */
function triggerHum(){
  const sec=document.getElementById('hum-section');
  sec.style.display=sec.style.display==='none'?'block':'none';
}
async function submitHum(){
  const file=document.getElementById('hum-file').files[0];
  if(!file){ alert('Please select an audio file first.'); return; }
  const fd=new FormData(); fd.append('audio',file);
  showStatus('gen-status','Converting hum to beat…','info');
  try{
    const r=await fetch(`${API}/hum`,{method:'POST',headers,body:fd});
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Hum failed'); }
    const d=await r.json();
    const audioUrl=`${API}${d.audio_url}`;
    addBeatCard(d.filename||'hum_beat.wav','Hum Beat',audioUrl);
    showStatus('gen-status','✓ Hum converted!','ok');
  }catch(e){ showStatus('gen-status','✗ '+e.message,'err'); }
}

/* ── Continue Beat ────────────────────────────────────────────── */
async function continueBeat(){
  if(!_currentFilename){ alert('No beat loaded to continue.'); return; }
  const btn=document.getElementById('cont-btn');
  btn.disabled=true; btn.textContent='⏳ Extending…';
  try{
    const r=await fetch(`${API}/continue`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify({filename:_currentFilename})
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Continue failed'); }
    const d=await r.json();
    addBeatCard(d.filename,'Extended Beat',`${API}${d.audio_url}`);
    showStatus('gen-status','✓ Beat extended!','ok');
  }catch(e){ showStatus('gen-status','✗ '+e.message,'err'); }
  finally{ btn.disabled=false; btn.textContent='⏭ Continue'; }
}

/* ── Select Audio helpers ────────────────────────────────────── */
function pickSessionBeat(filename){
  if(!filename) return;
  _currentFilename=filename;
  _currentFile=`${API}/audio/${filename}`;
  const lbl=document.getElementById('current-audio-label');
  lbl.textContent='✓ '+filename; lbl.style.display='block';
  showStatus('tools-status','✓ Beat selected: '+filename,'ok');
}

async function uploadAudioFile(input){
  const file=input.files[0]; if(!file) return;
  const fd=new FormData(); fd.append('file',file);
  showStatus('tools-status','Uploading '+file.name+'…','info');
  try{
    const r=await fetch(`${API}/upload`,{method:'POST',headers,body:fd});
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Upload failed'); }
    const d=await r.json();
    _currentFilename=d.filename;
    _currentFile=`${API}${d.audio_url}`;
    const lbl=document.getElementById('current-audio-label');
    lbl.textContent='✓ '+file.name+' (uploaded)'; lbl.style.display='block';
    // add to dropdown too
    const sel=document.getElementById('session-beat-select');
    if(sel){ const o=document.createElement('option'); o.value=d.filename; o.textContent=file.name; sel.appendChild(o); sel.value=d.filename; }
    showStatus('tools-status','✓ '+file.name+' ready for tools!','ok');
  }catch(e){ showStatus('tools-status','✗ '+e.message,'err'); }
  finally{ input.value=''; } // reset so same file can be re-picked
}

/* ── Analyze ──────────────────────────────────────────────────── */
async function analyzeAudio(){
  if(!_currentFilename){ showStatus('tools-status','No audio loaded yet.','err'); return; }
  showStatus('tools-status','Analyzing…','info');
  try{
    const r=await fetch(`${API}/analyze`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify({filename:_currentFilename})
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Analyze failed'); }
    _analysisData=await r.json();
    const card=document.getElementById('analysis-card'); card.style.display='block';
    document.getElementById('analysis-content').innerHTML=`
      <div class="row"><span class="analysis-key">BPM</span><span class="analysis-val">${_analysisData.bpm?.toFixed(1)||'—'}</span></div>
      <div class="row"><span class="analysis-key">Key</span><span class="analysis-val">${_analysisData.key||'—'}</span></div>
      <div class="row"><span class="analysis-key">Energy</span><span class="analysis-val">${_analysisData.energy?.toFixed(3)||'—'}</span></div>
      <div class="row"><span class="analysis-key">Duration</span><span class="analysis-val">${_analysisData.duration?.toFixed(1)||'—'}s</span></div>`;
    // Update waveform with real peaks
    if(_analysisData.waveform){
      const allCards=document.querySelectorAll('.beat-card canvas');
      if(allCards.length){ drawWaveform(allCards[0],_analysisData.waveform); }
    }
    showStatus('tools-status','✓ Analysis complete','ok');
    document.getElementById('cont-btn').disabled=false;
    if(_analysisData.bpm&&!document.getElementById('bpm-input').value) document.getElementById('bpm-input').value=Math.round(_analysisData.bpm);
  }catch(e){ showStatus('tools-status','✗ '+e.message,'err'); }
}

/* ── Separate stems ───────────────────────────────────────────── */
async function separateStems(){
  if(!_currentFilename){ showStatus('tools-status','No audio loaded yet.','err'); return; }
  showStatus('tools-status','Separating stems with DEMUCS… this takes ~30s','info');
  try{
    const r=await fetch(`${API}/separate`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify({filename:_currentFilename})
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Separation failed'); }
    const d=await r.json();
    const stemsSection=document.getElementById('stems-section'); stemsSection.style.display='block';
    const stemGrid=document.getElementById('stem-grid');
    const icons={drums:'🥁',bass:'🎸',vocals:'🎤',other:'🎹'};
    stemGrid.innerHTML=Object.entries(d.stems||{}).map(([name,url])=>`
      <div class="stem-card has-audio" onclick="playStem('${API}${url}')">
        <div class="stem-icon">${icons[name]||'🔊'}</div>
        <div class="stem-label">${name}</div>
      </div>`).join('');
    showStatus('tools-status','✓ Stems separated! Opening editor…','ok');
    // Launch FL-Studio editor
    initStemEditor(d.stems||{});
  }catch(e){ showStatus('tools-status','✗ '+e.message,'err'); }
}
function playStem(url){ new Audio(url).play(); }

/* ══════════════════════════════════════════════════════════════
   STEM EDITOR ENGINE
   ══════════════════════════════════════════════════════════════ */
const _stemEditor = {
  tracks: [],        // {name, url, audio, gainNode, panNode, canvas, muted, soloed, volume, pan}
  audioCtx: null,
  masterGain: null,
  analyser: null,
  playing: false,
  looping: false,
  duration: 0,
  startedAt: 0,
  pauseOffset: 0,
  rafId: null,
  sources: [],
  buffers: [],       // AudioBuffer[]
  _lastBeat: -1,     // for beat LED tracking
  _meterData: null,  // reused Uint8Array for analyser
  originalBpm: 120,  // BPM at which stems were loaded
  playbackRatio: 1,  // currentBpm / originalBpm → applied to AudioBufferSourceNode.playbackRate
};
const SE = _stemEditor;
const STEM_COLORS = { drums:'#f87171', bass:'#60a5fa', vocals:'#fbbf24', other:'#a78bfa' };
const STEM_ICONS  = { drums:'🥁', bass:'🎸', vocals:'🎤', other:'🎹' };

function initStemEditor(stems){
  // stems = {drums: '/audio/...', bass: '/audio/...', ...}
  if(!SE.audioCtx) SE.audioCtx = new (window.AudioContext||window.webkitAudioContext)();
  stemStop();
  SE.tracks = [];
  SE.sources = [];
  SE.buffers = [];
  SE.pauseOffset = 0;
  SE.duration = 0;
  // Capture the BPM at which stems are loaded — this is the "native" tempo
  SE.originalBpm = parseInt(document.getElementById('tr-bpm').value) || 120;
  SE.playbackRatio = 1;

  // Master gain + analyser
  SE.masterGain = SE.audioCtx.createGain();
  SE.analyser = SE.audioCtx.createAnalyser();
  SE.analyser.fftSize = 64;
  SE.masterGain.connect(SE.analyser);
  SE.analyser.connect(SE.audioCtx.destination);

  const trackContainer = document.getElementById('stem-tracks');
  trackContainer.innerHTML = '';

  const entries = Object.entries(stems);
  let loadCount = 0;

  entries.forEach(([name, url], idx) => {
    const fullUrl = url.startsWith('http') ? url : `${API}${url}`;
    const color = STEM_COLORS[name] || '#888';
    const icon = STEM_ICONS[name] || '🔊';

    // Create track row HTML
    const row = document.createElement('div');
    row.className = 'stem-track';
    row.id = `stem-track-${idx}`;
    row.innerHTML = `
      <div class="track-controls">
        <div class="track-header">
          <div class="track-icon" style="color:${color};">${icon}</div>
          <div class="track-name">${name}</div>
          <div class="track-btns">
            <button class="track-btn" title="Mute" onclick="stemMute(${idx})">M</button>
            <button class="track-btn" title="Solo" onclick="stemSolo(${idx})">S</button>
          </div>
        </div>
        <div class="track-sliders">
          <label>Vol</label>
          <input type="range" class="track-slider" min="0" max="150" value="100" oninput="stemSetVol(${idx},this.value)">
          <span class="vol-display" id="vol-${idx}">100%</span>
        </div>
        <div class="track-sliders">
          <label>Pan</label>
          <input type="range" class="track-slider" min="-100" max="100" value="0" oninput="stemSetPan(${idx},this.value)">
          <span class="vol-display" id="pan-${idx}">C</span>
        </div>
      </div>
      <div class="track-waveform-wrap" onclick="stemSeek(event,this)">
        <canvas id="wf-stem-${idx}" height="72"></canvas>
        <div class="playhead" id="ph-${idx}"></div>
      </div>
    `;
    trackContainer.appendChild(row);

    // Track data
    const track = {
      name, url: fullUrl, audio: null,
      gainNode: SE.audioCtx.createGain(),
      panNode: SE.audioCtx.createStereoPanner(),
      canvas: null, muted: false, soloed: false, volume: 1, pan: 0, buffer: null
    };
    track.gainNode.connect(track.panNode);
    track.panNode.connect(SE.masterGain);
    SE.tracks.push(track);

    // Load audio buffer
    fetch(fullUrl)
      .then(r => r.arrayBuffer())
      .then(buf => SE.audioCtx.decodeAudioData(buf))
      .then(decoded => {
        track.buffer = decoded;
        SE.buffers[idx] = decoded;
        SE.duration = Math.max(SE.duration, decoded.duration);
        track.canvas = document.getElementById(`wf-stem-${idx}`);
        drawStemWaveform(track.canvas, decoded, color);
        loadCount++;
        if(loadCount === entries.length){
          drawRuler();
          document.getElementById('tr-time').textContent = '0:00.0';
        }
      })
      .catch(e => console.error('Failed to load stem:', name, e));
  });

  // Show editor
  const editor = document.getElementById('stem-editor');
  editor.classList.add('active');
  editor.scrollIntoView({behavior:'smooth', block:'start'});

  // Set BPM and time signature from generator form if available
  const bpmVal = document.getElementById('bpm-input').value;
  if(bpmVal){
    document.getElementById('tr-bpm').value = bpmVal;
    const scrub = document.getElementById('bpm-scrub');
    const range = document.getElementById('bpm-range');
    if(scrub) scrub.textContent = bpmVal;
    if(range) range.value = bpmVal;
  }
  // Reset button is greyed — we're already at original tempo on load
  const resetBtn = document.getElementById('bpm-reset-btn');
  if(resetBtn) resetBtn.classList.add('at-original');
  const pitchEl = document.getElementById('tr-pitch-shift');
  if(pitchEl) pitchEl.textContent = '';
  const tsVal = document.getElementById('timesig-input').value;
  const trTs = document.getElementById('tr-timesig');
  if(trTs && tsVal) trTs.value = tsVal;
  drawRuler();
}

function closeStemEditor(){
  stemStop();
  document.getElementById('stem-editor').classList.remove('active');
}

/* ── Waveform drawing for stems ─────────────────────── */
function _buildPeakCache(buffer, pixelWidth){
  // Pre-compute min/max per pixel column from the raw PCM data.
  // Cached on the buffer object itself keyed by pixel width.
  if(!buffer._peakCache) buffer._peakCache = {};
  if(buffer._peakCache[pixelWidth]) return buffer._peakCache[pixelWidth];
  const data = buffer.getChannelData(0);
  const step = Math.ceil(data.length / pixelWidth);
  const mins = new Float32Array(pixelWidth);
  const maxs = new Float32Array(pixelWidth);
  for(let i = 0; i < pixelWidth; i++){
    let mn = 1, mx = -1;
    const base = i * step;
    for(let j = 0; j < step; j++){
      const v = data[base + j] || 0;
      if(v < mn) mn = v;
      if(v > mx) mx = v;
    }
    mins[i] = mn; maxs[i] = mx;
  }
  buffer._peakCache[pixelWidth] = { mins, maxs };
  return buffer._peakCache[pixelWidth];
}

function drawStemWaveform(canvas, buffer, color){
  if(!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  if(rect.width === 0) return;
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const w = Math.floor(rect.width), h = rect.height;

  ctx.fillStyle = 'rgba(0,0,0,.25)';
  ctx.fillRect(0,0,w,h);

  // Center line
  ctx.strokeStyle = 'rgba(255,255,255,.06)';
  ctx.beginPath(); ctx.moveTo(0,h/2); ctx.lineTo(w,h/2); ctx.stroke();

  // Use cached peaks — no PCM scan on re-draw
  const { mins, maxs } = _buildPeakCache(buffer, w);

  // Waveform lines
  ctx.beginPath();
  for(let i = 0; i < w; i++){
    const y1 = (1 + mins[i]) / 2 * h;
    const y2 = (1 + maxs[i]) / 2 * h;
    ctx.moveTo(i, y1); ctx.lineTo(i, y2);
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.globalAlpha = 0.85;
  ctx.stroke();
  ctx.globalAlpha = 1;

  // Fill area
  ctx.beginPath();
  for(let i = 0; i < w; i++){
    if(i === 0) ctx.moveTo(0, (1 + maxs[0]) / 2 * h);
    else ctx.lineTo(i, (1 + maxs[i]) / 2 * h);
  }
  for(let i = w - 1; i >= 0; i--) ctx.lineTo(i, (1 + mins[i]) / 2 * h);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.15;
  ctx.fill();
  ctx.globalAlpha = 1;
}

/* ── Ruler drawing ──────────────────────────────────── */
function drawRuler(){
  const canvas = document.getElementById('ruler-canvas');
  if(!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = 28 * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr,dpr);
  const w = rect.width, h = 28;
  ctx.clearRect(0,0,w,h);
  ctx.fillStyle = 'var(--bg-inset)';
  ctx.fillRect(0,0,w,h);

  if(SE.duration<=0) return;
  const bpm = parseInt(document.getElementById('tr-bpm').value)||120;

  // Parse time signature
  const tsSel = document.getElementById('tr-timesig');
  // Sync from generator form if user hasn't changed transport
  const formTs = document.getElementById('timesig-input');
  const tsVal = (tsSel ? tsSel.value : null) || (formTs ? formTs.value : '4/4') || '4/4';
  const [num, den] = tsVal.split('/').map(Number);
  // If denominator is 8, the beat unit is an eighth note (half a quarter)
  const beatSec = den === 8 ? 30/bpm : 60/bpm;
  const beatsPerBar = num;
  const barSec = beatSec * beatsPerBar;
  const totalBars = Math.ceil(SE.duration / barSec);

  ctx.fillStyle = '#888';
  ctx.font = '9px -apple-system, sans-serif';
  ctx.textBaseline = 'bottom';

  // Draw time sig label at far left
  ctx.fillStyle = 'rgba(255,255,255,.35)';
  ctx.fillText(tsVal, 4, h-4);
  ctx.fillStyle = '#888';

  for(let i=0; i<=totalBars; i++){
    const x = (i * barSec / SE.duration) * w;
    // Bar line
    ctx.strokeStyle = 'rgba(255,255,255,.15)';
    ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,h); ctx.stroke();
    if(i < totalBars) ctx.fillText(`${i+1}`, x+3, h-4);
    // Beat subdivisions
    for(let b=1; b<beatsPerBar; b++){
      const bx = x + (b * beatSec / SE.duration) * w;
      ctx.strokeStyle = 'rgba(255,255,255,.07)';
      ctx.beginPath(); ctx.moveTo(bx, h-8); ctx.lineTo(bx, h); ctx.stroke();
    }
  }
}

/* ── Transport controls ───────────────────────────── */
function stemPlayPause(){
  if(SE.audioCtx.state==='suspended') SE.audioCtx.resume();
  if(SE.playing){ _stemPause(); return; }
  _stemPlay(SE.pauseOffset);
}

function _stemPlay(offset){
  SE.sources.forEach(s=>{ try{s.stop();}catch(e){} });
  SE.sources = [];
  const now = SE.audioCtx.currentTime;
  SE.tracks.forEach((t,i) => {
    if(!t.buffer) return;
    const src = SE.audioCtx.createBufferSource();
    src.buffer = t.buffer;
    src.loop = false;
    src.playbackRate.value = SE.playbackRatio;   // apply current tempo ratio
    src.connect(t.gainNode);
    const startOff = Math.min(offset, t.buffer.duration / SE.playbackRatio);
    src.start(0, startOff * SE.playbackRatio);  // offset into the buffer is in buffer-time
    SE.sources[i] = src;
  });
  SE.startedAt = now - offset;
  SE.playing = true;
  document.getElementById('tr-play').textContent = '⏸';
  document.getElementById('tr-play').classList.add('play-active');
  _stemTick();

  // Auto-stop: wall-clock duration = audioDuration / playbackRatio
  const wallDuration = SE.duration / SE.playbackRatio;
  const remaining = wallDuration - offset;
  if(remaining > 0){
    SE._endTimer = setTimeout(()=>{
      if(SE.looping){ stemStop(); _stemPlay(0); }
      else { stemStop(); }
    }, remaining * 1000 + 50);
  }
}

function _stemPause(){
  SE.pauseOffset = SE.audioCtx.currentTime - SE.startedAt;
  SE.sources.forEach(s=>{ try{s.stop();}catch(e){} });
  SE.sources = [];
  SE.playing = false;
  clearTimeout(SE._endTimer);
  cancelAnimationFrame(SE.rafId);
  document.getElementById('tr-play').textContent = '▶';
  document.getElementById('tr-play').classList.remove('play-active');
}

function stemStop(){
  SE.sources.forEach(s=>{ try{s.stop();}catch(e){} });
  SE.sources = [];
  SE.playing = false;
  SE.pauseOffset = 0;
  clearTimeout(SE._endTimer);
  cancelAnimationFrame(SE.rafId);
  document.getElementById('tr-play').textContent = '▶';
  document.getElementById('tr-play').classList.remove('play-active');
  _updatePlayheads(0);
  document.getElementById('tr-time').textContent = '0:00.0';
  document.getElementById('master-meter').style.width = '0%';
  const bbEl = document.getElementById('tr-barbeat');
  if(bbEl) bbEl.textContent = '1.1';
  const led = document.getElementById('beat-led');
  if(led) led.classList.remove('beat-on','beat-accent');
  SE._lastBeat = -1;
}

function stemToggleLoop(){
  SE.looping = !SE.looping;
  const btn = document.getElementById('tr-loop');
  btn.classList.toggle('active', SE.looping);
}

function stemSeek(event, wrap){
  const rect = wrap.getBoundingClientRect();
  const pct = (event.clientX - rect.left) / rect.width;
  const seekTo = pct * SE.duration;
  if(SE.playing){
    _stemPause();
    SE.pauseOffset = seekTo;
    _stemPlay(seekTo);
  } else {
    SE.pauseOffset = seekTo;
    _updatePlayheads(pct);
    _updateTimeDisplay(seekTo);
  }
}

function _stemTick(){
  if(!SE.playing) return;
  // Elapsed wall-clock time → convert to audio position
  const wallElapsed = SE.audioCtx.currentTime - SE.startedAt;
  const elapsed = wallElapsed * SE.playbackRatio;   // position in the audio buffer
  const pct = Math.min(elapsed / SE.duration, 1);
  _updatePlayheads(pct);
  _updateTimeDisplay(elapsed);
  _updateMeter();
  _updateBeatLed(elapsed);
  SE.rafId = requestAnimationFrame(_stemTick);
}

function _updateBeatLed(elapsed){
  const bpm = parseInt(document.getElementById('tr-bpm').value) || 120;
  const tsVal = (document.getElementById('tr-timesig') || {value:'4/4'}).value || '4/4';
  const [num, den] = tsVal.split('/').map(Number);
  const beatSec = den === 8 ? 30 / bpm : 60 / bpm;
  const beatsPerBar = num;
  const totalBeat = Math.floor(elapsed / beatSec);
  const bar  = Math.floor(totalBeat / beatsPerBar);
  const beat = totalBeat % beatsPerBar;
  // Update bar:beat display
  const bbEl = document.getElementById('tr-barbeat');
  if(bbEl) bbEl.textContent = `${bar + 1}.${beat + 1}`;
  // Flash LED on each new beat
  if(totalBeat !== SE._lastBeat){
    SE._lastBeat = totalBeat;
    const led = document.getElementById('beat-led');
    if(led){
      led.classList.remove('beat-on','beat-accent');
      // Accent (brighter) on beat 1 of each bar
      led.classList.add(beat === 0 ? 'beat-accent' : 'beat-on');
      setTimeout(() => led.classList.remove('beat-on','beat-accent'), 80);
    }
  }
}

function _updatePlayheads(pct){
  const px = `${(pct*100).toFixed(3)}%`;
  document.getElementById('ruler-playhead').style.left = px;
  SE.tracks.forEach((_,i) => {
    const ph = document.getElementById(`ph-${i}`);
    if(ph) ph.style.left = px;
  });
}

function _updateTimeDisplay(sec){
  const m = Math.floor(sec/60);
  const s = sec%60;
  document.getElementById('tr-time').textContent = `${m}:${s<10?'0':''}${s.toFixed(1)}`;
}

function _updateMeter(){
  if(!SE.analyser) return;
  // Reuse the typed array to avoid GC pressure
  if(!SE._meterData || SE._meterData.length !== SE.analyser.frequencyBinCount)
    SE._meterData = new Uint8Array(SE.analyser.frequencyBinCount);
  SE.analyser.getByteFrequencyData(SE._meterData);
  let sum = 0;
  for(let i=0; i<SE._meterData.length; i++) sum += SE._meterData[i];
  const avg = sum / SE._meterData.length;
  const pct = Math.min(100, (avg/255)*150);
  document.getElementById('master-meter').style.width = pct+'%';
}

/* ── Mute / Solo / Volume / Pan ────────────────────── */
function stemMute(idx){
  const t = SE.tracks[idx];
  t.muted = !t.muted;
  const btn = document.querySelector(`#stem-track-${idx} .track-btn:first-child`);
  btn.classList.toggle('m-active', t.muted);
  document.getElementById(`stem-track-${idx}`).classList.toggle('muted', t.muted);
  _applyStemGains();
}

function stemSolo(idx){
  const t = SE.tracks[idx];
  t.soloed = !t.soloed;
  const btn = document.querySelectorAll(`#stem-track-${idx} .track-btn`)[1];
  btn.classList.toggle('s-active', t.soloed);
  _applyStemGains();
}

function _applyStemGains(){
  const anySolo = SE.tracks.some(t=>t.soloed);
  SE.tracks.forEach(t=>{
    let vol = t.volume;
    if(t.muted) vol = 0;
    else if(anySolo && !t.soloed) vol = 0;
    t.gainNode.gain.setTargetAtTime(vol, SE.audioCtx.currentTime, 0.02);
  });
}

function stemSetVol(idx, val){
  const v = parseInt(val)/100;
  SE.tracks[idx].volume = v;
  document.getElementById(`vol-${idx}`).textContent = val+'%';
  _applyStemGains();
}

function stemSetPan(idx, val){
  const v = parseInt(val)/100;
  SE.tracks[idx].pan = v;
  SE.tracks[idx].panNode.pan.setTargetAtTime(v, SE.audioCtx.currentTime, 0.02);
  const label = val==0?'C': val<0?`L${Math.abs(val)}`:`R${val}`;
  document.getElementById(`pan-${idx}`).textContent = label;
}

function setMasterVol(val){
  const v = parseInt(val)/100;
  SE.masterGain.gain.setTargetAtTime(v, SE.audioCtx.currentTime, 0.02);
  document.getElementById('master-vol-display').textContent = val+'%';
}

/* ── Export mix (client-side offline render) ─────── */
async function exportStemMix(){
  if(SE.buffers.length===0){ alert('No stems loaded.'); return; }
  const sr = SE.buffers[0].sampleRate;
  const len = Math.ceil(SE.duration * sr);
  const offline = new OfflineAudioContext(2, len, sr);
  const master = offline.createGain();
  const masterV = parseInt(document.getElementById('master-vol').value)/100;
  master.gain.value = masterV;
  master.connect(offline.destination);

  const anySolo = SE.tracks.some(t=>t.soloed);
  SE.tracks.forEach((t,i)=>{
    if(!t.buffer) return;
    const src = offline.createBufferSource();
    src.buffer = t.buffer;
    const g = offline.createGain();
    const p = offline.createStereoPanner();
    let vol = t.volume;
    if(t.muted) vol=0;
    else if(anySolo && !t.soloed) vol=0;
    g.gain.value = vol;
    p.pan.value = t.pan;
    src.connect(g); g.connect(p); p.connect(master);
    src.start(0);
  });

  const rendered = await offline.startRendering();
  // Encode WAV
  const wavBlob = audioBufferToWav(rendered);
  const url = URL.createObjectURL(wavBlob);
  const link = document.getElementById('export-link');
  link.href = url;
  link.download = 'stem_mix_' + Date.now() + '.wav';
  document.getElementById('export-panel').style.display = 'flex';
  showStatus('tools-status','✓ Mix rendered! Click download.','ok');
}

function audioBufferToWav(buffer){
  const numCh = buffer.numberOfChannels;
  const sr = buffer.sampleRate;
  const len = buffer.length;
  const bytesPerSample = 2;
  const blockAlign = numCh * bytesPerSample;
  const dataSize = len * blockAlign;
  const buf = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buf);
  function writeStr(offset, str){ for(let i=0;i<str.length;i++) view.setUint8(offset+i,str.charCodeAt(i)); }
  writeStr(0,'RIFF'); view.setUint32(4,36+dataSize,true); writeStr(8,'WAVE');
  writeStr(12,'fmt '); view.setUint32(16,16,true); view.setUint16(20,1,true);
  view.setUint16(22,numCh,true); view.setUint32(24,sr,true);
  view.setUint32(28,sr*blockAlign,true); view.setUint16(32,blockAlign,true);
  view.setUint16(34,16,true); writeStr(36,'data'); view.setUint32(40,dataSize,true);
  const channels = [];
  for(let c=0;c<numCh;c++) channels.push(buffer.getChannelData(c));
  let offset = 44;
  for(let i=0;i<len;i++){
    for(let c=0;c<numCh;c++){
      let s = Math.max(-1, Math.min(1, channels[c][i]));
      view.setInt16(offset, s<0?s*0x8000:s*0x7FFF, true);
      offset+=2;
    }
  }
  return new Blob([buf], {type:'audio/wav'});
}

/* ── Redraw on resize ──────────────────────────────── */
window.addEventListener('resize', ()=>{
  SE.tracks.forEach((t,i)=>{
    if(t.buffer && t.canvas){
      drawStemWaveform(t.canvas, t.buffer, STEM_COLORS[t.name]||'#888');
    }
  });
  drawRuler();
});

/* ── Master ───────────────────────────────────────────────────── */
async function masterAudio(){
  if(!_currentFilename){ showStatus('tools-status','No audio loaded yet.','err'); return; }
  showStatus('tools-status','Mastering… normalising loudness & limiting peaks…','info');
  try{
    const r=await fetch(`${API}/master`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify({filename:_currentFilename})
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Mastering failed'); }
    const d=await r.json();
    addBeatCard(d.filename,'Mastered: '+(_currentFilename||'beat'),`${API}${d.audio_url}`);
    // Show mastering analysis
    const a=d.analysis||{};
    const card=document.getElementById('analysis-card'); card.style.display='block';
    document.getElementById('analysis-content').innerHTML=`
      <div class="row"><span class="analysis-key">Original LUFS</span><span class="analysis-val">${a.original_lufs!=null?a.original_lufs+' LUFS':'—'}</span></div>
      <div class="row"><span class="analysis-key">Mastered LUFS</span><span class="analysis-val">${a.mastered_lufs!=null?a.mastered_lufs+' LUFS':'—'}</span></div>
      <div class="row"><span class="analysis-key">Peak</span><span class="analysis-val">${a.peak_db!=null?a.peak_db+' dBFS':'—'}</span></div>
      <div class="row"><span class="analysis-key">Duration</span><span class="analysis-val">${a.duration!=null?a.duration+'s':'—'}</span></div>
      <div class="row"><span class="analysis-key">Sample Rate</span><span class="analysis-val">${a.sample_rate!=null?a.sample_rate+' Hz':'—'}</span></div>`;
    showStatus('tools-status',`✓ Mastered to ${a.mastered_lufs!=null?a.mastered_lufs+' LUFS':'-14 LUFS'}, peak ${a.peak_db!=null?a.peak_db:'-1'} dBFS`,'ok');
  }catch(e){ showStatus('tools-status','✗ '+e.message,'err'); }
}

/* ── Save to Project (commit) ─────────────────────────────────── */
async function saveToProject(){
  if(!_currentFilename){ showStatus('save-status','Generate a beat first!','err'); return; }
  const repoId=document.getElementById('repo-select').value;
  if(!repoId){ showStatus('save-status','Select a project first!','err'); return; }
  const msg=document.getElementById('commit-msg').value||'New beat';
  // parent_hash comes from URL (branch-from-here / rollback flow)
  const params=new URLSearchParams(location.search);
  const parentHash=params.get('parent_hash')||undefined;
  try{
    const payload={
      filename:_currentFilename,            // ← CommitRequest expects `filename`
      message:msg,
      prompt:document.getElementById('prompt-input').value,
      mood:document.getElementById('mood-select').value||undefined,
      parent_hash:parentHash,              // ← CommitRequest uses parent_hash
    };
    const r=await fetch(`${API}/projects/${repoId}/commit`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Commit failed'); }
    const d=await r.json();
    const hash=d.hash||d.commit_hash||d.id?.slice(0,8);
    showStatus('save-status',`✓ Committed <code style="color:var(--blue)">${hash}</code> — <a href="repo.html?id=${repoId}" style="color:var(--blue)">View project →</a>`,'ok');
    document.getElementById('cont-btn').disabled=false;
  }catch(e){ showStatus('save-status','✗ '+e.message,'err'); }
}

/* ── Save to Library ──────────────────────────────────────────── */
async function saveToLibrary(){
  if(!_currentFilename){ showStatus('save-status','Generate a beat first!','err'); return; }
  try{
    const payload={
      filename:_currentFilename,
      mood:document.getElementById('mood-select').value||null,
      bpm:_analysisData?.bpm||null, key:_analysisData?.key||null,
      energy:_analysisData?.energy||null, duration:_analysisData?.duration||null,
      description:document.getElementById('prompt-input').value.slice(0,200)
    };
    const r=await fetch(`${API}/library/save`,{
      method:'POST', headers:{...headers,'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    if(!r.ok){ const e=await r.json(); throw new Error(e.detail||'Save failed'); }
    showStatus('save-status','✓ Saved to My Library!','ok');
  }catch(e){ showStatus('save-status','✗ '+e.message,'err'); }
}

// Scroll animations
const obs=new IntersectionObserver(e=>e.forEach(el=>{if(el.isIntersecting)el.target.classList.add('visible');}),{threshold:.1});
document.querySelectorAll('.fade-in').forEach(el=>obs.observe(el));
