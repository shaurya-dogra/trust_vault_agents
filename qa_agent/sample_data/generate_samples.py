"""
TrustVault QA — Sample data generator.
Run once before demo: python sample_data/generate_samples.py
Requires: pip install pillow numpy scipy
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import scipy.io.wavfile as wav

OUT_IMG  = Path(__file__).parent / "submissions" / "images"
OUT_AUD  = Path(__file__).parent / "submissions" / "audio"
OUT_IMG.mkdir(parents=True, exist_ok=True)
OUT_AUD.mkdir(parents=True, exist_ok=True)


# ─── IMAGE GENERATION ────────────────────────────────────────────

def draw_checkout_mockup(width: int, height: int, label: str) -> Image.Image:
    BG        = "#1a1a2e"
    CARD_BG   = "#16213e"
    ACCENT    = "#e94560"
    TEXT_PRI  = "#eaeaea"
    TEXT_SEC  = "#9a9ab0"
    FIELD_BG  = "#0f3460"
    FIELD_BOR = "#2a2a5a"

    img  = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    scale  = width / 1440
    cw     = int(600 * scale)
    ch     = int(520 * scale)
    cx     = (width - cw) // 2
    cy     = (height - ch) // 2

    # card shadow (offset rect)
    draw.rounded_rectangle(
        [cx + int(6*scale), cy + int(6*scale),
         cx + cw + int(6*scale), cy + ch + int(6*scale)],
        radius=int(16*scale), fill="#0a0a1a"
    )
    # card
    draw.rounded_rectangle(
        [cx, cy, cx + cw, cy + ch],
        radius=int(16*scale), fill=CARD_BG
    )

    # accent bar top of card
    draw.rounded_rectangle(
        [cx, cy, cx + cw, cy + int(6*scale)],
        radius=int(4*scale), fill=ACCENT
    )

    # try to load font, fall back gracefully
    try:
        font_title  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(10, int(28*scale)))
        font_label  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(10, int(14*scale)))
        font_small  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", max(10, int(12*scale)))
    except Exception:
        font_title = font_label = font_small = ImageFont.load_default()

    pad   = int(40 * scale)
    fw    = cw - pad * 2
    fh    = int(44 * scale)
    gap   = int(18 * scale)

    # title
    draw.text((cx + pad, cy + int(28*scale)), "Checkout", fill=TEXT_PRI, font=font_title)
    draw.text((cx + pad, cy + int(64*scale)), "Complete your purchase securely",
              fill=TEXT_SEC, font=font_small)

    # divider
    y_div = cy + int(96*scale)
    draw.line([(cx + pad, y_div), (cx + cw - pad, y_div)], fill=FIELD_BOR, width=1)

    fields = [
        ("Full Name",    "John Doe"),
        ("Email",        "john@example.com"),
        ("Card Number",  "•••• •••• •••• 4242"),
    ]

    y_cur = y_div + gap
    for label_text, placeholder in fields:
        draw.text((cx + pad, y_cur), label_text, fill=TEXT_SEC, font=font_small)
        y_cur += int(20 * scale)
        draw.rounded_rectangle(
            [cx + pad, y_cur, cx + pad + fw, y_cur + fh],
            radius=int(8*scale), fill=FIELD_BG, outline=FIELD_BOR, width=1
        )
        draw.text(
            (cx + pad + int(12*scale), y_cur + int(14*scale)),
            placeholder, fill=TEXT_SEC, font=font_label
        )
        y_cur += fh + gap

    # Pay Now button
    y_cur += int(4 * scale)
    draw.rounded_rectangle(
        [cx + pad, y_cur, cx + pad + fw, y_cur + int(52*scale)],
        radius=int(10*scale), fill=ACCENT
    )
    btn_label = "Pay Now"
    bbox = draw.textbbox((0, 0), btn_label, font=font_title)
    bw   = bbox[2] - bbox[0]
    bh   = bbox[3] - bbox[1]
    draw.text(
        (cx + pad + (fw - bw) // 2, y_cur + (int(52*scale) - bh) // 2),
        btn_label, fill="#ffffff", font=font_title
    )

    # watermark label
    draw.text(
        (width - int(160*scale), height - int(24*scale)),
        f"TrustVault Demo — {label}",
        fill="#2a2a4a", font=font_small
    )

    return img


print("Generating design_v1.png  (1440×900 desktop mockup)...")
img_desktop = draw_checkout_mockup(1440, 900, "Desktop 1440×900")
img_desktop.save(OUT_IMG / "design_v1.png")
print("  ✓ Saved design_v1.png")

print("Generating design_mobile.png  (375×812 mobile mockup)...")
img_mobile = draw_checkout_mockup(375, 812, "Mobile 375×812")
img_mobile.save(OUT_IMG / "design_mobile.png")
print("  ✓ Saved design_mobile.png")


# ─── AUDIO GENERATION ────────────────────────────────────────────

def generate_walkthrough_wav(path: Path,
                              duration: float = 35.0,
                              sr: int = 44100) -> None:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # speech-like fundamental with harmonics
    f0        = 180.0
    signal    = (
        0.55 * np.sin(2 * np.pi * f0 * t) +
        0.25 * np.sin(2 * np.pi * f0 * 2 * t) +
        0.12 * np.sin(2 * np.pi * f0 * 3 * t) +
        0.05 * np.sin(2 * np.pi * f0 * 4 * t)
    )

    # 3 Hz amplitude modulation (syllable cadence)
    signal   *= 0.5 + 0.5 * np.sin(2 * np.pi * 3.0 * t)

    # sentence-break silences every ~5 seconds
    silence_mask = np.ones_like(t)
    for pause_start in np.arange(4.5, duration, 5.0):
        s = int(pause_start * sr)
        e = min(int((pause_start + 0.35) * sr), len(t))
        silence_mask[s:e] = 0.0
    signal *= silence_mask

    # mild noise floor (breath)
    rng     = np.random.default_rng(42)
    signal += rng.normal(0, 0.008, signal.shape)

    # normalize to 80% of int16 headroom
    peak    = np.max(np.abs(signal)) + 1e-9
    signal  = (signal / peak * 0.80 * 32767).astype(np.int16)

    # stereo: slight pan variation between channels
    left    = signal
    right   = np.roll(signal, 64)       # 64-sample offset for mild stereo spread
    stereo  = np.stack([left, right], axis=1).astype(np.int16)

    wav.write(str(path), sr, stereo)


print("Generating walkthrough.wav  (35s stereo speech-sim)...")
generate_walkthrough_wav(OUT_AUD / "walkthrough.wav")
print("  ✓ Saved walkthrough.wav")

# remove silence.wav if it still exists
silence_path = OUT_AUD / "silence.wav"
if silence_path.exists():
    silence_path.unlink()
    print("  ✓ Removed silence.wav")

print("\\nAll sample files generated successfully.")
print(f"  Images → {OUT_IMG}")
print(f"  Audio  → {OUT_AUD}")
