from reportlab.platypus import Flowable, Paragraph
from reportlab.lib.units import mm

from .styles import (
    get_status_colors, BORDER, BG_SUBTLE, BRAND_DARK, MUTED, WHITE, INK, BLUE_BG, BLUE_BORDER
)

class ScoreGauge(Flowable):
    def __init__(self, score, width=160, height=32):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.score = score
        # Using status to drive colours based on score logic
        self.fg, self.bg, self.border, self.dark = get_status_colors("completed" if score >= 85 else "failed", score)

    def draw(self):
        canvas = self.canv
        # Background bar
        canvas.setFillColor(BG_SUBTLE)
        canvas.setStrokeColor(BG_SUBTLE)
        # We leave space on right for score label
        bar_width = self.width - 40
        canvas.roundRect(0, 0, bar_width, self.height, 4, fill=1, stroke=0)
        
        # Fill bar
        fill_width = bar_width * (max(0, min(100, self.score)) / 100.0)
        if fill_width > 0:
            canvas.setFillColor(self.fg)
            canvas.roundRect(0, 0, fill_width, self.height, 4, fill=1, stroke=0)
            
        # Score label
        canvas.setFillColor(self.fg)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawRightString(self.width, 8, f"{self.score:.1f}")

class StatusPill(Flowable):
    def __init__(self, text, fg, bg, width=100, height=20):
        Flowable.__init__(self)
        self.text = text
        self.fg = fg
        self.bg = bg
        self.width = width
        self.height = height

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(self.bg)
        canvas.setStrokeColor(self.bg)
        canvas.roundRect(0, 0, self.width, self.height, self.height/2.0, fill=1, stroke=0)
        
        canvas.setFillColor(self.fg)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawCentredString(self.width / 2.0, (self.height / 2.0) - 3, self.text.upper())

class DomainStripe(Flowable):
    def __init__(self, domain_name, color, bg_color, width, confidence_pct=None):
        Flowable.__init__(self)
        self.domain_name = domain_name
        self.color = color
        self.bg_color = bg_color
        self.width = width
        self.height = 24
        self.confidence_pct = confidence_pct

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(self.color)
        canvas.setStrokeColor(self.color)
        canvas.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 10)
        # Vertically align text (roughly)
        canvas.drawString(8, 8, self.domain_name.upper())
        
        if self.confidence_pct is not None:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.drawRightString(self.width - 8, 8, f"{self.confidence_pct}%")

class EvidenceBlock(Flowable):
    def __init__(self, text, width):
        Flowable.__init__(self)
        self.text = text
        self.width = width
        self.padding = 6
        
        from reportlab.lib.styles import ParagraphStyle
        style = ParagraphStyle(name='ev', fontName='Courier', fontSize=8, textColor=INK, leading=10)
        self.p = Paragraph(str(text), style)
        _w, self.p_h = self.p.wrap(self.width - self.padding * 2 - 3, 1000) # -3 for left border
        self.height = self.p_h + self.padding * 2

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        # BG
        canvas.setFillColor(BLUE_BG)
        canvas.setStrokeColor(BLUE_BG)
        canvas.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        
        # Left Border
        canvas.setFillColor(BLUE_BORDER)
        canvas.setStrokeColor(BLUE_BORDER)
        canvas.rect(0, 0, 3, self.height, fill=1, stroke=0)
        
        # Text
        self.p.drawOn(canvas, self.padding + 3, self.height - self.padding - self.p_h)

class MiniProgressBar(Flowable):
    def __init__(self, value, color=None, width=80, height=6):
        Flowable.__init__(self)
        self.value = value # 0.0 to 1.0
        self.width = width
        self.height = height
        
        from .styles import GREEN
        self.color = color or GREEN

    def draw(self):
        canvas = self.canv
        canvas.setFillColor(BORDER)
        canvas.roundRect(0, 0, self.width, self.height, 2, fill=1, stroke=0)
        
        fill_width = self.width * max(0, min(1.0, self.value))
        if fill_width > 0:
            canvas.setFillColor(self.color)
            canvas.roundRect(0, 0, fill_width, self.height, 2, fill=1, stroke=0)

class SectionDivider(Flowable):
    def __init__(self, width, color=None, thickness=0.5):
        Flowable.__init__(self)
        self.width = width
        self.height = thickness + 4 # some padding
        self.thickness = thickness
        self.color = color

    def draw(self):
        from .styles import BORDER
        canvas = self.canv
        color = self.color or BORDER
        canvas.setStrokeColor(color)
        canvas.setLineWidth(self.thickness)
        y = self.height / 2.0
        canvas.line(0, y, self.width, y)


def PageHeaderFooter(canvas, doc, milestone_id, tier):
    """
    Called on each page to render the fixed header/footer.
    """
    canvas.saveState()
    
    # Header
    canvas.setFillColor(BRAND_DARK)
    # The origin (0,0) is bottom-left
    canvas.rect(0, doc.pagesize[1] - 12*mm, doc.pagesize[0], 12*mm, fill=1, stroke=0)
    
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(doc.leftMargin, doc.pagesize[1] - 8*mm, "VaultedEscrow")
    
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(doc.pagesize[0] / 2.0, doc.pagesize[1] - 8*mm, "QA Evaluation Report")
    
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, doc.pagesize[1] - 8*mm, f"Milestone: {milestone_id}")
    
    # Footer
    canvas.setFillColor(BG_SUBTLE)
    canvas.rect(0, 0, doc.pagesize[0], 9*mm, fill=1, stroke=0)
    
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(doc.leftMargin, 4*mm, f"Generated by VaultedEscrow QA Agent \u00b7 Tier {tier}")
    
    canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 4*mm, f"Page {doc.page}")
    
    canvas.restoreState()
