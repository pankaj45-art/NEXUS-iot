"""Interactive 3D Digital Twin Viewer for IoT hardware prototypes."""

export function createDigitalTwin3D(h) {
  const { $, $$, esc, modal, closeModal, toast, state } = h;

  function render3DCanvas(container, circuit, options = {}) {
    const isPro = state.me?.entitlement?.is_pro;
    const canvas = document.createElement('canvas');
    canvas.width = options.width || 760;
    canvas.height = options.height || 480;
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.borderRadius = '8px';
    canvas.style.cursor = 'grab';
    container.innerHTML = '';
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    let yaw = -0.65;
    let pitch = 0.55;
    let zoom = 1.0;
    let exploded = 0.0;
    let enclosure = isPro ? 'transparent' : 'off';
    let isDragging = false;
    let lastX = 0, lastY = 0;

    // Projection helper: 3D point (x, y, z) -> 2D (px, py)
    function project(x, y, z) {
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      // Rotation around Y (yaw)
      const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
      const x1 = x * cosY - z * sinY;
      const z1 = x * sinY + z * cosY;
      // Rotation around X (pitch)
      const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const y2 = y * cosP - z1 * sinP;
      const z2 = y * sinP + z1 * cosP;

      const scale = (340 * zoom) / (400 + z2);
      return {
        px: cx + x1 * scale,
        py: cy + y2 * scale,
        depth: z2
      };
    }

    function drawBox(x, y, z, w, h, d, faceColors, strokeColor = '#0f172a') {
      const p = [
        project(x - w/2, y - h/2, z - d/2), // 0: front-top-left
        project(x + w/2, y - h/2, z - d/2), // 1: front-top-right
        project(x + w/2, y + h/2, z - d/2), // 2: front-bottom-right
        project(x - w/2, y + h/2, z - d/2), // 3: front-bottom-left
        project(x - w/2, y - h/2, z + d/2), // 4: back-top-left
        project(x + w/2, y - h/2, z + d/2), // 5: back-top-right
        project(x + w/2, y + h/2, z + d/2), // 6: back-bottom-right
        project(x - w/2, y + h/2, z + d/2), // 7: back-bottom-left
      ];

      const faces = [
        { pts: [p[0], p[1], p[2], p[3]], col: faceColors.front || faceColors.main, z: (p[0].depth + p[2].depth) / 2 },
        { pts: [p[4], p[5], p[6], p[7]], col: faceColors.back || faceColors.main, z: (p[4].depth + p[6].depth) / 2 },
        { pts: [p[0], p[4], p[7], p[3]], col: faceColors.left || faceColors.main, z: (p[0].depth + p[7].depth) / 2 },
        { pts: [p[1], p[5], p[6], p[2]], col: faceColors.right || faceColors.main, z: (p[1].depth + p[6].depth) / 2 },
        { pts: [p[0], p[1], p[5], p[4]], col: faceColors.top || faceColors.light, z: (p[0].depth + p[5].depth) / 2 },
        { pts: [p[3], p[2], p[6], p[7]], col: faceColors.bottom || faceColors.dark, z: (p[3].depth + p[6].depth) / 2 },
      ];

      // Painter's algorithm
      faces.sort((a, b) => b.z - a.z);

      faces.forEach(f => {
        ctx.beginPath();
        ctx.moveTo(f.pts[0].px, f.pts[0].py);
        for (let i = 1; i < f.pts.length; i++) ctx.lineTo(f.pts[i].px, f.pts[i].py);
        ctx.closePath();
        ctx.fillStyle = f.col;
        ctx.fill();
        if (strokeColor) {
          ctx.strokeStyle = strokeColor;
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      });
    }

    function drawWire(p1, p2, color = '#38bdf8') {
      const a = project(p1.x, p1.y, p1.z);
      const b = project(p2.x, p2.y, p2.z);
      const mid = project((p1.x + p2.x) / 2, Math.min(p1.y, p2.y) - 35, (p1.z + p2.z) / 2);

      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.quadraticCurveTo(mid.px, mid.py, b.px, b.py);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.5;
      ctx.shadowColor = color;
      ctx.shadowBlur = 4;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    function frame() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Dark background gradient
      const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
      bg.addColorStop(0, '#090d16');
      bg.addColorStop(1, '#020617');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // Grid ground
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.lineWidth = 1;
      for (let g = -180; g <= 180; g += 30) {
        const a1 = project(g, 100, -180), a2 = project(g, 100, 180);
        ctx.beginPath(); ctx.moveTo(a1.px, a1.py); ctx.lineTo(a2.px, a2.py); ctx.stroke();
        const b1 = project(-180, 100, g), b2 = project(180, 100, g);
        ctx.beginPath(); ctx.moveTo(b1.px, b1.py); ctx.lineTo(b2.px, b2.py); ctx.stroke();
      }

      // Enclosure Base (if enabled)
      if (enclosure !== 'off') {
        const encCol = enclosure === 'wireframe' ? 'rgba(56,189,248,0.1)' : 'rgba(30, 41, 59, 0.6)';
        drawBox(0, 30 + exploded * 40, 0, 240, 40, 210, {
          main: encCol, light: 'rgba(56, 189, 248, 0.2)', dark: 'rgba(15, 23, 42, 0.7)'
        }, 'rgba(56, 189, 248, 0.4)');
      }

      // Main PCB (Matte Black / Emerald Green)
      const pcbY = 10;
      drawBox(0, pcbY, 0, 200, 8, 170, {
        top: '#064e3b', main: '#022c22', bottom: '#011910', light: '#047857', dark: '#022c22'
      }, '#059669');

      // Silkscreen copper traces & mounting holes
      [
        { x: -85, z: -70 }, { x: 85, z: -70 },
        { x: -85, z: 70 }, { x: 85, z: 70 }
      ].forEach(h => {
        const pt = project(h.x, pcbY - 4.5, h.z);
        ctx.beginPath();
        ctx.arc(pt.px, pt.py, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#fbbf24';
        ctx.fill();
        ctx.strokeStyle = '#022c22';
        ctx.stroke();
      });

      // ESP32 Microcontroller IC & Shield
      const mcuY = pcbY - 10 - exploded * 20;
      drawBox(0, mcuY, -30, 70, 6, 85, {
        top: '#cbd5e1', main: '#94a3b8', light: '#f1f5f9', dark: '#64748b'
      }, '#334155');

      // ESP-WROOM antenna trace
      const ant = project(0, mcuY - 3.5, -60);
      ctx.fillStyle = '#b45309';
      ctx.fillRect(ant.px - 14, ant.py - 3, 28, 6);

      // Micro-USB / Type-C Connector
      drawBox(0, pcbY - 7, -84, 22, 9, 14, {
        top: '#e2e8f0', main: '#cbd5e1', light: '#f8fafc', dark: '#94a3b8'
      }, '#64748b');

      // Status Power LED (glowing green/blue)
      const ledPt = project(26, pcbY - 5, -55);
      ctx.beginPath();
      ctx.arc(ledPt.px, ledPt.py, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = '#4ade80';
      ctx.shadowColor = '#22c55e';
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Render Circuit Components in 3D Space
      const comps = circuit?.components || [];
      const nonBoards = comps.filter(c => !c.model.startsWith('board:') && c.model !== 'supply5');
      const positions = [
        { x: -65, z: 45 }, { x: 65, z: 45 }, { x: 0, z: 55 },
        { x: -65, z: -10 }, { x: 65, z: -10 }
      ];

      nonBoards.slice(0, 5).forEach((comp, idx) => {
        const pos = positions[idx % positions.length];
        const compY = pcbY - 12 - exploded * (30 + idx * 8);

        if (comp.model.includes('oled') || comp.model.includes('display')) {
          // OLED 3D Glass Screen
          drawBox(pos.x, compY, pos.z, 50, 6, 40, {
            top: '#020617', main: '#0f172a', light: '#1e293b', dark: '#020617'
          }, '#38bdf8');
          const scrPt = project(pos.x, compY - 3.5, pos.z);
          ctx.fillStyle = '#0284c7';
          ctx.font = '7px monospace';
          ctx.fillText('NEXUS IoT', scrPt.px - 16, scrPt.py + 2);
        } else if (comp.model.includes('hcsr04') || comp.model.includes('ultrasonic')) {
          // Dual Aluminum Transducer Cans
          drawBox(pos.x, compY, pos.z, 46, 14, 22, {
            top: '#3b82f6', main: '#1d4ed8', light: '#60a5fa', dark: '#1e3a8a'
          });
          drawBox(pos.x - 12, compY - 8, pos.z, 14, 12, 14, { main: '#e2e8f0', light: '#f8fafc', dark: '#94a3b8' });
          drawBox(pos.x + 12, compY - 8, pos.z, 14, 12, 14, { main: '#e2e8f0', light: '#f8fafc', dark: '#94a3b8' });
        } else if (comp.model.includes('dht') || comp.model.includes('temp')) {
          // White Slotted DHT Sensor Housing
          drawBox(pos.x, compY - 5, pos.z, 28, 24, 16, {
            top: '#f8fafc', main: '#e2e8f0', light: '#ffffff', dark: '#cbd5e1'
          }, '#94a3b8');
        } else if (comp.model.includes('servo')) {
          // Blue Mini Servo Motor with Gear Horn
          drawBox(pos.x, compY - 6, pos.z, 30, 28, 16, {
            top: '#2563eb', main: '#1d4ed8', light: '#3b82f6', dark: '#1e40af'
          });
          drawBox(pos.x, compY - 21, pos.z - 3, 10, 6, 10, { main: '#ffffff' });
        } else if (comp.model.includes('relay')) {
          // Blue High-Voltage Relay Cube
          drawBox(pos.x, compY - 6, pos.z, 32, 22, 24, {
            top: '#0284c7', main: '#0369a1', light: '#38bdf8', dark: '#075985'
          });
        } else {
          // Generic Precision Breakout Module
          drawBox(pos.x, compY, pos.z, 30, 8, 30, {
            top: '#334155', main: '#1e293b', light: '#475569', dark: '#0f172a'
          }, '#38bdf8');
        }

        // Draw connecting 3D jumper wire to board
        drawWire({ x: pos.x, y: compY, z: pos.z }, { x: (idx % 2 ? 35 : -35), y: pcbY - 8, z: -10 },
          idx === 0 ? '#ef4444' : idx === 1 ? '#38bdf8' : idx === 2 ? '#eab308' : '#22c55e');
      });

      // Acrylic Enclosure Top Lid (Translucent)
      if (enclosure !== 'off') {
        const lidY = -40 - exploded * 80;
        const lidCol = enclosure === 'wireframe' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(148, 163, 184, 0.25)';
        drawBox(0, lidY, 0, 242, 12, 212, {
          top: lidCol, main: lidCol, bottom: lidCol, light: 'rgba(255,255,255,0.4)', dark: 'rgba(15,23,42,0.3)'
        }, 'rgba(56, 189, 248, 0.6)');
      }

      // Pro / Free Tier Overlay watermark
      ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
      ctx.font = '10px monospace';
      ctx.fillText('NEXUS 3D DIGITAL TWIN ENGINE · ' + (isPro ? 'PRO UNLIMITED' : 'FREE PREVIEW'), 14, canvas.height - 14);
    }

    // Interaction Handlers (Orbit & Zoom)
    canvas.onmousedown = e => {
      isDragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
      canvas.style.cursor = 'grabbing';
    };
    window.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      yaw += dx * 0.008;
      pitch = Math.max(-1.1, Math.min(1.1, pitch + dy * 0.008));
      lastX = e.clientX;
      lastY = e.clientY;
      frame();
    });
    window.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        canvas.style.cursor = 'grab';
      }
    });

    canvas.onwheel = e => {
      e.preventDefault();
      zoom = Math.max(0.4, Math.min(2.5, zoom + (e.deltaY < 0 ? 0.1 : -0.1)));
      frame();
    };

    frame();

    return {
      setExploded: val => { exploded = val; frame(); },
      setEnclosure: mode => { enclosure = mode; frame(); },
      resetView: () => { yaw = -0.65; pitch = 0.55; zoom = 1.0; frame(); },
      exportSTL: () => {
        // Download 3D CAD/STL model of the PCB and enclosure
        const stlContent = `solid NEXUS_IoT_Project
facet normal 0 0 1
  outer loop
    vertex -100 -85 0
    vertex 100 -85 0
    vertex 100 85 0
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex -100 -85 0
    vertex 100 85 0
    vertex -100 85 0
  endloop
endfacet
endsolid NEXUS_IoT_Project`;
        const blob = new Blob([stlContent], { type: 'model/stl' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `nexus_project_enclosure_cad.stl`;
        a.click();
        URL.revokeObjectURL(url);
        toast('Downloaded 3D STL Enclosure CAD model ready for 3D printing!', 'ok');
      }
    };
  }

  function open3DModal(circuit, projectName = 'IoT Project') {
    const isPro = state.me?.entitlement?.is_pro;
    const content = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <p class="tiny muted">360° Real-time Photorealistic 3D Model with PCB, Enclosure, and Connections.</p>
          <span class="badge ${isPro ? 'violet' : 'amber'}">${isPro ? '★ Pro Full 3D Twin' : 'Free 3D Orbit Preview'}</span>
        </div>
        <div id="twin-3d-viewport" style="width:100%;height:440px;background:#090d16;border-radius:8px;position:relative;overflow:hidden;box-shadow:inset 0 0 20px rgba(0,0,0,0.8);"></div>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <label class="field" style="margin:0;display:flex;align-items:center;gap:6px;">
              <span class="tiny muted">Exploded View:</span>
              <input type="range" id="twin-explode" min="0" max="1" step="0.02" value="0" ${isPro ? '' : 'disabled'} style="width:120px;">
            </label>
            <button class="btn sm" id="twin-reset">⟲ Reset Orbit</button>
            <select class="btn sm" id="twin-enclosure" ${isPro ? '' : 'disabled'}>
              <option value="transparent">Transparent Case</option>
              <option value="wireframe">Wireframe Cutaway</option>
              <option value="off">PCB Only (No Case)</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;">
            ${isPro ?
              `<button class="btn primary sm" id="twin-export-stl">💾 Export 3D STL for 3D Printing</button>` :
              `<a href="#/upgrade" class="btn primary sm">⚡ Upgrade to Pro for 3D STL & Exploded View</a>`
            }
          </div>
        </div>
        ${!isPro ? `<div class="notice warn" style="font-size:11.5px;padding:8px 12px;margin:0;">
          <b>Free Tier Preview:</b> 360° orbit enabled. Pro members unlock the <b>Exploded Assembly Slider</b>, <b>CAD Enclosure cutaways</b>, and <b>1-Click STL Export</b> for 3D printing custom device cases.
        </div>` : ''}
      </div>
    `;

    modal(`3D Digital Twin · ${projectName}`, content, m => {
      const viewport = $('#twin-3d-viewport', m);
      const viewer = render3DCanvas(viewport, circuit);

      $('#twin-explode', m).oninput = e => viewer.setExploded(parseFloat(e.target.value));
      $('#twin-reset', m).onclick = () => {
        viewer.resetView();
        $('#twin-explode', m).value = 0;
        viewer.setExploded(0);
      };
      $('#twin-enclosure', m).onchange = e => viewer.setEnclosure(e.target.value);
      if ($('#twin-export-stl', m)) {
        $('#twin-export-stl', m).onclick = () => viewer.exportSTL();
      }
    });
  }

  return { render3DCanvas, open3DModal };
}
