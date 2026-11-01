"""Generate high-resolution PWA icons for NEXUS IoT (Samsung Galaxy Store & Mobile)."""
import os
import math
from PIL import Image, ImageDraw

def create_nexus_icon(size: int, output_path: str, maskable: bool = False):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background
    corner_radius = 0 if maskable else int(size * 0.22)
    bg_color = (11, 18, 32, 255) # #0b1220 deep navy
    
    if maskable or corner_radius == 0:
        draw.rectangle([0, 0, size, size], fill=bg_color)
    else:
        draw.rounded_rectangle([0, 0, size, size], radius=corner_radius, fill=bg_color)

    # Glowing subtle circuit grid in background
    grid_color = (18, 30, 52, 255)
    step = size // 8
    for i in range(1, 8):
        pos = i * step
        draw.line([(pos, 0), (pos, size)], fill=grid_color, width=max(1, size // 128))
        draw.line([(0, pos), (size, pos)], fill=grid_color, width=max(1, size // 128))

    # Margin & padding
    pad = int(size * 0.24) if maskable else int(size * 0.20)
    w = size - 2 * pad
    h = size - 2 * pad

    # NEXUS 'N' Circuit Glyph
    # Points:
    # P1: bottom-left (pad, pad + h)
    # P2: top-left (pad, pad)
    # P3: bottom-mid (pad + int(w * 0.52), pad + h)
    # P4: top-mid (pad + int(w * 0.52), pad)
    # P5: right-arm (pad + w, pad)
    
    p1 = (pad, pad + h)
    p2 = (pad, pad)
    p3 = (pad + int(w * 0.52), pad + h)
    p4 = (pad + int(w * 0.52), pad)
    p5 = (pad + int(w * 0.88), pad)

    stroke_width = max(3, int(size * 0.08))
    cyan = (34, 211, 238, 255) # #22d3ee
    violet = (139, 92, 246, 255) # #8b5cf6
    electric_blue = (0, 212, 255, 255)

    # Draw circuit paths
    draw.line([p1, p2], fill=cyan, width=stroke_width)
    draw.line([p2, p3], fill=electric_blue, width=stroke_width)
    draw.line([p3, p4], fill=cyan, width=stroke_width)
    draw.line([p4, p5], fill=violet, width=stroke_width)

    # Terminal pads (circuit dots)
    dot_r = max(4, int(stroke_width * 0.75))
    # Glowing dot at P5
    draw.ellipse([p5[0] - dot_r, p5[1] - dot_r, p5[0] + dot_r, p5[1] + dot_r], fill=violet)
    # Accent dot at P1
    draw.ellipse([p1[0] - dot_r//2, p1[1] - dot_r//2, p1[0] + dot_r//2, p1[1] + dot_r//2], fill=cyan)

    img.save(output_path, "PNG", optimize=True)
    print(f"Generated {output_path} ({size}x{size})")

if __name__ == "__main__":
    web_dir = os.path.join(os.path.dirname(__file__), "..", "web")
    create_nexus_icon(192, os.path.join(web_dir, "icon-192.png"))
    create_nexus_icon(512, os.path.join(web_dir, "icon-512.png"))
    create_nexus_icon(512, os.path.join(web_dir, "icon-512-maskable.png"), maskable=True)
