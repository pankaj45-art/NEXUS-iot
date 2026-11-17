/* Lightweight, local neural-plexus wallpaper. No external assets or services. */
let activeCleanup = null;
export function startNeuralWallpaper(root = document) {
  activeCleanup?.();
  const host = root.querySelector('.nexus-live-wallpaper');
  if (!host) return;
  let canvas = host.querySelector('canvas.neural-plexus');
  if (!canvas) {
    canvas = document.createElement('canvas');
    canvas.className = 'neural-plexus';
    canvas.setAttribute('aria-hidden', 'true');
    host.appendChild(canvas);
  }
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  let width = 0, height = 0, raf = 0, last = 0, nodes = [], dpr = 1, disposed = false;
  const pointer = { x: -1000, y: -1000 };
  const palettes = { cinematic:{line:[0,240,255],node:[0,245,255],accent:[245,158,11]}, neural:{line:[62,190,235],node:[93,224,255],accent:[174,151,255]}, circuit:{line:[32,244,213],node:[53,255,211],accent:[22,140,255]}, aurora:{line:[71,255,209],node:[111,255,221],accent:[182,109,255]}, cosmos:{line:[124,140,255],node:[143,160,255],accent:[255,99,216]}, blueprint:{line:[123,232,255],node:[123,232,255],accent:[79,156,255]}, fusion:{line:[73,244,255],node:[73,244,255],accent:[255,195,107]} };
  const palette = () => palettes[host.dataset.wallpaper || 'cinematic'] || palettes.cinematic;
  const resize = () => {
    const box = host.getBoundingClientRect();
    width = Math.max(1, box.width); height = Math.max(1, box.height);
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`; canvas.style.height = `${height}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.max(34, Math.min(112, Math.round((width * height) / 18500)));
    nodes = Array.from({ length: count }, (_, i) => ({
      x: Math.random() * width, y: Math.random() * height,
      vx: (Math.random() - .5) * .22, vy: (Math.random() - .5) * .22,
      phase: Math.random() * Math.PI * 2, size: .7 + Math.random() * 1.5,
      hue: i % 5 === 0 ? 255 : (i % 3 === 0 ? 195 : 183),
      pulse: .35 + Math.random() * .65
    }));
    draw(performance.now(), true);
  };
  const draw = (now, staticFrame = false) => {
    if (disposed) return;
    if (!staticFrame && document.hidden) { raf = 0; return; }
    if (!staticFrame && now - last < 32) { raf = requestAnimationFrame(draw); return; }
    const dt = Math.min(2, (now - (last || now)) / 16.67 || 1); last = now;
    ctx.clearRect(0, 0, width, height);

    // Modern Tech Cinematic Engineering Wallpaper: High-tech holographic circuit traces,
    // energy bus routing, moving photon data packets, and oscilloscope waveforms.
    if (!host.dataset.wallpaper || host.dataset.wallpaper === 'cinematic') {
      const t = reduced.matches ? 0 : now * 0.001;
      const rx = width * 0.74, ry = height * 0.50;
      
      // 1. Subtle glowing radar / reactor rings
      if (!reduced.matches) {
        for (let k = 0; k < 3; k++) {
          const rad = ((now * 0.024 + k * 120) % 360);
          const alpha = 0.16 * (1 - rad / 360);
          ctx.strokeStyle = `rgba(0,240,255,${alpha})`;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(rx, ry, rad, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      // 2. High-speed traveling bus lines with 45-degree angled PCB routing
      const busLines = [
        [ [0, height * 0.16], [width * 0.22, height * 0.16], [width * 0.28, height * 0.24], [width * 0.52, height * 0.24], [width * 0.60, height * 0.32], [rx, ry] ],
        [ [0, height * 0.35], [width * 0.18, height * 0.35], [width * 0.26, height * 0.45], [width * 0.48, height * 0.45], [rx, ry] ],
        [ [0, height * 0.78], [width * 0.25, height * 0.78], [width * 0.34, height * 0.68], [width * 0.55, height * 0.68], [rx, ry] ],
        [ [0, height * 0.88], [width * 0.30, height * 0.88], [width * 0.38, height * 0.78], [width * 0.62, height * 0.78], [width * 0.70, ry], [rx, ry] ],
        [ [width * 0.35, 0], [width * 0.35, height * 0.22], [width * 0.45, height * 0.32], [rx, ry] ],
        [ [width, height * 0.28], [width * 0.88, height * 0.28], [rx, ry] ],
        [ [width, height * 0.72], [width * 0.85, height * 0.72], [rx, ry] ]
      ];

      ctx.lineWidth = 1.4;
      busLines.forEach((pts, bi) => {
        // Draw underlying subtle conductive trace
        ctx.strokeStyle = bi % 2 === 0 ? 'rgba(0,229,255,0.18)' : 'rgba(56,189,248,0.14)';
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        for (let p = 1; p < pts.length; p++) ctx.lineTo(pts[p][0], pts[p][1]);
        ctx.stroke();

        // High-speed photons / data packets traveling along the bus
        if (!reduced.matches) {
          const speed = 0.00018 + (bi % 3) * 0.00006;
          const cycle = ((now * speed + bi * 0.16) % 1);
          let totalLen = 0;
          const segLens = [];
          for (let p = 0; p < pts.length - 1; p++) {
            const l = Math.hypot(pts[p+1][0] - pts[p][0], pts[p+1][1] - pts[p][1]);
            segLens.push(l);
            totalLen += l;
          }
          let targetDist = cycle * totalLen;
          let curDist = 0, px = pts[0][0], py = pts[0][1];
          for (let p = 0; p < segLens.length; p++) {
            if (curDist + segLens[p] >= targetDist) {
              const rem = (targetDist - curDist) / segLens[p];
              px = pts[p][0] + (pts[p+1][0] - pts[p][0]) * rem;
              py = pts[p][1] + (pts[p+1][1] - pts[p][1]) * rem;
              break;
            }
            curDist += segLens[p];
          }

          const col = bi % 3 === 0 ? '0,245,255' : bi % 3 === 1 ? '245,158,11' : '129,140,248';
          ctx.beginPath();
          ctx.arc(px, py, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = `rgb(${col})`;
          ctx.shadowBlur = 10;
          ctx.shadowColor = `rgb(${col})`;
          ctx.fill();
          ctx.shadowBlur = 0;
        }
      });

      // 3. Oscilloscope waveform at bottom
      const oscY = height * 0.94;
      ctx.lineWidth = 1.2;
      ctx.strokeStyle = 'rgba(0,245,255,0.32)';
      ctx.beginPath();
      const oscW = Math.min(380, width * 0.35);
      const oscX = width - oscW - 24;
      for (let x = 0; x <= oscW; x += 3) {
        const nx = x / oscW;
        const wave = Math.sin(nx * 14 + t * 4) * 8 * Math.sin(nx * Math.PI) + Math.sin(nx * 32 - t * 6) * 3;
        if (x === 0) ctx.moveTo(oscX + x, oscY + wave);
        else ctx.lineTo(oscX + x, oscY + wave);
      }
      ctx.stroke();

      // 4. Interactive Crosshair Reticle for Pointer
      if (!reduced.matches && pointer.x > 0 && pointer.y > 0) {
        ctx.strokeStyle = 'rgba(0,245,255,0.22)';
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(pointer.x, pointer.y, 14, 0, Math.PI * 2);
        ctx.moveTo(pointer.x - 22, pointer.y); ctx.lineTo(pointer.x + 22, pointer.y);
        ctx.moveTo(pointer.x, pointer.y - 22); ctx.lineTo(pointer.x, pointer.y + 22);
        ctx.stroke();
      }

      if (!staticFrame && !reduced.matches) raf = requestAnimationFrame(draw);
      return;
    }

    // Data-Flow Aurora: layered, animated signal ribbons with traveling particles.
    // This is decorative background motion, not live device telemetry.
    if (host.dataset.wallpaper === 'aurora') {
      const t = reduced.matches ? 0 : now * 0.00022;
      const horizon = height * 0.53;
      const bands = [
        { rgb:[71,255,209], amp:height*.105, freq:1.55, phase:0.0, width:2.0 },
        { rgb:[36,170,255], amp:height*.075, freq:1.9, phase:1.4, width:1.5 },
        { rgb:[182,109,255], amp:height*.095, freq:1.35, phase:2.8, width:1.8 },
        { rgb:[44,115,255], amp:height*.055, freq:2.35, phase:4.2, width:1.0 }
      ];
      // Deep, low-contrast horizon grid.
      ctx.lineWidth = 1;
      for (let k=0;k<9;k++) {
        const y = horizon + k*k*height*.0048;
        ctx.strokeStyle = `rgba(65,170,220,${.035 + k*.004})`;
        ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(width,y); ctx.stroke();
      }
      for (let k=-7;k<=7;k++) {
        ctx.strokeStyle='rgba(65,170,220,.045)'; ctx.beginPath();
        ctx.moveTo(width*.5+k*width*.025,horizon); ctx.lineTo(width*.5+k*width*.13,height); ctx.stroke();
      }
      bands.forEach((b, bi) => {
        const grad = ctx.createLinearGradient(0,horizon-b.amp*2,0,horizon+b.amp*2);
        grad.addColorStop(0,`rgba(${b.rgb.join(',')},0)`);
        grad.addColorStop(.48,`rgba(${b.rgb.join(',')},.16)`);
        grad.addColorStop(.54,`rgba(${b.rgb.join(',')},.025)`);
        grad.addColorStop(1,`rgba(${b.rgb.join(',')},0)`);
        ctx.beginPath();
        for(let x=0;x<=width+4;x+=4){
          const nx=x/Math.max(1,width);
          const y=horizon + Math.sin(nx*Math.PI*b.freq*2+t*2.4+b.phase)*b.amp
            + Math.sin(nx*Math.PI*5.2-t*1.7+b.phase)*b.amp*.24
            + (nx-.5)*height*.08*(bi%2?1:-1);
          if(x===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
        }
        ctx.lineWidth=b.width; ctx.strokeStyle=`rgba(${b.rgb.join(',')},.58)`;
        ctx.shadowBlur=14; ctx.shadowColor=`rgb(${b.rgb.join(',')})`; ctx.stroke(); ctx.shadowBlur=0;
        // Broad translucent ribbon under each signal line.
        ctx.lineTo(width,horizon+height*.28); ctx.lineTo(0,horizon+height*.28); ctx.closePath();
        ctx.fillStyle=grad; ctx.fill();
        if(!reduced.matches){
          for(let n=0;n<5;n++){
            const nx=((now*.000035*(1+bi*.13)+n*.217+bi*.11)%1);
            const x=nx*width;
            const y=horizon + Math.sin(nx*Math.PI*b.freq*2+t*2.4+b.phase)*b.amp
              + Math.sin(nx*Math.PI*5.2-t*1.7+b.phase)*b.amp*.24
              + (nx-.5)*height*.08*(bi%2?1:-1);
            ctx.beginPath(); ctx.arc(x,y,1.2+(n%2)*.6,0,Math.PI*2);
            ctx.fillStyle=`rgba(${b.rgb.join(',')},.9)`; ctx.shadowBlur=10; ctx.shadowColor=`rgb(${b.rgb.join(',')})`; ctx.fill(); ctx.shadowBlur=0;
          }
        }
      });
      if (!staticFrame && !reduced.matches) raf = requestAnimationFrame(draw);
      return;
    }
    const maxLink = Math.max(92, Math.min(155, width * .105));
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      if (!staticFrame && !reduced.matches) {
        a.x += a.vx * dt; a.y += a.vy * dt; a.phase += .012 * dt;
        if (a.x < -12) a.x = width + 12; if (a.x > width + 12) a.x = -12;
        if (a.y < -12) a.y = height + 12; if (a.y > height + 12) a.y = -12;
      }
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, dist = Math.hypot(dx, dy);
        if (dist > maxLink) continue;
        const alpha = (1 - dist / maxLink) * .22;
        const pal = palette();
        ctx.strokeStyle = `rgba(${pal.line.join(',')},${alpha})`; ctx.lineWidth = .65;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        // Moving data packet along selected links, deliberately subtle.
        if (!reduced.matches && dist < maxLink * .72 && ((i * 7 + j * 3) % 13 === 0)) {
          const t = (now * .00011 + a.phase + i * .13) % 1;
          const px = a.x + (b.x - a.x) * t, py = a.y + (b.y - a.y) * t;
          ctx.fillStyle = `rgba(${palette().node.join(',')},.82)`; ctx.shadowBlur = 7; ctx.shadowColor = `rgb(${palette().node.join(',')})`;
          ctx.beginPath(); ctx.arc(px, py, 1.2, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
        }
      }
      const pulse = reduced.matches ? .6 : .45 + .35 * Math.sin(a.phase);
      const pal = palette();
      const nodeColor = a.hue === 255 ? pal.accent : pal.node;
      ctx.fillStyle = `rgba(${nodeColor.join(',')},${pulse})`;
      ctx.shadowBlur = 8; ctx.shadowColor = `rgb(${nodeColor.join(',')})`;
      ctx.beginPath(); ctx.arc(a.x, a.y, a.size, 0, Math.PI * 2); ctx.fill(); ctx.shadowBlur = 0;
    }
    // Faint signal ripples anchor the visual in an engineering/telemetry theme.
    const cx = width * .76, cy = height * .43;
    if (!reduced.matches) {
      for (let k = 0; k < 3; k++) {
        const r = ((now * .012 + k * 105) % 315);
        ctx.strokeStyle = `rgba(${palette().line.join(',')},${.075 * (1 - r / 315)})`;
        ctx.lineWidth = 1; ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
      }
    }
    if (!staticFrame && !reduced.matches) raf = requestAnimationFrame(draw);
  };
  const onPointer = e => { const r = host.getBoundingClientRect(); pointer.x = e.clientX - r.left; pointer.y = e.clientY - r.top; };
  const onVisibility = () => { if (!document.hidden && !reduced.matches && !raf) raf = requestAnimationFrame(draw); };
  const onMotion = () => { cancelAnimationFrame(raf); raf = 0; if (reduced.matches) draw(performance.now(), true); else raf = requestAnimationFrame(draw); };
  const observer = new ResizeObserver(resize);
  observer.observe(host); window.addEventListener('pointermove', onPointer, { passive: true });
  document.addEventListener('visibilitychange', onVisibility); reduced.addEventListener?.('change', onMotion);
  resize(); if (!reduced.matches) raf = requestAnimationFrame(draw);
  activeCleanup = () => { disposed = true; cancelAnimationFrame(raf); observer.disconnect(); window.removeEventListener('pointermove', onPointer); document.removeEventListener('visibilitychange', onVisibility); reduced.removeEventListener?.('change', onMotion); };
  return activeCleanup;
}
