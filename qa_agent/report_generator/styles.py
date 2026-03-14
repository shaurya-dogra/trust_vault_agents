from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Brand
BRAND_DARK    = colors.HexColor("#0f1729")   # deep navy
BRAND_MID     = colors.HexColor("#1a2744")   # section headers
BRAND_ACCENT  = colors.HexColor("#2563EB")   # links, code, info highlights

# Neutrals
INK           = colors.HexColor("#1a1a2e")
MUTED         = colors.HexColor("#5f5e5a")
LIGHT         = colors.HexColor("#888780")
BORDER        = colors.HexColor("#d3d1c7")
BG_SURFACE    = colors.HexColor("#f8f7f4")
BG_SUBTLE     = colors.HexColor("#f1efe8")
WHITE         = colors.HexColor("#ffffff")

# Semantic — status
GREEN         = colors.HexColor("#1D9E75")
GREEN_BG      = colors.HexColor("#e1f5ee")
GREEN_DARK    = colors.HexColor("#085041")
GREEN_BORDER  = colors.HexColor("#9FE1CB")

AMBER         = colors.HexColor("#BA7517")
AMBER_BG      = colors.HexColor("#faeeda")
AMBER_BORDER  = colors.HexColor("#FAC775")

RED           = colors.HexColor("#A32D2D")
RED_BG        = colors.HexColor("#fcebeb")
RED_BORDER    = colors.HexColor("#F09595")

BLUE          = colors.HexColor("#185FA5")
BLUE_BG       = colors.HexColor("#e6f1fb")
BLUE_BORDER   = colors.HexColor("#85B7EB")

# Domain colours
COLOR_CODE    = colors.HexColor("#085041")   # teal-dark
COLOR_CODE_BG = colors.HexColor("#e1f5ee")
COLOR_IMAGE   = colors.HexColor("#712B13")   # coral-dark
COLOR_IMAGE_BG= colors.HexColor("#faece7")
COLOR_AUDIO   = colors.HexColor("#633806")   # amber-dark
COLOR_AUDIO_BG= colors.HexColor("#faeeda")

def get_status_colors(status: str, score: float):
    if status == "completed" or score >= 85:
        return GREEN, GREEN_BG, GREEN_BORDER, GREEN_DARK
    elif status == "partial_completion" or score >= 60:
        return AMBER, AMBER_BG, AMBER_BORDER, AMBER
    else:
        return RED, RED_BG, RED_BORDER, RED

def get_domain_colors(domain: str):
    domain = domain.lower()
    if domain == "code":
        return COLOR_CODE, COLOR_CODE_BG
    elif domain == "image":
        return COLOR_IMAGE, COLOR_IMAGE_BG
    elif domain == "audio":
        return COLOR_AUDIO, COLOR_AUDIO_BG
    return BRAND_MID, BG_SUBTLE

def get_theme_styles():
    styles = getSampleStyleSheet()
    
    # Base modifications for built-in Helvetica
    styles.add(ParagraphStyle(name='Normal_INK', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=INK))
    styles.add(ParagraphStyle(name='Normal_MUTED', parent=styles['Normal'], fontName='Helvetica', fontSize=9, textColor=MUTED, leading=11))
    
    styles.add(ParagraphStyle(name='H1_BRAND', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=BRAND_DARK, spaceAfter=12))
    styles.add(ParagraphStyle(name='H2_BRAND', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=14, textColor=BRAND_DARK, spaceBefore=12, spaceAfter=8))
    
    styles.add(ParagraphStyle(name='LABEL', fontName='Helvetica-Bold', fontSize=7, textColor=MUTED, spaceAfter=2))
    styles.add(ParagraphStyle(name='BOLD', fontName='Helvetica-Bold', fontSize=9, textColor=INK))
    
    styles.add(ParagraphStyle(name='NARRATIVE', fontName='Helvetica-Oblique', fontSize=9, textColor=INK, spaceBefore=6, spaceAfter=12, leading=12))
    
    return styles
