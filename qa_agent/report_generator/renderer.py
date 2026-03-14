import io
from reportlab.platypus import SimpleDocTemplate
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from .templates.standard import build_standard_story
from .components import PageHeaderFooter

def render_report_to_bytes(qa_report: dict, llm_data: dict) -> bytes:
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=20*mm,
        bottomMargin=20*mm,
        allowSplitting=1
    )
    
    story = build_standard_story(qa_report, llm_data)
    
    tier = str(qa_report.get("tier", "Unknown"))
    milestone_id = str(qa_report.get("milestone_id", "Unknown"))
    
    def on_page(canvas, doc):
        PageHeaderFooter(canvas, doc, milestone_id, tier)
        
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    
    pdf_bytes = buffer.getvalue()
    buffer.close()
    
    return pdf_bytes
