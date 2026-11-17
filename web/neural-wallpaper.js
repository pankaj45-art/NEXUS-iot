/* NEXUS Realistic Photorealistic Digital Circuit Flow Wallpaper
   Authentic multi-layer dark FR4 PCB substrate, octilinear CAD traces,
   ENIG gold/copper plating, plated through-hole vias, genuine SMD footprints,
   and physical photon/electron wave-packet flow with realistic bloom. */

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
  let width = 0, height = 0, raf = 0, last = 0, dpr = 1, disposed = false;
  let traces = [], smdComponents = [], groundVias = [], testPoints = [];

  // Generate realistic high-density PCB geometry adapted to screen size
  const buildBoard = () => {
    const isMobile = width < 768;
    const cx = Math.round(width * (isMobile ? 0.5 : 0.68));
    const cy = Math.round(height * (isMobile ? 0.38 : 0.48));

    // 1. SMD Processor / FPGA (U1) dimensions
    const chipW = isMobile ? 84 : 110;
    const chipH = isMobile ? 84 : 110;

    // 2. Secondary IC (U2 - High-Speed Transceiver / Flash ROM)
    const u2W = isMobile ? 36 : 48;
    const u2H = isMobile ? 54 : 70;
    const u2X = Math.round(cx - (isMobile ? 0 : chipW * 1.8));
    const u2Y = Math.round(cy + (isMobile ? chipH * 1.5 : chipH * 0.2));

    smdComponents = [
      // Primary Processor (U1)
      { type: 'bga_chip', x: cx, y: cy, w: chipW, h: chipH, label: 'NEXUS-X86', sub: 'ARCH-ARM64', pins: isMobile ? 8 : 12 },
      // Secondary Transceiver / Memory (U2)
      { type: 'soic_chip', x: u2X, y: u2Y, w: u2W, h: u2H, label: 'U2 FLASH', pins: 8 }
    ];

    // Decoupling capacitors (0603/0805) placed near power rails
    const capOffsets = isMobile ? [
      { x: cx - chipW/2 - 14, y: cy - chipH/4, label: 'C1' },
      { x: cx + chipW/2 + 14, y: cy + chipH/4, label: 'C2' }
    ] : [
      { x: cx - chipW/2 - 16, y: cy - chipH/3, label: 'C1' },
      { x: cx - chipW/2 - 16, y: cy + chipH/3, label: 'C2' },
      { x: cx + chipW/2 + 16, y: cy - chipH/4, label: 'C3' },
      { x: cx + chipW/2 + 16, y: cy + chipH/4, label: 'C4' },
      { x: u2X + u2W/2 + 12, y: u2Y - 10, label: 'C5' }
    ];

    capOffsets.forEach(c => {
      smdComponents.push({ type: 'capacitor', x: c.x, y: c.y, w: 10, h: 5, label: c.label });
    });

    // Termination resistors (0603)
    const resOffsets = isMobile ? [
      { x: cx - 20, y: cy + chipH/2 + 18, label: 'R1' }
    ] : [
      { x: cx - 35, y: cy + chipH/2 + 20, label: 'R1' },
      { x: cx - 18, y: cy + chipH/2 + 20, label: 'R2' },
      { x: cx + 18, y: cy + chipH/2 + 20, label: 'R3' },
      { x: cx + 35, y: cy + chipH/2 + 20, label: 'R4' }
    ];

    resOffsets.forEach(r => {
      smdComponents.push({ type: 'resistor', x: r.x, y: r.y, w: 9, h: 4, label: r.label });
    });

    // Test points (gold circular annular pads)
    testPoints = isMobile ? [
      { x: cx - chipW/2 - 25, y: cy - chipH/2 - 15, label: 'TP_CLK' },
      { x: cx + chipW/2 + 25, y: cy - chipH/2 - 15, label: 'TP_TX' }
    ] : [
      { x: cx - chipW/2 - 38, y: cy - chipH/2 - 22, label: 'TP_CLK' },
      { x: cx - chipW/2 - 18, y: cy - chipH/2 - 22, label: 'TP_TX' },
      { x: cx + chipW/2 + 18, y: cy - chipH/2 - 22, label: 'TP_RX' },
      { x: cx + chipW/2 + 38, y: cy - chipH/2 - 22, label: 'TP_VCC' },
      { x: u2X - 22, y: u2Y + u2H/2 + 15, label: 'TP_GND' }
    ];

    // Ground stitching vias (matrix of micro-vias across open board areas)
    groundVias = [];
    const step = isMobile ? 90 : 75;
    for (let gx = 25; gx < width - 20; gx += step) {
      for (let gy = 25; gy < height - 20; gy += step) {
        // Keep clear of chips and high density areas
        const distU1 = Math.hypot(gx - cx, gy - cy);
        const distU2 = Math.hypot(gx - u2X, gy - u2Y);
        if (distU1 > chipW * 0.9 && distU2 > u2W * 1.2) {
          // Add small jitter for organic PCB appearance
          const jx = gx + ((gx * 17 + gy * 31) % 19) - 9;
          const jy = gy + ((gx * 23 + gy * 13) % 19) - 9;
          groundVias.push({ x: jx, y: jy });
        }
      }
    }

    // 3. Octilinear CAD Traces with true 45° chamfers & matched lengths
    traces = [];

    // Bus 1: 4-Lane High-Speed Parallel Data Bus (Cyan Photon Flow)
    const laneCount = isMobile ? 3 : 4;
    const laneSpacing = 5;
    for (let l = 0; l < laneCount; l++) {
      const off = (l - (laneCount - 1) / 2) * laneSpacing;
      const startX = 0;
      const startY = Math.round(cy - chipH * 0.65 + off);
      const jog1X = Math.round(cx * 0.35 + off);
      const jog1Y = startY;
      const jog2X = Math.round(cx * 0.35 + (cx * 0.15) + off);
      const jog2Y = Math.round(startY - (cx * 0.15));
      const midX = Math.round(cx - chipW/2 - 35 + off);
      const midY = jog2Y;
      const entryX = Math.round(cx - chipW/2 - 10);
      const entryY = Math.round(cy - chipH/4 + off * 1.5);

      traces.push({
        id: `data_bus_${l}`,
        color: '0, 229, 255',
        width: 1.3,
        speed: 0.00018,
        offset: l * 0.04, // synchronous parallel packet alignment with tiny skew
        pts: [
          [startX, startY],
          [jog1X, jog1Y],
          [jog2X, jog2Y],
          [midX, midY],
          [midX + 20, entryY],
          [entryX, entryY]
        ]
      });
    }

    // Bus 2: Differential Clock Pair with Serpentine Delay Tuning (Amber Flow)
    const clkY = Math.round(cy + chipH * 0.65);
    [-2.5, 2.5].forEach((off, i) => {
      const sy = clkY + off;
      const x1 = Math.round(cx * 0.25);
      const x2 = Math.round(cx * 0.45);
      const targetY = Math.round(cy + chipH/4 + off * 2);
      const targetX = Math.round(cx - chipW/2 - 10);

      // Octilinear routing with serpentine meander for realistic delay matching
      const pts = [
        [0, sy],
        [x1, sy],
        [x1 + 18, sy - 18],
        [x1 + 30, sy - 18],
        [x1 + 48, sy],
        [x2, sy],
        [x2 + 25, targetY],
        [targetX, targetY]
      ];

      traces.push({
        id: `clk_diff_${i}`,
        color: '245, 158, 11',
        width: 1.4,
        speed: 0.00024,
        offset: i * 0.5, // 180° complementary differential phase
        pts
      });
    });

    // Bus 3: North Memory / Expansion Bus (Cyan Flow)
    for (let l = 0; l < (isMobile ? 2 : 3); l++) {
      const off = (l - 1) * 6;
      const endX = Math.round(cx + chipW/4 + off);
      const endY = Math.round(cy - chipH/2 - 6);
      const midY = Math.round(cy - chipH/2 - 35);
      const jogX = Math.round(endX + 35);
      const topX = Math.round(jogX + 35);

      traces.push({
        id: `north_bus_${l}`,
        color: '0, 229, 255',
        width: 1.2,
        speed: 0.00020,
        offset: l * 0.07,
        pts: [
          [topX, 0],
          [topX, Math.max(20, midY - 40)],
          [jogX, midY],
          [endX, midY],
          [endX, endY]
        ]
      });
    }

    // Bus 4: East Peripheral Bus (Amber / Gold Flow)
    for (let l = 0; l < (isMobile ? 2 : 3); l++) {
      const off = (l - 1) * 6;
      const startX = Math.round(cx + chipW/2 + 6);
      const startY = Math.round(cy - chipH/4 + off * 1.5);
      const jog1X = Math.round(cx + chipW/2 + 30 + off);
      const jog1Y = startY;
      const jog2X = Math.round(jog1X + 30);
      const jog2Y = Math.round(startY + 30);
      const endX = width;
      const endY = jog2Y;

      traces.push({
        id: `east_bus_${l}`,
        color: '245, 158, 11',
        width: 1.3,
        speed: 0.00022,
        offset: l * 0.12,
        pts: [
          [startX, startY],
          [jog1X, jog1Y],
          [jog2X, jog2Y],
          [endX, endY]
        ]
      });
    }

    // Bus 5: South Inter-Chip Interconnect (Between U1 & U2)
    if (!isMobile) {
      for (let l = 0; l < 3; l++) {
        const off = (l - 1) * 5;
        const p1X = Math.round(cx - chipW/3 + off);
        const p1Y = Math.round(cy + chipH/2 + 6);
        const p2X = p1X;
        const p2Y = Math.round(cy + chipH/2 + 25);
        const p3X = Math.round(u2X + u2W/2 + 25);
        const p3Y = Math.round(u2Y - 20 + off * 4);
        const p4X = Math.round(u2X + u2W/2 + 6);
        const p4Y = p3Y;

        traces.push({
          id: `interconnect_${l}`,
          color: '0, 229, 255',
          width: 1.2,
          speed: 0.00026,
          offset: l * 0.15,
          pts: [
            [p1X, p1Y],
            [p2X, p2Y],
            [p3X + 15, p3Y - 15],
            [p3X, p3Y],
            [p4X, p4Y]
          ]
        });
      }
    }

    // Pre-calculate path lengths and segments for smooth interpolation
    traces.forEach(tr => {
      let total = 0;
      const segs = [];
      for (let p = 0; p < tr.pts.length - 1; p++) {
        const dx = tr.pts[p+1][0] - tr.pts[p][0];
        const dy = tr.pts[p+1][1] - tr.pts[p][1];
        const len = Math.hypot(dx, dy);
        segs.push({ len, dx, dy, x1: tr.pts[p][0], y1: tr.pts[p][1], x2: tr.pts[p+1][0], y2: tr.pts[p+1][1] });
        total += len;
      }
      tr.totalLen = total;
      tr.segs = segs;
    });
  };

  const resize = () => {
    const box = host.getBoundingClientRect();
    width = Math.max(1, Math.round(box.width));
    height = Math.max(1, Math.round(box.height));
    dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    buildBoard();
    draw(performance.now(), true);
  };

  const draw = (now, staticFrame = false) => {
    if (disposed) return;
    if (!staticFrame && document.hidden) { raf = 0; return; }
    if (!staticFrame && now - last < 24) { raf = requestAnimationFrame(draw); return; }
    last = now;

    ctx.clearRect(0, 0, width, height);

    // ==========================================
    // 1. REALISTIC PCB SUBSTRATE LAYER (Dark FR4)
    // ==========================================
    // Deep matte obsidian/charcoal dielectric base with subtle radial depth
    const cx = Math.round(width * (width < 768 ? 0.5 : 0.68));
    const cy = Math.round(height * (width < 768 ? 0.38 : 0.48));

    const bgGrad = ctx.createRadialGradient(cx, cy, 40, cx, cy, Math.max(width, height) * 0.85);
    bgGrad.addColorStop(0, '#060d1b');
    bgGrad.addColorStop(0.45, '#040914');
    bgGrad.addColorStop(1, '#02050a');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);

    // Micro Ground Plane Hatching (subtle copper mesh pour)
    ctx.strokeStyle = 'rgba(20, 38, 64, 0.22)';
    ctx.lineWidth = 0.5;
    const hatchStep = 36;
    ctx.beginPath();
    for (let x = 0; x <= width; x += hatchStep) {
      ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    for (let y = 0; y <= height; y += hatchStep) {
      ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    ctx.stroke();

    // ==========================================
    // 2. GROUND STITCHING VIAS (Annular Rings + Core)
    // ==========================================
    for (let v = 0; v < groundVias.length; v++) {
      const gv = groundVias[v];
      // Outer ENIG gold/copper annular ring
      ctx.strokeStyle = 'rgba(180, 142, 68, 0.28)';
      ctx.lineWidth = 0.9;
      ctx.beginPath();
      ctx.arc(gv.x, gv.y, 2.2, 0, Math.PI * 2);
      ctx.stroke();

      // Inner plated through-hole (dark drill barrel)
      ctx.fillStyle = 'rgba(2, 4, 10, 0.95)';
      ctx.beginPath();
      ctx.arc(gv.x, gv.y, 1.1, 0, Math.PI * 2);
      ctx.fill();
    }

    // ==========================================
    // 3. CONDUCTIVE OCTILINEAR TRACES (Physical Plating)
    // ==========================================
    traces.forEach(tr => {
      // Step A: Etched solder mask trench (subtle recess shadow)
      ctx.strokeStyle = 'rgba(8, 18, 32, 0.65)';
      ctx.lineWidth = tr.width + 1.6;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(tr.pts[0][0], tr.pts[0][1]);
      for (let p = 1; p < tr.pts.length; p++) ctx.lineTo(tr.pts[p][0], tr.pts[p][1]);
      ctx.stroke();

      // Step B: Metallic ENIG copper/gold trace body
      ctx.strokeStyle = 'rgba(175, 135, 65, 0.38)';
      ctx.lineWidth = tr.width;
      ctx.beginPath();
      ctx.moveTo(tr.pts[0][0], tr.pts[0][1]);
      for (let p = 1; p < tr.pts.length; p++) ctx.lineTo(tr.pts[p][0], tr.pts[p][1]);
      ctx.stroke();

      // Step C: Subtle specular centerline
      ctx.strokeStyle = 'rgba(230, 190, 110, 0.25)';
      ctx.lineWidth = tr.width * 0.4;
      ctx.stroke();

      // Step D: Plated Through-Hole Vias at corners & terminations
      for (let p = 0; p < tr.pts.length; p++) {
        const px = tr.pts[p][0], py = tr.pts[p][1];
        if (p === 0 && (px === 0 || px === width || py === 0 || py === height)) continue;

        // Copper annular ring
        ctx.strokeStyle = 'rgba(195, 155, 80, 0.45)';
        ctx.lineWidth = 1.0;
        ctx.beginPath();
        ctx.arc(px, py, 3.2, 0, Math.PI * 2);
        ctx.stroke();

        // Dark drilled hole
        ctx.fillStyle = '#02050b';
        ctx.beginPath();
        ctx.arc(px, py, 1.5, 0, Math.PI * 2);
        ctx.fill();
      }
    });

    // ==========================================
    // 4. TEST POINTS & CAD SILKSCREEN
    // ==========================================
    testPoints.forEach(tp => {
      // Annular gold test point pad
      ctx.fillStyle = 'rgba(215, 168, 72, 0.45)';
      ctx.beginPath();
      ctx.arc(tp.x, tp.y, 3.6, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = '#030712';
      ctx.beginPath();
      ctx.arc(tp.x, tp.y, 1.4, 0, Math.PI * 2);
      ctx.fill();

      // Engineering CAD silkscreen label
      ctx.fillStyle = 'rgba(148, 163, 184, 0.35)';
      ctx.font = '6px "SF Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(tp.label, tp.x, tp.y - 6);
    });

    // ==========================================
    // 5. AUTHENTIC SMD COMPONENTS & IC CHIPS
    // ==========================================
    smdComponents.forEach(cmp => {
      if (cmp.type === 'bga_chip') {
        const { x, y, w, h, pins, label, sub } = cmp;

        // Copper landing pads along perimeter
        const padW = 7, padH = 2.2;
        ctx.fillStyle = 'rgba(195, 155, 80, 0.6)';
        for (let p = 0; p < pins; p++) {
          const off = -w/2 + (p + 1) * (w / (pins + 1));
          // Top & bottom pads
          ctx.fillRect(x + off - padH/2, y - h/2 - padW + 1, padH, padW);
          ctx.fillRect(x + off - padH/2, y + h/2 - 1, padH, padW);
          // Left & right pads
          ctx.fillRect(x - w/2 - padW + 1, y + off - padH/2, padW, padH);
          ctx.fillRect(x + w/2 - 1, y + off - padH/2, padW, padH);
        }

        // Molded epoxy IC body
        ctx.fillStyle = '#0a101d';
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.28)';
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w/2, y - h/2, w, h, 6);
        else ctx.rect(x - w/2, y - h/2, w, h);
        ctx.fill();
        ctx.stroke();

        // Pin 1 Index Notch (standard IC orientation indicator)
        ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
        ctx.beginPath();
        ctx.arc(x - w/2 + 8, y - h/2 + 8, 2.2, 0, Math.PI * 2);
        ctx.fill();

        // Metallic Heat Spreader Inset
        ctx.fillStyle = '#0e1726';
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
        ctx.lineWidth = 0.8;
        const inset = 12;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w/2 + inset, y - h/2 + inset, w - inset*2, h - inset*2, 3);
        else ctx.rect(x - w/2 + inset, y - h/2 + inset, w - inset*2, h - inset*2);
        ctx.fill();
        ctx.stroke();

        // Laser-etched chip typography
        ctx.fillStyle = 'rgba(148, 163, 184, 0.6)';
        ctx.font = '700 8.5px "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 2);

        ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
        ctx.font = '6.5px "SF Mono", monospace';
        ctx.fillText(sub, x, y + 10);

        // Core Power / Micro Status LED (soft organic glow)
        const ledPulse = reduced.matches ? 0.6 : 0.45 + 0.35 * Math.sin(now * 0.003);
        ctx.fillStyle = `rgba(0, 229, 255, ${ledPulse})`;
        ctx.shadowBlur = 6 * ledPulse;
        ctx.shadowColor = '#00e5ff';
        ctx.beginPath();
        ctx.arc(x + w/2 - 12, y - h/2 + 12, 1.8, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

      } else if (cmp.type === 'soic_chip') {
        const { x, y, w, h, pins, label } = cmp;

        // Gull-wing metallic solder leads
        ctx.fillStyle = 'rgba(160, 175, 200, 0.7)';
        const leadW = 6, leadH = 2.4;
        const halfPins = pins / 2;
        for (let p = 0; p < halfPins; p++) {
          const py = y - h/2 + (p + 1) * (h / (halfPins + 1));
          ctx.fillRect(x - w/2 - leadW + 1, py - leadH/2, leadW, leadH);
          ctx.fillRect(x + w/2 - 1, py - leadH/2, leadW, leadH);
        }

        // IC body
        ctx.fillStyle = '#0c1322';
        ctx.strokeStyle = 'rgba(148, 163, 184, 0.25)';
        ctx.lineWidth = 1;
        ctx.fillRect(x - w/2, y - h/2, w, h);
        ctx.strokeRect(x - w/2, y - h/2, w, h);

        // Pin 1 dimple
        ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.beginPath();
        ctx.arc(x - w/2 + 5, y - h/2 + 5, 1.4, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = 'rgba(148, 163, 184, 0.5)';
        ctx.font = '6px "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y + 2);

      } else if (cmp.type === 'capacitor') {
        const { x, y, w, h, label } = cmp;
        // Ceramic body (brown/grey tan)
        ctx.fillStyle = '#3a342c';
        ctx.fillRect(x - w/2, y - h/2, w, h);
        // Silver solder end-caps
        ctx.fillStyle = 'rgba(180, 195, 215, 0.8)';
        ctx.fillRect(x - w/2, y - h/2, 2.5, h);
        ctx.fillRect(x + w/2 - 2.5, y - h/2, 2.5, h);
        // Silkscreen
        ctx.fillStyle = 'rgba(148, 163, 184, 0.25)';
        ctx.font = '5.5px "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 4);

      } else if (cmp.type === 'resistor') {
        const { x, y, w, h, label } = cmp;
        // Matte black body
        ctx.fillStyle = '#111620';
        ctx.fillRect(x - w/2, y - h/2, w, h);
        // Silver endcaps
        ctx.fillStyle = 'rgba(160, 175, 195, 0.75)';
        ctx.fillRect(x - w/2, y - h/2, 2, h);
        ctx.fillRect(x + w/2 - 2, y - h/2, 2, h);
        // Silkscreen
        ctx.fillStyle = 'rgba(148, 163, 184, 0.25)';
        ctx.font = '5.5px "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 4);
      }
    });

    // ==========================================
    // 6. REALISTIC DIGITAL CIRCUIT FLOW (Photons / Current)
    // ==========================================
    if (!reduced.matches) {
      traces.forEach(tr => {
        // 2 staggered packets per trace for continuous electrical rhythm
        for (let pkt = 0; pkt < 2; pkt++) {
          const tCycle = ((now * tr.speed + tr.offset + pkt * 0.5) % 1);
          const targetDist = tCycle * tr.totalLen;

          // Interpolate current position along multi-segment octilinear path
          let curDist = 0, px = tr.pts[0][0], py = tr.pts[0][1], segAngle = 0;
          for (let s = 0; s < tr.segs.length; s++) {
            const seg = tr.segs[s];
            if (curDist + seg.len >= targetDist) {
              const r = (targetDist - curDist) / seg.len;
              px = seg.x1 + seg.dx * r;
              py = seg.y1 + seg.dy * r;
              segAngle = Math.atan2(seg.dy, seg.dx);
              break;
            }
            curDist += seg.len;
          }

          // A. Photorealistic Motion Tail (exponential decay streak along trace)
          const tailLen = 28;
          ctx.save();
          ctx.lineCap = 'round';
          const tailGrad = ctx.createLinearGradient(
            px - Math.cos(segAngle) * tailLen,
            py - Math.sin(segAngle) * tailLen,
            px,
            py
          );
          tailGrad.addColorStop(0, `rgba(${tr.color}, 0)`);
          tailGrad.addColorStop(0.7, `rgba(${tr.color}, 0.25)`);
          tailGrad.addColorStop(1, `rgba(${tr.color}, 0.85)`);

          ctx.strokeStyle = tailGrad;
          ctx.lineWidth = tr.width * 1.5;
          ctx.beginPath();
          ctx.moveTo(px - Math.cos(segAngle) * tailLen, py - Math.sin(segAngle) * tailLen);
          ctx.lineTo(px, py);
          ctx.stroke();

          // B. High-Intensity White-Hot Photon Core
          ctx.shadowBlur = 10;
          ctx.shadowColor = `rgb(${tr.color})`;
          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(px, py, 1.4, 0, Math.PI * 2);
          ctx.fill();

          // C. Soft Outer Photon Bloom
          ctx.fillStyle = `rgba(${tr.color}, 0.7)`;
          ctx.shadowBlur = 16;
          ctx.beginPath();
          ctx.arc(px, py, 2.6, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }
      });
    }

    if (!staticFrame && !reduced.matches) {
      raf = requestAnimationFrame(draw);
    }
  };

  const onVisibility = () => {
    if (!document.hidden && !reduced.matches && !raf) {
      raf = requestAnimationFrame(draw);
    }
  };

  const onMotion = () => {
    cancelAnimationFrame(raf);
    raf = 0;
    if (reduced.matches) draw(performance.now(), true);
    else raf = requestAnimationFrame(draw);
  };

  const observer = new ResizeObserver(resize);
  observer.observe(host);

  document.addEventListener('visibilitychange', onVisibility);
  reduced.addEventListener?.('change', onMotion);

  resize();
  if (!reduced.matches) raf = requestAnimationFrame(draw);

  activeCleanup = () => {
    disposed = true;
    cancelAnimationFrame(raf);
    observer.disconnect();
    document.removeEventListener('visibilitychange', onVisibility);
    reduced.removeEventListener?.('change', onMotion);
  };

  return activeCleanup;
}
