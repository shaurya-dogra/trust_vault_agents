import io
import json
from typing import Optional
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

from .llm_analyst import analyse_report
from .renderer import render_report_to_bytes
from .styles import get_theme_styles

def generate_error_pdf(error_message: str, raw_json: dict) -> bytes:
    """
    Fallback: generates a simple PDF with the error and the raw QA JSON.
    Used when the main generator fails.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
        allowSplitting=1
    )
    styles = get_theme_styles()
    story = []
    
    story.append(Paragraph("VaultedEscrow QA Report Generation Error", styles['H1_BRAND']))
    story.append(Spacer(1, 5*mm))
    
    story.append(Paragraph("An error occurred during report generation:", styles['BOLD']))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(str(error_message), styles['Normal_INK']))
    story.append(Spacer(1, 10*mm))
    
    story.append(Paragraph("Raw QA JSON Data:", styles['BOLD']))
    story.append(Spacer(1, 2*mm))
    try:
        json_str = json.dumps(raw_json, indent=2)
        if len(json_str) > 3000:
            json_str = json_str[:3000] + "\n... [TRUNCATED]"
    except Exception:
        json_str = str(raw_json)
        
    from reportlab.lib.styles import ParagraphStyle
    from .styles import INK, BG_SUBTLE
    mono_s = ParagraphStyle('mono', fontName='Courier', fontSize=8, textColor=INK, backColor=BG_SUBTLE)
    
    # Very basic fix for newlines in Paragraph
    json_str = json_str.replace("\n", "<br/>").replace(" ", "&nbsp;")
    story.append(Paragraph(json_str, mono_s))
    
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

def generate_qa_report_pdf(qa_report: dict, output_path: Optional[str] = None) -> bytes:
    """
    Main entry point. Takes QAReport dict, returns PDF as bytes.
    Never raises — on any error, generates a minimal error report PDF with the error message.
    """
    try:
        # Step 1: Call llm_analyst
        llm_data = analyse_report(qa_report)
        
        # Step 2 & 3: Build & Render
        pdf_bytes = render_report_to_bytes(qa_report, llm_data)
        
        if output_path:
            with open(output_path, "wb") as f:
                f.write(pdf_bytes)
                
        return pdf_bytes
        
    except Exception as e:
        print(f"Error generating QA Report PDF: {str(e)}")
        error_pdf = generate_error_pdf(str(e), qa_report)
        if output_path:
            with open(output_path, "wb") as f:
                f.write(error_pdf)
        return error_pdf

if __name__ == "__main__":
    from . import SAMPLE_QA_REPORT # We need . for module execution properly unless we run top level
    import os
    
    print("Starting generation. Calling LLMs (may take 10-30s)...")
    pdf_bytes = generate_qa_report_pdf(
        SAMPLE_QA_REPORT,
        output_path="./VaultedEscrow_QA_Sample_Report.pdf"
    )
    print(f"Report generated: {len(pdf_bytes)} bytes")
    print("Saved to: ./VaultedEscrow_QA_Sample_Report.pdf")
