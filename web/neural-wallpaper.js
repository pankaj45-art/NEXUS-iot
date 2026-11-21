/* NEXUS Live Modern Tech Cinematic TITANIUM CIRCUIT Wallpaper
   Industrial engineering aesthetics: Machined aerospace titanium chassis,
   metallic bevel-shaded conductive busbars, CNC-milled component structures,
   laser-etched CAD fiducials, and kinetic warm electrical current glow. */

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
  let traces = [], heavyBusbars = [], metallicComponents = [], groundVias = [], hexBolts = [];

  // Build the complete industrial titanium circuit geometry
  const buildBoard = () => {
    const isMobile = width < 768;
    const cx = Math.round(width * (isMobile ? 0.5 : 0.68));
    const cy = Math.round(height * (isMobile ? 0.38 : 0.48));

    // 1. Primary Titanium Processor (U1 - Industrial Core)
    const chipW = isMobile ? 88 : 116;
    const chipH = isMobile ? 88 : 116;

    // 2. High-Power Solid-State Driver / Power Conditioning Unit (U2)
    const u2W = isMobile ? 40 : 54;
    const u2H = isMobile ? 58 : 78;
    const u2X = Math.round(cx - (isMobile ? 0 : chipW * 1.9));
    const u2Y = Math.round(cy + (isMobile ? chipH * 1.55 : chipH * 0.22));

    metallicComponents = [
      {
        type: 'titanium_cpu',
        x: cx, y: cy, w: chipW, h: chipH,
        label: 'TI-CORE 6AL4V',
        sub: 'INDUSTRIAL CONTROLLER',
        pins: isMobile ? 8 : 14
      },
      {
        type: 'power_driver',
        x: u2X, y: u2Y, w: u2W, h: u2H,
        label: 'PW-800V',
        sub: 'SOLID-STATE DRIVER',
        pins: 8
      }
    ];

    // Industrial Solid Electrolytic & Ceramic Capacitors
    const capLocations = isMobile ? [
      { x: cx - chipW/2 - 16, y: cy - chipH/4, label: 'C1' },
      { x: cx + chipW/2 + 16, y: cy + chipH/4, label: 'C2' }
    ] : [
      { x: cx - chipW/2 - 18, y: cy - chipH/3, label: 'C1' },
      { x: cx - chipW/2 - 18, y: cy + chipH/3, label: 'C2' },
      { x: cx + chipW/2 + 18, y: cy - chipH/4, label: 'C3' },
      { x: cx + chipW/2 + 18, y: cy + chipH/4, label: 'C4' },
      { x: u2X + u2W/2 + 14, y: u2Y - 12, label: 'C5' },
      { x: u2X - u2W/2 - 14, y: u2Y + 14, label: 'C6' }
    ];

    capLocations.forEach(c => {
      metallicComponents.push({ type: 'capacitor', x: c.x, y: c.y, w: 12, h: 6, label: c.label });
    });

    // Precision Shunt Resistors / Current Sensors
    const resLocations = isMobile ? [
      { x: cx - 22, y: cy + chipH/2 + 20, label: 'R1' }
    ] : [
      { x: cx - 40, y: cy + chipH/2 + 22, label: 'R1' },
      { x: cx - 18, y: cy + chipH/2 + 22, label: 'R2' },
      { x: cx + 18, y: cy + chipH/2 + 22, label: 'R3' },
      { x: cx + 40, y: cy + chipH/2 + 22, label: 'R4' }
    ];

    resLocations.forEach(r => {
      metallicComponents.push({ type: 'resistor', x: r.x, y: r.y, w: 11, h: 5, label: r.label });
    });

    // CNC Hex Fasteners (Industrial Chassis Hardware)
    hexBolts = isMobile ? [
      { x: 30, y: 30 },
      { x: width - 30, y: 30 },
      { x: 30, y: height - 30 },
      { x: width - 30, y: height - 30 }
    ] : [
      { x: 40, y: 40 },
      { x: width - 40, y: 40 },
      { x: 40, y: height - 40 },
      { x: width - 40, y: height - 40 },
      { x: Math.round(cx - chipW * 1.1), y: Math.round(cy - chipH * 0.9) },
      { x: Math.round(cx + chipW * 1.1), y: Math.round(cy + chipH * 0.9) }
    ];

    // Titanium Ground Grid / Thermal Relief Vias
    groundVias = [];
    const vStep = isMobile ? 85 : 68;
    for (let gx = 30; gx < width - 25; gx += vStep) {
      for (let gy = 30; gy < height - 25; gy += vStep) {
        const d1 = Math.hypot(gx - cx, gy - cy);
        const d2 = Math.hypot(gx - u2X, gy - u2Y);
        if (d1 > chipW * 0.88 && d2 > u2W * 1.15) {
          const jx = gx + ((gx * 19 + gy * 37) % 17) - 8;
          const jy = gy + ((gx * 31 + gy * 17) % 17) - 8;
          groundVias.push({ x: jx, y: jy });
        }
      }
    }

    // Heavy Industrial Titanium Busbars (Horizontal & Vertical Mains)
    heavyBusbars = [];
    const busY1 = Math.round(cy - chipH * 0.85);
    const busY2 = Math.round(cy + chipH * 0.85);
    heavyBusbars.push({
      x1: 0, y1: busY1, x2: Math.round(cx - chipW/2 - 40), y2: busY1,
      width: 7, label: 'BUS-VCC 24V'
    });
    heavyBusbars.push({
      x1: Math.round(cx + chipW/2 + 40), y1: busY1, x2: width, y2: busY1,
      width: 7, label: 'BUS-PWR MAIN'
    });
    heavyBusbars.push({
      x1: 0, y1: busY2, x2: Math.round(cx - chipW/2 - 40), y2: busY2,
      width: 7, label: 'BUS-GND COMMON'
    });
    heavyBusbars.push({
      x1: Math.round(cx + chipW/2 + 40), y1: busY2, x2: width, y2: busY2,
      width: 7, label: 'BUS-RETURN'
    });

    // 3. Metallic Conductive Traces with Warm Electrical Flow
    traces = [];

    // Bus A: Heavy Power Phase Channels (Intense Warm Amber Glow)
    const p1Start = 0;
    const p1Y = busY1;
    const p1Jog1X = Math.round(cx * 0.32);
    const p1Jog2X = Math.round(cx * 0.32 + 25);
    const p1MidY = Math.round(cy - chipH/3);
    const p1EntryX = Math.round(cx - chipW/2 - 8);

    traces.push({
      id: 'pwr_phase_a',
      color: '255, 175, 45',     // Warm Molten Gold
      coreColor: '#fff9e6',
      width: 2.4,
      speed: 0.00022,
      offset: 0,
      glowRadius: 18,
      pts: [
        [p1Start, p1Y],
        [p1Jog1X, p1Y],
        [p1Jog2X, p1MidY],
        [p1EntryX - 25, p1MidY],
        [p1EntryX, p1MidY]
      ]
    });

    // Bus B: 4-Lane High-Frequency Data Bus (Warm Amber / Incandescent Orange Flow)
    const lanes = isMobile ? 3 : 5;
    const spacing = 6;
    for (let l = 0; l < lanes; l++) {
      const off = (l - (lanes - 1) / 2) * spacing;
      const startX = 0;
      const startY = Math.round(cy - chipH * 0.45 + off * 1.8);
      const j1X = Math.round(cx * 0.36 + off * 2);
      const j1Y = startY;
      const j2X = Math.round(j1X + 32);
      const j2Y = Math.round(startY - 32);
      const midX = Math.round(cx - chipW/2 - 38 + off);
      const midY = j2Y;
      const entryX = Math.round(cx - chipW/2 - 8);
      const entryY = Math.round(cy - chipH/5 + off * 2);

      traces.push({
        id: `data_lane_${l}`,
        color: l % 2 === 0 ? '255, 160, 30' : '255, 190, 50', // Radiant Warm Electrical Spectrum
        coreColor: '#ffffff',
        width: 1.6,
        speed: 0.00026 + l * 0.000015,
        offset: l * 0.18,
        glowRadius: 14,
        pts: [
          [startX, startY],
          [j1X, j1Y],
          [j2X, j2Y],
          [midX, midY],
          [midX + 22, entryY],
          [entryX, entryY]
        ]
      });
    }

    // Bus C: Differential Clock Lines with Meander Geometry (Warm Tungsten Arc)
    const clkBaseY = Math.round(cy + chipH * 0.55);
    [-3.5, 3.5].forEach((off, i) => {
      const sy = clkBaseY + off;
      const x1 = Math.round(cx * 0.22);
      const x2 = Math.round(cx * 0.44);
      const targetY = Math.round(cy + chipH/4 + off * 2);
      const targetX = Math.round(cx - chipW/2 - 8);

      traces.push({
        id: `clk_diff_${i}`,
        color: '255, 140, 20',    // Intense Incandescent Flame
        coreColor: '#fff5d6',
        width: 1.8,
        speed: 0.00030,
        offset: i * 0.5,
        glowRadius: 16,
        pts: [
          [0, sy],
          [x1, sy],
          [x1 + 16, sy - 16],
          [x1 + 32, sy - 16],
          [x1 + 48, sy],
          [x2, sy],
          [x2 + 24, targetY],
          [targetX, targetY]
        ]
      });
    });

    // Bus D: East Peripheral Conduits (Warm Golden Radiance)
    const eLanes = isMobile ? 2 : 4;
    for (let l = 0; l < eLanes; l++) {
      const off = (l - 1.5) * 7;
      const startX = Math.round(cx + chipW/2 + 8);
      const startY = Math.round(cy - chipH/4 + off * 2);
      const j1X = Math.round(cx + chipW/2 + 36 + off * 2);
      const j1Y = startY;
      const j2X = Math.round(j1X + 35);
      const j2Y = Math.round(startY + 35);
      const endX = width;
      const endY = j2Y;

      traces.push({
        id: `east_conduit_${l}`,
        color: '255, 185, 40',   // Warm Metallic Gold Flow
        coreColor: '#ffffff',
        width: 1.7,
        speed: 0.00024 + l * 0.00002,
        offset: l * 0.22,
        glowRadius: 15,
        pts: [
          [startX, startY],
          [j1X, j1Y],
          [j2X, j2Y],
          [endX, endY]
        ]
      });
    }

    // Bus E: North High-Voltage Expansion Lines (Molten Copper-Amber)
    const nLanes = isMobile ? 2 : 3;
    for (let l = 0; l < nLanes; l++) {
      const off = (l - 1) * 8;
      const endX = Math.round(cx + chipW/4 + off);
      const endY = Math.round(cy - chipH/2 - 8);
      const midY = Math.round(cy - chipH/2 - 42);
      const jX = Math.round(endX + 38);
      const topX = Math.round(jX + 38);

      traces.push({
        id: `north_rail_${l}`,
        color: '255, 165, 35',
        coreColor: '#fffdf5',
        width: 1.6,
        speed: 0.00021 + l * 0.00003,
        offset: l * 0.14,
        glowRadius: 14,
        pts: [
          [topX, 0],
          [topX, Math.max(25, midY - 45)],
          [jX, midY],
          [endX, midY],
          [endX, endY]
        ]
      });
    }

    // Bus F: Inter-Chip Industrial Bus (Connecting Controller to Solid-State Driver)
    if (!isMobile) {
      for (let l = 0; l < 3; l++) {
        const off = (l - 1) * 6;
        const p1X = Math.round(cx - chipW/3 + off);
        const p1Y = Math.round(cy + chipH/2 + 8);
        const p2X = p1X;
        const p2Y = Math.round(cy + chipH/2 + 30);
        const p3X = Math.round(u2X + u2W/2 + 28);
        const p3Y = Math.round(u2Y - 22 + off * 5);
        const p4X = Math.round(u2X + u2W/2 + 8);
        const p4Y = p3Y;

        traces.push({
          id: `interchip_${l}`,
          color: '255, 150, 25',  // High-Energy Warm Amber
          coreColor: '#ffffff',
          width: 1.5,
          speed: 0.00028,
          offset: l * 0.19,
          glowRadius: 16,
          pts: [
            [p1X, p1Y],
            [p2X, p2Y],
            [p3X + 18, p3Y - 18],
            [p3X, p3Y],
            [p4X, p4Y]
          ]
        });
      }
    }

    // Pre-calculate path lengths and segments for buttery 60fps interpolation
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

  // Main Render Loop
  const draw = (now, staticFrame = false) => {
    if (disposed) return;
    if (!staticFrame && document.hidden) { raf = 0; return; }
    if (!staticFrame && now - last < 22) { raf = requestAnimationFrame(draw); return; }
    last = now;

    ctx.clearRect(0, 0, width, height);

    const isMobile = width < 768;
    const cx = Math.round(width * (isMobile ? 0.5 : 0.68));
    const cy = Math.round(height * (isMobile ? 0.38 : 0.48));

    // ========================================================
    // 1. INDUSTRIAL TITANIUM SUBSTRATE (AEROSPACE CHASSIS)
    // ========================================================
    // Radial titanium illumination: Deep carbon-titanium gradient
    const bgGrad = ctx.createRadialGradient(cx, cy, 50, cx, cy, Math.max(width, height) * 0.9);
    bgGrad.addColorStop(0, '#0d131f');     // Anodized dark titanium center
    bgGrad.addColorStop(0.35, '#090e18');  // Brushed metallic slate
    bgGrad.addColorStop(0.75, '#050810');  // Industrial obsidian edge
    bgGrad.addColorStop(1, '#020408');     // Absolute edge depth
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);

    // Milled Industrial Precision Grid (Diagonal & Orthogonal Hatch)
    ctx.lineWidth = 0.5;
    ctx.strokeStyle = 'rgba(75, 95, 125, 0.12)';
    const gStep = 40;
    ctx.beginPath();
    for (let x = 0; x <= width; x += gStep) {
      ctx.moveTo(x, 0); ctx.lineTo(x, height);
    }
    for (let y = 0; y <= height; y += gStep) {
      ctx.moveTo(0, y); ctx.lineTo(width, y);
    }
    ctx.stroke();

    // Subtle 45° CNC Milled Tool-path Texture
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.04)';
    ctx.lineWidth = 0.6;
    ctx.beginPath();
    const dStep = 90;
    for (let d = -height; d <= width + height; d += dStep) {
      ctx.moveTo(d, 0);
      ctx.lineTo(d + height, height);
    }
    ctx.stroke();

    // ========================================================
    // 2. CNC HEX BOLTS & STRUCTURAL FASTENERS
    // ========================================================
    hexBolts.forEach(bolt => {
      // Outer counter-bored socket ring
      ctx.strokeStyle = 'rgba(140, 160, 185, 0.35)';
      ctx.lineWidth = 1.2;
      ctx.fillStyle = '#060a12';
      ctx.beginPath();
      ctx.arc(bolt.x, bolt.y, 6.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      // Inner Allen Hex Socket
      ctx.fillStyle = 'rgba(80, 100, 125, 0.5)';
      ctx.beginPath();
      for (let a = 0; a < 6; a++) {
        const rad = (a * Math.PI) / 3;
        const hx = bolt.x + 3.2 * Math.cos(rad);
        const hy = bolt.y + 3.2 * Math.sin(rad);
        if (a === 0) ctx.moveTo(hx, hy);
        else ctx.lineTo(hx, hy);
      }
      ctx.closePath();
      ctx.fill();
    });

    // ========================================================
    // 3. HEAVY TITANIUM BUSBARS WITH METALLIC BEVEL
    // ========================================================
    heavyBusbars.forEach(bus => {
      // Sunk relief channel (machined groove shadow)
      ctx.strokeStyle = 'rgba(0, 0, 0, 0.7)';
      ctx.lineWidth = bus.width + 3;
      ctx.lineCap = 'butt';
      ctx.beginPath();
      ctx.moveTo(bus.x1, bus.y1); ctx.lineTo(bus.x2, bus.y2);
      ctx.stroke();

      // Machined Titanium Body
      const tGrad = ctx.createLinearGradient(bus.x1, bus.y1 - bus.width/2, bus.x1, bus.y1 + bus.width/2);
      tGrad.addColorStop(0, '#53657d');    // Metallic top reflection
      tGrad.addColorStop(0.3, '#323d4f');  // Titanium body
      tGrad.addColorStop(0.7, '#1e2634');  // Lower shadow
      tGrad.addColorStop(1, '#111722');    // Bevel trough
      ctx.strokeStyle = tGrad;
      ctx.lineWidth = bus.width;
      ctx.beginPath();
      ctx.moveTo(bus.x1, bus.y1); ctx.lineTo(bus.x2, bus.y2);
      ctx.stroke();

      // Top specular highlight edge
      ctx.strokeStyle = 'rgba(215, 230, 255, 0.3)';
      ctx.lineWidth = 0.8;
      ctx.beginPath();
      ctx.moveTo(bus.x1, bus.y1 - bus.width/2 + 0.5);
      ctx.lineTo(bus.x2, bus.y2 - bus.width/2 + 0.5);
      ctx.stroke();

      // Laser-etched CAD Label
      if (Math.abs(bus.x2 - bus.x1) > 120) {
        ctx.fillStyle = 'rgba(180, 195, 215, 0.35)';
        ctx.font = '700 6.5px "JetBrains Mono", "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(bus.label, (bus.x1 + bus.x2) / 2, bus.y1 + 2);
      }
    });

    // ========================================================
    // 4. THERMAL GROUND VIAS (TITANIUM + GOLD CORE)
    // ========================================================
    for (let v = 0; v < groundVias.length; v++) {
      const gv = groundVias[v];
      // Outer titanium annular ring
      ctx.strokeStyle = 'rgba(120, 140, 165, 0.3)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(gv.x, gv.y, 2.5, 0, Math.PI * 2);
      ctx.stroke();

      // Gold conductive barrel rim
      ctx.strokeStyle = 'rgba(245, 175, 55, 0.45)';
      ctx.lineWidth = 0.6;
      ctx.beginPath();
      ctx.arc(gv.x, gv.y, 1.6, 0, Math.PI * 2);
      ctx.stroke();

      // Drilled dark core
      ctx.fillStyle = '#020408';
      ctx.beginPath();
      ctx.arc(gv.x, gv.y, 0.9, 0, Math.PI * 2);
      ctx.fill();
    }

    // ========================================================
    // 5. CONDUCTIVE METALLIC TRACES & PHYSICAL PINS
    // ========================================================
    traces.forEach(tr => {
      // A. Milled isolation channel shadow
      ctx.strokeStyle = 'rgba(2, 5, 10, 0.8)';
      ctx.lineWidth = tr.width + 2;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      ctx.moveTo(tr.pts[0][0], tr.pts[0][1]);
      for (let p = 1; p < tr.pts.length; p++) ctx.lineTo(tr.pts[p][0], tr.pts[p][1]);
      ctx.stroke();

      // B. Metallic Titanium / Copper Alloy Trace Body
      ctx.strokeStyle = 'rgba(145, 160, 180, 0.45)';
      ctx.lineWidth = tr.width;
      ctx.beginPath();
      ctx.moveTo(tr.pts[0][0], tr.pts[0][1]);
      for (let p = 1; p < tr.pts.length; p++) ctx.lineTo(tr.pts[p][0], tr.pts[p][1]);
      ctx.stroke();

      // C. Specular metal centerline highlight
      ctx.strokeStyle = 'rgba(225, 235, 250, 0.35)';
      ctx.lineWidth = tr.width * 0.4;
      ctx.stroke();

      // D. Annular pads & through-hole vias at junction vertices
      for (let p = 0; p < tr.pts.length; p++) {
        const px = tr.pts[p][0], py = tr.pts[p][1];
        if (p === 0 && (px === 0 || px === width || py === 0 || py === height)) continue;

        ctx.strokeStyle = 'rgba(170, 185, 205, 0.55)';
        ctx.lineWidth = 1.1;
        ctx.beginPath();
        ctx.arc(px, py, 3.4, 0, Math.PI * 2);
        ctx.stroke();

        ctx.fillStyle = '#03060c';
        ctx.beginPath();
        ctx.arc(px, py, 1.6, 0, Math.PI * 2);
        ctx.fill();
      }
    });

    // ========================================================
    // 6. INDUSTRIAL METALLIC HARDWARE & CHIP PACKAGES
    // ========================================================
    metallicComponents.forEach(cmp => {
      if (cmp.type === 'titanium_cpu') {
        const { x, y, w, h, pins, label, sub } = cmp;

        // Gold/Titanium Lead Pins along perimeter
        const pinLen = 8, pinThick = 2.4;
        ctx.fillStyle = 'rgba(225, 175, 75, 0.75)';
        for (let p = 0; p < pins; p++) {
          const off = -w/2 + (p + 1) * (w / (pins + 1));
          // Top & bottom leads
          ctx.fillRect(x + off - pinThick/2, y - h/2 - pinLen + 1, pinThick, pinLen);
          ctx.fillRect(x + off - pinThick/2, y + h/2 - 1, pinThick, pinLen);
          // Left & right leads
          ctx.fillRect(x - w/2 - pinLen + 1, y + off - pinThick/2, pinLen, pinThick);
          ctx.fillRect(x + w/2 - 1, y + off - pinThick/2, pinLen, pinThick);
        }

        // Heavy Machined Titanium IC Case
        ctx.fillStyle = '#0a101b';
        ctx.strokeStyle = 'rgba(100, 125, 155, 0.5)';
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w/2, y - h/2, w, h, 6);
        else ctx.rect(x - w/2, y - h/2, w, h);
        ctx.fill();
        ctx.stroke();

        // Brushed Titanium Integrated Heat Spreader (IHS)
        const ihsInset = 11;
        const ihsGrad = ctx.createLinearGradient(x - w/2 + ihsInset, y - h/2 + ihsInset, x + w/2 - ihsInset, y + h/2 - ihsInset);
        ihsGrad.addColorStop(0, '#2c3749');
        ihsGrad.addColorStop(0.3, '#192231');
        ihsGrad.addColorStop(0.7, '#131a26');
        ihsGrad.addColorStop(1, '#0e141f');
        ctx.fillStyle = ihsGrad;
        ctx.strokeStyle = 'rgba(190, 210, 235, 0.25)';
        ctx.lineWidth = 0.9;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(x - w/2 + ihsInset, y - h/2 + ihsInset, w - ihsInset*2, h - ihsInset*2, 3);
        else ctx.rect(x - w/2 + ihsInset, y - h/2 + ihsInset, w - ihsInset*2, h - ihsInset*2);
        ctx.fill();
        ctx.stroke();

        // Pin 1 Gold Index Dimple
        ctx.fillStyle = 'rgba(255, 195, 65, 0.75)';
        ctx.beginPath();
        ctx.arc(x - w/2 + 8, y - h/2 + 8, 2.2, 0, Math.PI * 2);
        ctx.fill();

        // Laser-etched Industrial Markings
        ctx.fillStyle = 'rgba(215, 230, 250, 0.75)';
        ctx.font = '700 9px "JetBrains Mono", "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 4);

        ctx.fillStyle = 'rgba(245, 165, 55, 0.65)'; // Warm Amber Subtitle
        ctx.font = '600 6.5px "JetBrains Mono", "SF Mono", monospace';
        ctx.fillText(sub, x, y + 10);

        // Core Status Incandescent Warm Glow Beacon
        const warmBreath = reduced.matches ? 0.7 : 0.55 + 0.45 * Math.sin(now * 0.0028);
        ctx.fillStyle = `rgba(255, 170, 40, ${warmBreath})`;
        ctx.shadowBlur = 12 * warmBreath;
        ctx.shadowColor = 'rgba(255, 150, 20, 0.9)';
        ctx.beginPath();
        ctx.arc(x + w/2 - 12, y - h/2 + 12, 2.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

      } else if (cmp.type === 'power_driver') {
        const { x, y, w, h, pins, label, sub } = cmp;

        // Solid-state metallic solder tabs
        ctx.fillStyle = 'rgba(190, 205, 225, 0.75)';
        const tabW = 6, tabH = 2.6;
        const half = pins / 2;
        for (let p = 0; p < half; p++) {
          const py = y - h/2 + (p + 1) * (h / (half + 1));
          ctx.fillRect(x - w/2 - tabW + 1, py - tabH/2, tabW, tabH);
          ctx.fillRect(x + w/2 - 1, py - tabH/2, tabW, tabH);
        }

        // Ceramic / Metal driver body
        ctx.fillStyle = '#0b111d';
        ctx.strokeStyle = 'rgba(120, 145, 175, 0.35)';
        ctx.lineWidth = 1;
        ctx.fillRect(x - w/2, y - h/2, w, h);
        ctx.strokeRect(x - w/2, y - h/2, w, h);

        ctx.fillStyle = 'rgba(200, 215, 235, 0.7)';
        ctx.font = '700 7px "JetBrains Mono", "SF Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 2);

        ctx.fillStyle = 'rgba(245, 160, 40, 0.55)';
        ctx.font = '5.5px "JetBrains Mono", monospace';
        ctx.fillText(sub, x, y + 9);

        // Warm power rail indicator
        const pwrGlow = reduced.matches ? 0.6 : 0.5 + 0.35 * Math.cos(now * 0.0035);
        ctx.fillStyle = `rgba(255, 160, 30, ${pwrGlow})`;
        ctx.shadowBlur = 8 * pwrGlow;
        ctx.shadowColor = '#ff9900';
        ctx.beginPath();
        ctx.arc(x - w/2 + 5, y - h/2 + 5, 1.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.shadowBlur = 0;

      } else if (cmp.type === 'capacitor') {
        const { x, y, w, h, label } = cmp;
        // Titanium/Tantalum Capacitor Body
        ctx.fillStyle = '#262f3d';
        ctx.fillRect(x - w/2, y - h/2, w, h);
        // Polished Metallic Solder End-caps
        ctx.fillStyle = 'rgba(205, 220, 240, 0.85)';
        ctx.fillRect(x - w/2, y - h/2, 2.8, h);
        ctx.fillRect(x + w/2 - 2.8, y - h/2, 2.8, h);
        // Laser Text
        ctx.fillStyle = 'rgba(160, 175, 195, 0.4)';
        ctx.font = '5.5px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 5);

      } else if (cmp.type === 'resistor') {
        const { x, y, w, h, label } = cmp;
        ctx.fillStyle = '#111722';
        ctx.fillRect(x - w/2, y - h/2, w, h);
        ctx.fillStyle = 'rgba(180, 200, 225, 0.8)';
        ctx.fillRect(x - w/2, y - h/2, 2.2, h);
        ctx.fillRect(x + w/2 - 2.2, y - h/2, 2.2, h);
        ctx.fillStyle = 'rgba(160, 175, 195, 0.4)';
        ctx.font = '5.5px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.fillText(label, x, y - 5);
      }
    });

    // ========================================================
    // 7. WARM ELECTRICAL GLOW (INCANDESCENT PLASMA CURRENT)
    // ========================================================
    if (!reduced.matches) {
      traces.forEach(tr => {
        // 2 staggered warm electrical packets per trace for continuous cinematic flow
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

          ctx.save();

          // A. Cinematic Exponential Decay Motion Tail (Warm Electrical Arc)
          const tailLen = 34;
          const xTail = px - Math.cos(segAngle) * tailLen;
          const yTail = py - Math.sin(segAngle) * tailLen;
          const tailGrad = ctx.createLinearGradient(xTail, yTail, px, py);
          tailGrad.addColorStop(0, `rgba(${tr.color}, 0)`);
          tailGrad.addColorStop(0.5, `rgba(${tr.color}, 0.35)`);
          tailGrad.addColorStop(0.85, `rgba(${tr.color}, 0.75)`);
          tailGrad.addColorStop(1, `rgba(${tr.color}, 0.95)`);

          ctx.strokeStyle = tailGrad;
          ctx.lineWidth = tr.width * 1.8;
          ctx.lineCap = 'round';
          ctx.beginPath();
          ctx.moveTo(xTail, yTail);
          ctx.lineTo(px, py);
          ctx.stroke();

          // B. Outer Radiant Warm Electrical Bloom Halo
          ctx.fillStyle = `rgba(${tr.color}, 0.45)`;
          ctx.shadowBlur = tr.glowRadius * 1.4;
          ctx.shadowColor = `rgb(${tr.color})`;
          ctx.beginPath();
          ctx.arc(px, py, 3.4, 0, Math.PI * 2);
          ctx.fill();

          // C. Inner Luminous Incandescent Plasma Core
          ctx.fillStyle = `rgba(${tr.color}, 0.85)`;
          ctx.shadowBlur = 8;
          ctx.shadowColor = '#ffb300';
          ctx.beginPath();
          ctx.arc(px, py, 2.1, 0, Math.PI * 2);
          ctx.fill();

          // D. Ultra White-Hot Center
          ctx.fillStyle = tr.coreColor || '#ffffff';
          ctx.beginPath();
          ctx.arc(px, py, 1.2, 0, Math.PI * 2);
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
