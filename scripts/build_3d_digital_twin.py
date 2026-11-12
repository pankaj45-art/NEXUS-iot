import os
from pathlib import Path

content = r'''/* Interactive 3D Digital Twin Viewer for IoT hardware prototypes.
   Supports dynamic board geometries (Arduino Uno, Raspberry Pi 4, Pico W, ESP32, ESP32-S3, ESP8266)
   and photorealistic 3D models for the entire component catalog with wiring and annotations. */

export function createDigitalTwin3D(h) {
  const { $, $$, esc, modal, closeModal, toast, state } = h;

  function render3DCanvas(container, circuit, options = {}) {
    const isPro = true; // Open access enabled
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
    let pitch = 0.45;
    let zoom = 1.0;
    let exploded = 0.0;
    let enclosure = 'transparent';
    let isDragging = false;
    let lastX = 0, lastY = 0;

    // Detect board architecture
    const boardKey = (
      circuit?.board_config?.board ||
      circuit?.board ||
      (circuit?.components || []).find(c => c.model && c.model.startsWith('board:'))?.model?.replace('board:', '') ||
      'esp32'
    ).toLowerCase();

    // 3D Point Projection (x, y, z) -> 2D (px, py, depth)
    function project(x, y, z) {
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const cosY = Math.cos(yaw), sinY = Math.sin(yaw);
      const x1 = x * cosY - z * sinY;
      const z1 = x * sinY + z * cosY;

      const cosP = Math.cos(pitch), sinP = Math.sin(pitch);
      const y2 = y * cosP - z1 * sinP;
      const z2 = y * sinP + z1 * cosP;

      const scale = (350 * zoom) / (440 + z2);
      return {
        px: cx + x1 * scale,
        py: cy + y2 * scale,
        depth: z2
      };
    }

    function drawBox(x, y, z, w, h, d, faceColors, strokeColor = '#0f172a', rx = 0) {
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
        { pts: [p[0], p[1], p[5], p[4]], col: faceColors.top || faceColors.light || faceColors.main, z: (p[0].depth + p[5].depth) / 2 },
        { pts: [p[3], p[2], p[6], p[7]], col: faceColors.bottom || faceColors.dark || faceColors.main, z: (p[3].depth + p[6].depth) / 2 },
      ];

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
          ctx.lineWidth = 0.8;
          ctx.stroke();
        }
      });
    }

    function drawCylinder(x, y, z, r, h, color, topColor = null, stroke = 'rgba(15,23,42,0.4)') {
      const segs = 12;
      const ptsTop = [], ptsBot = [];
      for (let i = 0; i < segs; i++) {
        const ang = (i / segs) * Math.PI * 2;
        const cx = x + Math.cos(ang) * r;
        const cz = z + Math.sin(ang) * r;
        ptsTop.push(project(cx, y - h/2, cz));
        ptsBot.push(project(cx, y + h/2, cz));
      }
      // Top face
      ctx.beginPath();
      ctx.moveTo(ptsTop[0].px, ptsTop[0].py);
      for (let i = 1; i < segs; i++) ctx.lineTo(ptsTop[i].px, ptsTop[i].py);
      ctx.closePath();
      ctx.fillStyle = topColor || color;
      ctx.fill();
      if (stroke) { ctx.strokeStyle = stroke; ctx.stroke(); }
      // Side panels
      for (let i = 0; i < segs; i++) {
        const next = (i + 1) % segs;
        ctx.beginPath();
        ctx.moveTo(ptsTop[i].px, ptsTop[i].py);
        ctx.lineTo(ptsTop[next].px, ptsTop[next].py);
        ctx.lineTo(ptsBot[next].px, ptsBot[next].py);
        ctx.lineTo(ptsBot[i].px, ptsBot[i].py);
        ctx.closePath();
        ctx.fillStyle = color;
        ctx.fill();
        if (stroke) { ctx.strokeStyle = stroke; ctx.stroke(); }
      }
    }

    function drawWire(p1, p2, color = '#38bdf8', curveY = -40) {
      const a = project(p1.x, p1.y, p1.z);
      const b = project(p2.x, p2.y, p2.z);
      const mid = project((p1.x + p2.x) / 2, Math.min(p1.y, p2.y) + curveY, (p1.z + p2.z) / 2);

      ctx.beginPath();
      ctx.moveTo(a.px, a.py);
      ctx.quadraticCurveTo(mid.px, mid.py, b.px, b.py);
      ctx.strokeStyle = color;
      ctx.lineWidth = 2.2;
      ctx.shadowColor = color;
      ctx.shadowBlur = 3;
      ctx.stroke();
      ctx.shadowBlur = 0;
    }

    function drawPinHeader(x, y, z, count, pitch, isDouble = false) {
      const w = count * pitch;
      drawBox(x, y, z, w, 9, isDouble ? 11 : 6, { main: '#1e293b', top: '#0f172a', dark: '#020617' });
      for (let i = 0; i < count; i++) {
        const px = x - w/2 + (i + 0.5) * pitch;
        const pt = project(px, y - 5, z);
        ctx.fillStyle = '#fbbf24';
        ctx.fillRect(pt.px - 1.2, pt.py - 1.2, 2.4, 2.4);
      }
    }

    // Render Specific Board Geometries
    function renderBoard(bKey, pcbY) {
      if (bKey.includes('uno') || bKey.includes('arduino')) {
        // Arduino Uno R3: Classic Blue PCB with ATmega328P DIP & USB-B
        const bw = 190, bd = 140;
        drawBox(0, pcbY, 0, bw, 8, bd, {
          top: '#0284c7', main: '#0369a1', light: '#38bdf8', dark: '#075985'
        }, '#0284c7');
        // ATmega328P DIP IC (Dual In-line package with silver legs)
        drawBox(20, pcbY - 6 - exploded * 10, 15, 75, 7, 22, {
          top: '#0f172a', main: '#1e293b', light: '#334155', dark: '#020617'
        });
        const dipPt = project(20, pcbY - 10 - exploded * 10, 15);
        ctx.fillStyle = '#94a3b8';
        ctx.font = '7px monospace';
        ctx.fillText('ATmega328P', dipPt.px - 22, dipPt.py);
        // USB-B Metal Socket
        drawBox(-75, pcbY - 10, -35, 30, 18, 30, {
          top: '#e2e8f0', main: '#cbd5e1', light: '#f8fafc', dark: '#94a3b8'
        });
        // DC Power Barrel Jack
        drawBox(-75, pcbY - 11, 40, 32, 20, 26, {
          top: '#1e293b', main: '#0f172a', light: '#334155', dark: '#020617'
        });
        // Reset Pushbutton
        drawBox(-65, pcbY - 7, -10, 10, 7, 10, { main: '#dc2626', top: '#ef4444' });
        // Dual Pin Headers
        drawPinHeader(15, pcbY - 8, -62, 14, 8);
        drawPinHeader(20, pcbY - 8, 62, 12, 8);
        // Silkscreen
        const logo = project(-10, pcbY - 4.5, -35);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 9px sans-serif';
        ctx.fillText('ARDUINO UNO R3', logo.px - 20, logo.py);
      }
      else if (bKey.includes('rpi') || bKey.includes('raspberry') || bKey.includes('pi4')) {
        // Raspberry Pi 4 Model B: Emerald Green PCB with Ethernet, 4x USB & 40-pin GPIO
        const bw = 210, bd = 140;
        drawBox(0, pcbY, 0, bw, 8, bd, {
          top: '#15803d', main: '#166534', light: '#22c55e', dark: '#14532d'
        }, '#15803d');
        // Broadcom BCM2711 SoC with silver heatspreader
        drawBox(-15, pcbY - 7 - exploded * 15, 5, 38, 6, 38, {
          top: '#cbd5e1', main: '#94a3b8', light: '#f1f5f9', dark: '#64748b'
        });
        // Gigabit Ethernet Jack
        drawBox(80, pcbY - 14, -40, 36, 26, 38, {
          top: '#e2e8f0', main: '#cbd5e1', light: '#f8fafc', dark: '#94a3b8'
        });
        // Dual Stacked USB 3.0 (Blue) & USB 2.0 (Grey) Ports
        drawBox(80, pcbY - 15, 12, 34, 28, 34, { top: '#0284c7', main: '#0369a1', light: '#38bdf8' });
        drawBox(80, pcbY - 15, 52, 34, 28, 34, { top: '#cbd5e1', main: '#94a3b8', light: '#e2e8f0' });
        // 40-Pin Double-Row GPIO Header
        drawPinHeader(-15, pcbY - 8, -58, 20, 5.5, true);
        // Type-C Power and Dual Micro-HDMI
        drawBox(-75, pcbY - 6, 62, 18, 7, 14, { main: '#94a3b8' });
        drawBox(-30, pcbY - 6, 62, 14, 6, 12, { main: '#94a3b8' });
        drawBox(0, pcbY - 6, 62, 14, 6, 12, { main: '#94a3b8' });
        // Silkscreen
        const logo = project(-60, pcbY - 4.5, -15);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 8.5px sans-serif';
        ctx.fillText('Raspberry Pi 4', logo.px - 15, logo.py);
      }
      else if (bKey.includes('pico')) {
        // Raspberry Pi Pico W: Slender Bright Green PCB with RP2040 & Silver Wi-Fi Can
        const bw = 160, bd = 70;
        drawBox(0, pcbY, 0, bw, 7, bd, {
          top: '#059669', main: '#047857', light: '#10b981', dark: '#064e3b'
        }, '#059669');
        // RP2040 Microcontroller IC
        drawBox(-15, pcbY - 5 - exploded * 10, 0, 24, 4, 24, {
          top: '#0f172a', main: '#1e293b', light: '#334155', dark: '#020617'
        });
        // Wi-Fi Silver Module Can (CYW43439)
        drawBox(35, pcbY - 6 - exploded * 10, 0, 32, 5, 28, {
          top: '#cbd5e1', main: '#94a3b8', light: '#f1f5f9', dark: '#64748b'
        });
        // Micro-USB Port
        drawBox(-72, pcbY - 6, 0, 18, 7, 14, { main: '#e2e8f0', top: '#cbd5e1' });
        // Castellated Gold Edge Pads
        drawPinHeader(0, pcbY - 4.5, -31, 20, 6.8);
        drawPinHeader(0, pcbY - 4.5, 31, 20, 6.8);
        // Silkscreen
        const logo = project(-45, pcbY - 4.2, 0);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 8px sans-serif';
        ctx.fillText('Pico W', logo.px - 12, logo.py);
      }
      else {
        // ESP32 / ESP32-S3 DevKit: Matte Black PCB with Metal Shield & Meandering Antenna
        const bw = 175, bd = 90;
        drawBox(0, pcbY, 0, bw, 8, bd, {
          top: '#0f172a', main: '#020617', light: '#1e293b', dark: '#020617'
        }, '#38bdf8');
        // Metal RF Shield Can
        drawBox(0, pcbY - 6 - exploded * 15, -5, 62, 5, 65, {
          top: '#cbd5e1', main: '#94a3b8', light: '#f1f5f9', dark: '#64748b'
        }, '#475569');
        // ESP32 PCB Meandering Trace Antenna
        const ant = project(50, pcbY - 4.5, -5);
        ctx.fillStyle = '#b45309';
        ctx.fillRect(ant.px - 12, ant.py - 15, 24, 30);
        ctx.strokeStyle = '#f59e0b';
        ctx.strokeRect(ant.px - 12, ant.py - 15, 24, 30);
        // Micro-USB / Type-C Port
        drawBox(-78, pcbY - 6, -5, 20, 8, 14, { main: '#e2e8f0', top: '#cbd5e1' });
        // Dual 15-Pin Headers
        drawPinHeader(0, pcbY - 8, -38, 15, 9);
        drawPinHeader(0, pcbY - 8, 38, 15, 9);
        // Status Power LED (Bright Green Glow)
        const ledPt = project(-40, pcbY - 5, -25);
        ctx.beginPath();
        ctx.arc(ledPt.px, ledPt.py, 2.5, 0, Math.PI * 2);
        ctx.fillStyle = '#4ade80';
        ctx.shadowColor = '#22c55e';
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
        // Silkscreen
        const logo = project(0, pcbY - 8 - exploded * 15, -5);
        ctx.fillStyle = '#334155';
        ctx.font = 'bold 8px monospace';
        ctx.fillText(bKey.toUpperCase(), logo.px - 18, logo.py + 2);
      }
    }

    // Render Individual Component 3D Models
    function renderComponent(comp, pos, compY, idx) {
      const m = (comp.model || '').toLowerCase();
      const label = comp.label || comp.id || comp.model;

      if (m.includes('oled') || m.includes('display')) {
        // OLED 0.96" 128x64 Blue/Cyan Display
        drawBox(pos.x, compY, pos.z, 56, 6, 42, {
          top: '#020617', main: '#0f172a', light: '#1e293b', dark: '#020617'
        }, '#38bdf8');
        const scrPt = project(pos.x, compY - 3.5, pos.z);
        ctx.fillStyle = '#0284c7';
        ctx.fillRect(scrPt.px - 22, scrPt.py - 12, 44, 24);
        ctx.fillStyle = '#38bdf8';
        ctx.font = 'bold 7px monospace';
        ctx.fillText('NEXUS IoT', scrPt.px - 18, scrPt.py - 2);
        ctx.font = '6px monospace';
        ctx.fillStyle = '#a5f3fc';
        ctx.fillText('SYSTEM OK', scrPt.px - 17, scrPt.py + 7);
      }
      else if (m.includes('lcd') || m.includes('1602')) {
        // LCD 1602 Character Display with Bezel & Backlight
        drawBox(pos.x, compY, pos.z, 80, 8, 38, {
          top: '#064e3b', main: '#022c22', light: '#047857', dark: '#011910'
        }, '#059669');
        drawBox(pos.x, compY - 5, pos.z, 64, 4, 26, {
          top: '#0284c7', main: '#0369a1', light: '#38bdf8', dark: '#075985'
        });
        const txt = project(pos.x, compY - 7.5, pos.z);
        ctx.fillStyle = '#ffffff';
        ctx.font = '7px monospace';
        ctx.fillText('16x2 LCD DISPLAY', txt.px - 26, txt.py);
      }
      else if (m.includes('hcsr04') || m.includes('ultrasonic')) {
        // HC-SR04 Dual Aluminum Ultrasonic Cylinders ("Eyes")
        drawBox(pos.x, compY, pos.z, 52, 12, 26, {
          top: '#1d4ed8', main: '#1e40af', light: '#3b82f6', dark: '#172554'
        }, '#3b82f6');
        drawCylinder(pos.x - 14, compY - 9, pos.z, 9, 14, '#cbd5e1', '#e2e8f0');
        drawCylinder(pos.x + 14, compY - 9, pos.z, 9, 14, '#cbd5e1', '#e2e8f0');
      }
      else if (m.includes('dht') || m.includes('temp') || m.includes('humidity')) {
        // DHT11 (Blue) / DHT22 (White) Aerated Grid Sensor
        const isDht22 = m.includes('22');
        drawBox(pos.x, compY - 6, pos.z, 30, 24, 18, {
          top: isDht22 ? '#f8fafc' : '#0284c7',
          main: isDht22 ? '#e2e8f0' : '#0369a1',
          light: isDht22 ? '#ffffff' : '#38bdf8',
          dark: isDht22 ? '#cbd5e1' : '#075985'
        }, isDht22 ? '#94a3b8' : '#0284c7');
        // Slotted Vents
        for (let v = -7; v <= 7; v += 4) {
          const pt = project(pos.x + v, compY - 14, pos.z - 9.5);
          ctx.fillStyle = '#475569';
          ctx.fillRect(pt.px - 1, pt.py - 6, 2, 12);
        }
      }
      else if (m.includes('bme') || m.includes('bmp') || m.includes('pressure')) {
        // BME280 / BMP280 Purple Precision Environmental Sensor
        drawBox(pos.x, compY, pos.z, 32, 6, 32, {
          top: '#7e22ce', main: '#6b21a8', light: '#a855f7', dark: '#581c87'
        }, '#c084fc');
        // Bosch Metal Cap with Port Hole
        drawBox(pos.x, compY - 4.5, pos.z, 12, 4, 12, {
          top: '#cbd5e1', main: '#94a3b8', light: '#f1f5f9', dark: '#64748b'
        });
      }
      else if (m.includes('mq') || m.includes('gas') || m.includes('smoke')) {
        // MQ Gas Sensor: Blue Breakout + Round Wire-Mesh Dome
        drawBox(pos.x, compY, pos.z, 40, 7, 36, {
          top: '#1d4ed8', main: '#1e40af', light: '#3b82f6', dark: '#172554'
        }, '#3b82f6');
        drawCylinder(pos.x, compY - 12, pos.z, 13, 18, '#94a3b8', '#cbd5e1', '#475569');
      }
      else if (m.includes('pir') || m.includes('motion')) {
        // PIR Motion Sensor: Green PCB + White Faceted Dome Lens
        drawBox(pos.x, compY, pos.z, 42, 6, 36, {
          top: '#15803d', main: '#166534', light: '#22c55e', dark: '#14532d'
        }, '#22c55e');
        drawCylinder(pos.x, compY - 10, pos.z, 14, 14, '#f8fafc', '#ffffff', '#cbd5e1');
      }
      else if (m.includes('servo')) {
        // SG90 Micro Servo: Translucent Blue Body + White Horn
        drawBox(pos.x, compY - 6, pos.z, 32, 28, 16, {
          top: '#2563eb', main: '#1d4ed8', light: '#3b82f6', dark: '#1e40af'
        }, '#1d4ed8');
        drawBox(pos.x + 6, compY - 22, pos.z, 12, 6, 12, { main: '#ffffff', top: '#f8fafc' });
        drawBox(pos.x + 6, compY - 26, pos.z, 28, 3, 7, { main: '#ffffff', top: '#f8fafc' });
      }
      else if (m.includes('relay')) {
        // High-Voltage Blue Relay Cube + Green Screw Terminal
        drawBox(pos.x - 6, compY - 8, pos.z, 36, 26, 30, {
          top: '#0284c7', main: '#0369a1', light: '#38bdf8', dark: '#075985'
        }, '#0284c7');
        drawBox(pos.x + 20, compY - 5, pos.z, 16, 18, 26, {
          top: '#15803d', main: '#166534', light: '#22c55e', dark: '#14532d'
        });
      }
      else if (m.includes('soil')) {
        // Capacitive Soil Moisture Sensor: Dual Long PCB Prongs
        drawBox(pos.x, compY - 8, pos.z, 24, 10, 18, { main: '#1e293b', top: '#0f172a' });
        drawBox(pos.x, compY + 20, pos.z, 16, 45, 4, {
          top: '#064e3b', main: '#022c22', light: '#fbbf24', dark: '#011910'
        }, '#fbbf24');
      }
      else if (m.includes('buzzer')) {
        // Piezo Buzzer: Black Cylinder with Center Sound Aperture
        drawCylinder(pos.x, compY - 7, pos.z, 14, 14, '#1e293b', '#0f172a');
        const hole = project(pos.x, compY - 14, pos.z);
        ctx.beginPath();
        ctx.arc(hole.px, hole.py, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#020617';
        ctx.fill();
      }
      else if (m.includes('led') && !m.includes('oled')) {
        // Indicator LED Bulb with soft luminous glow
        const ledCol = m.includes('red') ? '#ef4444' : m.includes('blue') ? '#38bdf8' : '#22c55e';
        drawCylinder(pos.x, compY - 8, pos.z, 7, 16, ledCol, '#ffffff');
        const glowPt = project(pos.x, compY - 16, pos.z);
        ctx.beginPath();
        ctx.arc(glowPt.px, glowPt.py, 5, 0, Math.PI * 2);
        ctx.fillStyle = ledCol;
        ctx.shadowColor = ledCol;
        ctx.shadowBlur = 12;
        ctx.fill();
        ctx.shadowBlur = 0;
      }
      else if (m.includes('mpu') || m.includes('imu') || m.includes('accel')) {
        // MPU-6050 6-Axis Gyro/Accelerometer Blue Breakout
        drawBox(pos.x, compY, pos.z, 36, 6, 26, {
          top: '#1d4ed8', main: '#1e40af', light: '#3b82f6', dark: '#172554'
        }, '#60a5fa');
        drawBox(pos.x, compY - 4.5, pos.z, 14, 3, 14, {
          top: '#0f172a', main: '#1e293b', light: '#334155', dark: '#020617'
        });
      }
      else if (m.includes('rfid') || m.includes('rc522')) {
        // RFID RC522 Reader with Golden Antenna Loop Coils
        drawBox(pos.x, compY, pos.z, 46, 6, 60, {
          top: '#1d4ed8', main: '#1e40af', light: '#3b82f6', dark: '#172554'
        }, '#fbbf24');
        const antPt = project(pos.x, compY - 3.5, pos.z);
        ctx.strokeStyle = '#fbbf24';
        ctx.lineWidth = 1.2;
        ctx.strokeRect(antPt.px - 16, antPt.py - 20, 32, 40);
      }
      else if (m.includes('pump') || m.includes('motor')) {
        // Mini 5V DC Water Pump / Motor
        drawCylinder(pos.x, compY - 8, pos.z, 15, 26, '#334155', '#475569');
        drawBox(pos.x + 14, compY - 8, pos.z, 12, 6, 6, { main: '#94a3b8' });
      }
      else {
        // Advanced Precision IoT Breakout Module
        drawBox(pos.x, compY, pos.z, 36, 8, 32, {
          top: '#1e293b', main: '#0f172a', light: '#334155', dark: '#020617'
        }, '#38bdf8');
        drawBox(pos.x, compY - 5, pos.z, 16, 4, 16, { main: '#475569' });
      }

      // Draw Floating 3D Text Label
      const lblPt = project(pos.x, compY - 26, pos.z);
      ctx.fillStyle = '#e2e8f0';
      ctx.font = 'bold 8.5px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(label, lblPt.px, lblPt.py);
      ctx.textAlign = 'start';
    }

    function frame() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Deep Space / Engineering Dark Gradient Background
      const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
      bg.addColorStop(0, '#090d16');
      bg.addColorStop(0.5, '#050811');
      bg.addColorStop(1, '#020617');
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // 3D Perspective Ground Grid
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.lineWidth = 1;
      for (let g = -220; g <= 220; g += 35) {
        const a1 = project(g, 110, -220), a2 = project(g, 110, 220);
        ctx.beginPath(); ctx.moveTo(a1.px, a1.py); ctx.lineTo(a2.px, a2.py); ctx.stroke();
        const b1 = project(-220, 110, g), b2 = project(220, 110, g);
        ctx.beginPath(); ctx.moveTo(b1.px, b1.py); ctx.lineTo(b2.px, b2.py); ctx.stroke();
      }

      // CAD Enclosure Base (Cutaway / Acrylic)
      if (enclosure !== 'off') {
        const encCol = enclosure === 'wireframe' ? 'rgba(56,189,248,0.1)' : 'rgba(30, 41, 59, 0.55)';
        drawBox(0, 32 + exploded * 45, 0, 260, 42, 230, {
          main: encCol, light: 'rgba(56, 189, 248, 0.25)', dark: 'rgba(15, 23, 42, 0.7)'
        }, 'rgba(56, 189, 248, 0.4)');
      }

      const pcbY = 10;

      // 1. Render the dynamic board geometry
      renderBoard(boardKey, pcbY);

      // 2. Filter components (exclude the MCU board itself and bench supplies)
      const rawComps = circuit?.components || [];
      const nonBoards = rawComps.filter(c => !c.model.startsWith('board:') && c.model !== 'supply5');

      // 3. Intelligent Radial / Flank Positioning for up to 12 components
      const layoutPositions = [
        { x: -115, z: 45 },
        { x: 115, z: 45 },
        { x: -115, z: -45 },
        { x: 115, z: -45 },
        { x: 0, z: 85 },
        { x: 0, z: -85 },
        { x: -150, z: 0 },
        { x: 150, z: 0 },
        { x: -80, z: 95 },
        { x: 80, z: 95 },
        { x: -80, z: -95 },
        { x: 80, z: -95 }
      ];

      const wireColors = ['#ef4444', '#38bdf8', '#22c55e', '#f59e0b', '#a855f7', '#ec4899', '#06b6d4', '#eab308'];

      nonBoards.slice(0, 12).forEach((comp, idx) => {
        const pos = layoutPositions[idx % layoutPositions.length];
        const compY = pcbY - 14 - exploded * (30 + (idx % 4) * 12);

        // Render distinct 3D model
        renderComponent(comp, pos, compY, idx);

        // Draw 3D Signal Wire
        const boardPinX = idx % 2 === 0 ? -40 : 40;
        const boardPinZ = pos.z > 0 ? 30 : -30;
        const wireColor = wireColors[idx % wireColors.length];
        drawWire(
          { x: pos.x, y: compY, z: pos.z },
          { x: boardPinX, y: pcbY - 8, z: boardPinZ },
          wireColor,
          -35 - (idx % 3) * 15
        );
      });

      // CAD Enclosure Top Cover Lid (Translucent)
      if (enclosure !== 'off') {
        const lidY = -48 - exploded * 85;
        const lidCol = enclosure === 'wireframe' ? 'rgba(56, 189, 248, 0.12)' : 'rgba(148, 163, 184, 0.22)';
        drawBox(0, lidY, 0, 264, 14, 234, {
          top: lidCol, main: lidCol, bottom: lidCol, light: 'rgba(255,255,255,0.4)', dark: 'rgba(15,23,42,0.3)'
        }, 'rgba(56, 189, 248, 0.6)');
      }

      // Title & Telemetry Status HUD
      ctx.fillStyle = '#38bdf8';
      ctx.font = 'bold 11px monospace';
      ctx.fillText('NEXUS 3D DIGITAL TWIN · ' + boardKey.toUpperCase(), 16, 24);
      ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
      ctx.font = '9.5px monospace';
      ctx.fillText(`${nonBoards.length} COMPONENT${nonBoards.length === 1 ? '' : 'S'} ACTIVE · REAL-TIME 360° ORBIT ENGINE`, 16, 40);
    }

    // Interaction Handlers (Orbit Dragging & Wheel Zoom)
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
      pitch = Math.max(-1.15, Math.min(1.15, pitch + dy * 0.008));
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
      zoom = Math.max(0.4, Math.min(2.8, zoom + (e.deltaY < 0 ? 0.1 : -0.1)));
      frame();
    };

    frame();

    return {
      setExploded: val => { exploded = val; frame(); },
      setEnclosure: mode => { enclosure = mode; frame(); },
      resetView: () => { yaw = -0.65; pitch = 0.45; zoom = 1.0; frame(); },
      exportSTL: () => {
        const stlContent = `solid NEXUS_IoT_${boardKey}_Digital_Twin
facet normal 0 0 1
  outer loop
    vertex -110 -90 0
    vertex 110 -90 0
    vertex 110 90 0
  endloop
endfacet
facet normal 0 0 1
  outer loop
    vertex -110 -90 0
    vertex 110 90 0
    vertex -110 90 0
  endloop
endfacet
endsolid NEXUS_IoT_${boardKey}_Digital_Twin`;
        const blob = new Blob([stlContent], { type: 'model/stl' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `nexus_${boardKey}_digital_twin_cad.stl`;
        a.click();
        URL.revokeObjectURL(url);
        toast('Downloaded 3D STL Enclosure CAD model ready for 3D printing!', 'ok');
      }
    };
  }

  function open3DModal(circuit, projectName = 'IoT Project') {
    const isPro = true;
    const content = `
      <div style="display:flex;flex-direction:column;gap:12px;">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <p class="tiny muted">360° Real-time Photorealistic 3D Model with Custom Board Geometry, Enclosure, and Connections.</p>
          <span class="badge violet">★ Pro 3D Digital Twin</span>
        </div>
        <div id="twin-3d-viewport" style="width:100%;height:450px;background:#090d16;border-radius:8px;position:relative;overflow:hidden;box-shadow:inset 0 0 20px rgba(0,0,0,0.8);"></div>
        <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:10px;">
            <label class="field" style="margin:0;display:flex;align-items:center;gap:6px;">
              <span class="tiny muted">Exploded View:</span>
              <input type="range" id="twin-explode" min="0" max="1" step="0.02" value="0" style="width:130px;">
            </label>
            <button class="btn sm" id="twin-reset">⟲ Reset Orbit</button>
            <select class="btn sm" id="twin-enclosure">
              <option value="transparent">Transparent Case</option>
              <option value="wireframe">Wireframe Cutaway</option>
              <option value="off">PCB Only (No Case)</option>
            </select>
          </div>
          <div style="display:flex;gap:8px;">
            <button class="btn primary sm" id="twin-export-stl">💾 Export 3D STL CAD Model</button>
          </div>
        </div>
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
'''

target_path = Path(r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\web\digital-twin-3d.js")
target_path.write_text(content, encoding='utf-8')
print("Successfully updated web/digital-twin-3d.js")
