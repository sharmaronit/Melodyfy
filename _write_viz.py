content = r'''/**
 * Melodyfy Music Visualizer
 * Self-contained Three.js / GLSL shader music visualizer.
 * Based on https://www.shadertoy.com/view/MtVBzG
 *
 * Queue-safe usage — works before OR after module loads:
 *   window._vizQueue = window._vizQueue || [];
 *   window._vizQueue.push({ wrapId:'vw-ID', audioId:'audio-ID' });
 *
 * Direct API:
 *   const viz = new MusicVisualizer(element, { preset:'melodyfy', height:80 });
 *   viz.connectAudio(audioEl);
 *   viz.start();
 */

import * as THREE from "https://esm.sh/three@0.175.0";

const VERT = `
varying vec2 vUv;
void main(){
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const FRAG = `
precision highp float;
uniform vec2  iResolution;
uniform float iTime;
uniform float lowFreq;
uniform float midFreq;
uniform float highFreq;
uniform float transitionFactor;
uniform float idleAnimation;
uniform float kickEnergy;
uniform float bounceEffect;
uniform vec3  bgColorDown;
uniform vec3  bgColorUp;
uniform vec3  color1In;
uniform vec3  color1Out;
uniform vec3  color2In;
uniform vec3  color2Out;
uniform vec3  color3In;
uniform vec3  color3Out;
uniform float baseSpeed;
uniform float idleSpeed;
uniform float bassReact;
uniform float midReact;
uniform float highReact;
uniform float kickReact;
uniform float bounceInt;
uniform float waveInt;
uniform float waveComp;
uniform float lineThick;
uniform float lineStraight;
uniform float idleWH;
uniform float grainIntensity;
uniform float grainSpeed;
varying vec2 vUv;

float sq(float v){ return v*v; }
float sst(float a, float b, float x){
  float t = clamp((x-a)/(b-a), 0.0, 1.0);
  return t*t*t*(t*(t*6.0-15.0)+10.0);
}
float gaussian(float z, float u, float o){
  return (1.0/(o*2.506628))*exp(-(sq(z-u))/(2.0*sq(o)));
}

void main(){
  vec2 p = vUv;
  vec3 bg = mix(bgColorDown, bgColorUp, clamp(p.y*2.0, 0.0, 1.0));
  float tf       = transitionFactor;
  float speed    = mix(idleSpeed, baseSpeed, tf);
  float straight = mix(1.0, lineStraight, tf);

  float idleW = idleWH * sin(p.x*5.0 + idleAnimation*0.2);
  float bass  = sq(lowFreq)   * bassReact * tf;
  float mid   = sq(midFreq)   * midReact  * tf;
  float hi    = sq(highFreq)  * highReact * tf;
  float kick  = sq(kickEnergy)* kickReact * 1.5 * tf;
  float bounce= bounceEffect  * bounceInt * tf;

  float curveI = mix(idleWH, 0.05 + waveInt*(bass + kick*0.7), tf);
  float curve  = curveI * sin(6.25*p.x + speed*iTime);
  float audioW = mix(0.0,(0.10*sin(p.x*20.0*waveComp)*bass+0.08*sin(p.x*30.0*waveComp)*mid+0.05*sin(p.x*50.0*waveComp)*hi)/straight,tf);

  float aFreqV = 40.0*waveComp+80.0*bass+90.0*kick;
  float aSpdV  = 1.5*speed+6.0*bass+6.0*kick;
  float aWv    = mix(idleW,(0.01+0.05*bass+0.1*kick)/straight,tf);
  float kickFx = (kickEnergy>0.1)?kickEnergy*0.3*sin(15.0*(p.x-iTime*0.5))*tf:0.0;
  float aOff   = bass*0.3*sin(p.x*10.0-iTime*2.0)+kickFx*0.7;
  float aY     = mix(0.5+idleW, 0.5+curve+audioW+aWv*sin(aFreqV*p.x-aSpdV*iTime)+aOff-bounce, tf);
  float aT     = lineThick*(1.0+bass*0.4+kick*0.8);
  float aDst   = distance(p.y,aY)*(2.0/aT);
  float aShp   = sst(1.0-clamp(aDst,0.0,1.0),1.0,0.99);
  vec3  kCol   = vec3(1.0,0.85,0.6);
  vec3  c1i    = mix(color1In, kCol, kickEnergy*0.6*tf);
  vec3  c1o    = mix(color1Out,vec3(1.0,0.5,0.0),kickEnergy*0.4*tf);
  vec3  lineA  = (1.0-aShp)*mix(c1i,c1o,aShp);
  float bSz    = 0.5+0.4*bass+kickEnergy*1.2*tf;
  float bBx    = 0.2+0.1*sin(iTime*0.2*speed)*mid;
  float bDst   = distance(p,vec2(bBx,aY));
  float bShp   = sst(1.0-clamp(bDst*bSz,0.0,1.0),1.0,0.99);
  vec3  ballA  = (1.0-bShp)*mix(c1i,c1o,bShp)*mix(1.0,0.2,tf);

  float bFreqV = 50.0*waveComp+100.0*mid;
  float bSpdV  = 2.0*speed+8.0*mid;
  float bWv    = mix(idleW*0.8,(0.01+0.05*mid)/straight,tf);
  float bOff   = mid*0.2*sin(p.x*15.0-iTime*1.5)+kickEnergy*0.1*sin(p.x*25.0-iTime*3.0)*tf;
  float bY     = mix(0.5+idleW*0.8, 0.5+curve-audioW+bWv*sin(bFreqV*p.x+bSpdV*iTime)*sin(bSpdV*iTime)+bOff-bounce*0.5, tf);
  float bT2    = lineThick*(1.0+mid*0.3+kickEnergy*0.3*tf);
  float bDst2  = distance(p.y,bY)*(2.0/bT2);
  float bShp2  = sst(1.0-clamp(bDst2,0.0,1.0),1.0,0.99);
  vec3  c2i    = mix(color2In,vec3(1.0,0.5,0.5),kickEnergy*0.3*tf);
  vec3  lineB  = (1.0-bShp2)*mix(c2i,color2Out,bShp2);
  float bb2    = 0.5+0.4*hi+kickEnergy*0.3*tf;
  float bBx2   = 0.8-0.1*sin(iTime*0.3*speed)*mid;
  float bDst3  = distance(p,vec2(bBx2,bY));
  float bShp3  = sst(1.0-clamp(bDst3*bb2,0.0,1.0),1.0,0.99);
  vec3  ballB  = (1.0-bShp3)*mix(c2i,color2Out,bShp3)*mix(1.0,0.2,tf);

  float cFreqV = 60.0*waveComp+120.0*hi;
  float cSpdV  = 2.5*speed+10.0*hi;
  float cWv    = mix(idleW*1.2,(0.01+0.05*hi)/straight,tf);
  float cOff   = hi*0.15*sin(p.x*20.0-iTime);
  float cY     = mix(0.5+idleW*1.2, 0.5+curve*0.7-audioW*0.5+cWv*sin(cFreqV*p.x+cSpdV*iTime)*sin(cSpdV*(iTime+0.1))+cOff-bounce*0.3, tf);
  float cT     = lineThick*(1.0+hi*0.2+kickEnergy*0.1*tf);
  float cDst   = distance(p.y,cY)*(2.0/cT);
  float cShp   = sst(1.0-clamp(cDst,0.0,1.0),1.0,0.99);
  vec3  lineC  = (1.0-cShp)*mix(color3In,color3Out,cShp);
  float bc     = 0.5+0.4*hi+kickEnergy*0.1*tf;
  float cBx    = 0.5+0.15*sin(iTime*0.4*speed)*hi;
  float cDst2  = distance(p,vec2(cBx,cY));
  float cShp2  = sst(1.0-clamp(cDst2*bc,0.0,1.0),1.0,0.99);
  vec3  ballC  = (1.0-cShp2)*mix(color3In,color3Out,cShp2)*mix(1.0,0.2,tf);

  bg = mix(bg, mix(bg, vec3(1.0), 0.2), kickEnergy*0.4*tf);
  vec3 col = bg + lineA + lineB + lineC + ballA + ballB + ballC;

  float seed  = dot(p, vec2(12.9898,78.233));
  float noise = fract(sin(seed)*43758.5453 + iTime*grainSpeed);
  noise = gaussian(noise, 0.0, 0.25);
  col  += vec3(noise)*(1.0-col)*grainIntensity;

  gl_FragColor = vec4(clamp(col,0.0,1.0), 1.0);
}
`;

const PRESETS = {
  melodyfy:{ bgD:[7,7,10],   bgU:[14,12,18],  c1i:[237,232,223], c1o:[170,160,148], c2i:[190,182,172], c2o:[110,105,100], c3i:[150,145,138], c3o:[80,78,75]  },
  warm:    { bgD:[40,20,10], bgU:[20,10,5],   c1i:[255,200,0],   c1o:[255,100,0],   c2i:[255,100,100], c2o:[200,50,50],   c3i:[255,150,50],  c3o:[200,100,0] },
  neon:    { bgD:[10,10,20], bgU:[5,5,15],    c1i:[255,0,255],   c1o:[128,0,255],   c2i:[0,255,255],   c2o:[0,128,255],   c3i:[255,255,0],   c3o:[255,128,0] },
  cool:    { bgD:[10,20,30], bgU:[5,10,20],   c1i:[100,200,255], c1o:[0,100,200],   c2i:[100,255,200], c2o:[0,150,100],   c3i:[150,200,255], c3o:[50,100,200]}
};

export class MusicVisualizer {
  constructor(container, options = {}) {
    if (!container) return;
    this._container = container;
    this._preset    = options.preset || 'melodyfy';
    this._height    = options.height || 80;
    this._running   = false;
    this._raf       = null;
    this._time      = Math.random() * 100;
    this._idleAnim  = Math.random() * 10;
    this._tf        = 0;
    this._playing   = false;
    this._built     = false;
    this._pendingStart = false;
    this._audioCtx  = null;
    this._analyser  = null;
    this._dataArray = null;
    this._audioEl   = null;
    this._low = 0; this._mid = 0; this._high = 0;
    this._kick = 0; this._kickDetected = false;
    this._kickDecay = 0.82;
    this._lastKickTime = 0;
    this._kickImpact = 0;
    this._bandEnergies  = Array(8).fill(0);
    this._bandHistories = Array(8).fill(null).map(() => []);
    this._deferBuild();
  }

  _deferBuild() {
    const check = () => {
      const w = this._container.offsetWidth;
      if (w > 0) { this._build(w); }
      else { requestAnimationFrame(check); }
    };
    check();
  }

  _build(w) {
    const c = this._container;
    const h = this._height;
    c.style.position = 'relative';
    c.style.overflow = 'hidden';

    this._scene  = new THREE.Scene();
    this._camera = new THREE.OrthographicCamera(-1,1,1,-1,0,1);
    this._camera.position.z = 1;
    this._renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this._renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this._renderer.setSize(w, h);

    const cvs = this._renderer.domElement;
    cvs.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;display:block;pointer-events:none;';
    c.appendChild(cvs);

    const p  = PRESETS[this._preset] || PRESETS.melodyfy;
    const v3 = rgb => new THREE.Vector3(rgb[0]/255, rgb[1]/255, rgb[2]/255);

    this._uni = {
      iResolution:      { value: new THREE.Vector2(w, h) },
      iTime:            { value: this._time },
      lowFreq:          { value: 0 }, midFreq: { value: 0 }, highFreq: { value: 0 },
      transitionFactor: { value: 0 },
      idleAnimation:    { value: this._idleAnim },
      kickEnergy:       { value: 0 }, bounceEffect: { value: 0 },
      baseSpeed:        { value: 1.0  }, idleSpeed:    { value: 0.10 },
      bassReact:        { value: 0.40 }, midReact:     { value: 0.50 },
      highReact:        { value: 0.40 }, kickReact:    { value: 0.60 },
      bounceInt:        { value: 0.15 }, waveInt:      { value: 0.08 },
      waveComp:         { value: 2.20 }, lineThick:    { value: 1.80 },
      lineStraight:     { value: 2.53 }, idleWH:       { value: 0.012 },
      grainIntensity:   { value: 0.055 }, grainSpeed:  { value: 2.0 },
      bgColorDown: { value: v3(p.bgD) }, bgColorUp:  { value: v3(p.bgU) },
      color1In:    { value: v3(p.c1i) }, color1Out:  { value: v3(p.c1o) },
      color2In:    { value: v3(p.c2i) }, color2Out:  { value: v3(p.c2o) },
      color3In:    { value: v3(p.c3i) }, color3Out:  { value: v3(p.c3o) },
    };

    const mat  = new THREE.ShaderMaterial({ vertexShader:VERT, fragmentShader:FRAG, uniforms:this._uni });
    const geo  = new THREE.PlaneGeometry(2, 2);
    this._mesh = new THREE.Mesh(geo, mat);
    this._scene.add(this._mesh);

    if (window.ResizeObserver) {
      this._ro = new ResizeObserver(() => this._resize());
      this._ro.observe(c);
    }

    this._built = true;
    if (this._pendingStart) { this._pendingStart = false; this._loop(); }
  }

  _resize() {
    if (!this._renderer) return;
    const w = this._container.offsetWidth || 100;
    this._renderer.setSize(w, this._height);
    this._uni.iResolution.value.set(w, this._height);
  }

  connectAudio(audioEl) {
    if (!audioEl) return;
    this._audioEl = audioEl;
    audioEl.addEventListener('play',  () => this._onPlay());
    audioEl.addEventListener('pause', () => this._onPause());
    audioEl.addEventListener('ended', () => this._onPause());
  }

  _onPlay() {
    if (!this._audioCtx) {
      this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      this._analyser  = this._audioCtx.createAnalyser();
      this._analyser.fftSize = 1024;
      this._dataArray = new Uint8Array(this._analyser.frequencyBinCount);
      if (!this._audioEl._mfyVizNode) {
        const src = this._audioCtx.createMediaElementSource(this._audioEl);
        this._audioEl._mfyVizNode = src;
      }
      this._audioEl._mfyVizNode.connect(this._analyser);
      this._analyser.connect(this._audioCtx.destination);
    }
    if (this._audioCtx.state === 'suspended') this._audioCtx.resume();
    this._playing = true;
    if (!this._running) this.start();
  }

  _onPause() { this._playing = false; }

  start() {
    if (this._running) return;
    this._running = true;
    if (!this._built) { this._pendingStart = true; return; }
    this._loop();
  }

  stop() {
    this._running = false;
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
  }

  destroy() {
    this.stop();
    if (this._ro) this._ro.disconnect();
    if (this._renderer) { this._renderer.dispose(); this._renderer.domElement.remove(); }
  }

  setPreset(name) {
    if (!this._uni) return;
    const p  = PRESETS[name] || PRESETS.melodyfy;
    const v3 = rgb => new THREE.Vector3(rgb[0]/255, rgb[1]/255, rgb[2]/255);
    this._uni.bgColorDown.value = v3(p.bgD); this._uni.bgColorUp.value  = v3(p.bgU);
    this._uni.color1In.value    = v3(p.c1i); this._uni.color1Out.value  = v3(p.c1o);
    this._uni.color2In.value    = v3(p.c2i); this._uni.color2Out.value  = v3(p.c2o);
    this._uni.color3In.value    = v3(p.c3i); this._uni.color3Out.value  = v3(p.c3o);
  }

  _loop() {
    if (!this._running || !this._built) return;
    this._raf = requestAnimationFrame(() => this._loop());
    this._time     += 0.012;
    this._idleAnim += 0.012;
    this._uni.iTime.value         = this._time;
    this._uni.idleAnimation.value = this._idleAnim;
    const rate = 0.03;
    if (this._playing && this._tf < 1) this._tf = Math.min(this._tf + rate, 1);
    else if (!this._playing && this._tf > 0) {
      this._tf = Math.max(this._tf - rate, 0);
      if (this._tf === 0) this._clearFreq();
    }
    this._uni.transitionFactor.value = this._tf;
    this._updateFreq();
    this._renderer.render(this._scene, this._camera);
  }

  _clearFreq() {
    this._low = this._mid = this._high = this._kick = 0;
    this._uni.lowFreq.value = this._uni.midFreq.value = this._uni.highFreq.value = 0;
    this._uni.kickEnergy.value = this._uni.bounceEffect.value = 0;
  }

  _updateFreq() {
    if (!this._analyser || this._tf === 0) return;
    this._analyser.getByteFrequencyData(this._dataArray);
    const bands = [[1,4],[4,9],[9,20],[20,40],[40,80],[80,160],[160,300],[300,500]];
    for (let i = 0; i < bands.length; i++) {
      const avg = this._wavg(this._dataArray.slice(...bands[i]));
      this._bandEnergies[i] = avg;
      this._bandHistories[i].unshift(avg);
      if (this._bandHistories[i].length > 4) this._bandHistories[i].pop();
    }
    const kickAvg = this._bandEnergies[1];
    const hist    = this._bandHistories[1];
    const recent  = hist.slice(1).reduce((s, v) => s + v, 0) / (hist.length - 1 || 1);
    const jump = kickAvg - recent;
    const now  = performance.now();
    if (jump > 0.06 && kickAvg > 0.15 && (!this._kickDetected || now - this._lastKickTime > 150)) {
      this._kickDetected = true;
      this._kick = Math.min(1, kickAvg * 2.0);
      this._kickImpact = 10;
      this._lastKickTime = now;
    } else {
      this._kick *= this._kickDecay;
      if (this._kick < 0.05) this._kickDetected = false;
      if (this._kickImpact > 0) this._kickImpact--;
    }
    const bass = (this._bandEnergies[1]*1.2 + this._bandEnergies[2]) / 2.2;
    const mid  = (this._bandEnergies[3] + this._bandEnergies[4]) / 2;
    const high = (this._bandEnergies[5] + this._bandEnergies[6] + this._bandEnergies[7]) / 3;
    this._low  = bass  > this._low  * 1.1 ? this._low*0.3  + bass*0.7  : this._low*0.85  + bass*0.15;
    this._mid  = mid   > this._mid  * 1.1 ? this._mid*0.4  + mid*0.6   : this._mid*0.80  + mid*0.20;
    this._high = high  > this._high * 1.05? this._high*0.5 + high*0.5  : this._high*0.80 + high*0.20;
    this._low  = Math.max(this._low, this._kick * 0.6);
    const bounce = this._kickImpact > 0 ? Math.pow(this._kickImpact / 10, 0.6) * 0.03 : 0;
    this._uni.lowFreq.value      = this._low;
    this._uni.midFreq.value      = this._mid;
    this._uni.highFreq.value     = this._high;
    this._uni.kickEnergy.value   = this._kick;
    this._uni.bounceEffect.value = bounce + this._kick * 0.025;
  }

  _wavg(arr) {
    if (!arr.length) return 0;
    let s = 0, w = 0, mx = 0;
    for (const v of arr) {
      const n = v / 255; mx = Math.max(mx, n);
      s += Math.pow(n, 1.5); w++;
    }
    return (s / w) * 0.7 + mx * 0.3;
  }
}

/* ── Queue processor: handle mounts pushed before OR after module load ── */
const _vizRegistry = {};

function _doMount(item) {
  const id = item.wrapId;
  if (_vizRegistry[id]) return;
  const wrap  = document.getElementById(id);
  const audio = item.audioId ? document.getElementById(item.audioId) : null;
  if (!wrap) return;
  const viz = new MusicVisualizer(wrap, { preset: item.preset || 'melodyfy', height: item.height || 80 });
  if (audio) viz.connectAudio(audio);
  viz.start();
  _vizRegistry[id] = viz;
}

// Drain any items queued before this module loaded
const _earlyQueue = Array.isArray(window._vizQueue) ? window._vizQueue : [];
_earlyQueue.forEach(_doMount);

// Future pushes are handled immediately
window._vizQueue = { push: (item) => _doMount(item) };

// Also expose class globally for external use
window.MusicVisualizer = MusicVisualizer;
'''

with open('visualizer.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
