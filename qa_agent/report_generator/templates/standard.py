from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.units import mm
import json

from ..styles import (
    get_theme_styles, get_status_colors, get_domain_colors,
    BRAND_DARK, BRAND_MID, BRAND_ACCENT, INK, MUTED, LIGHT, BORDER,
    BG_SURFACE, BG_SUBTLE, WHITE,
    GREEN, GREEN_BG, GREEN_BORDER, GREEN_DARK,
    AMBER, AMBER_BG, AMBER_BORDER,
    RED, RED_BG, RED_BORDER,
    BLUE, BLUE_BG, BLUE_BORDER
)
from ..components import (
    ScoreGauge, StatusPill, DomainStripe, EvidenceBlock, 
    MiniProgressBar, SectionDivider
)

styles = get_theme_styles()

def build_standard_story(qa_report: dict, llm_data: dict) -> list:
    story = []
    
    # Section 1 — Cover metadata strip
    evaluated_at = qa_report.get("evaluated_at", "Unknown").split(".")[0].replace("T", " ")
    milestone_id = qa_report.get("milestone_id", "Unknown")
    sub_hash = str(qa_report.get("submission_hash", "Unknown"))
    short_hash = sub_hash[:12] + "..." if len(sub_hash) > 12 else sub_hash
    tier = str(qa_report.get("tier", "Unknown"))
    
    meta_data = [
        [Paragraph("EVALUATED AT", styles['LABEL']), Paragraph("MILESTONE ID", styles['LABEL']), 
         Paragraph("SUBMISSION HASH", styles['LABEL']), Paragraph("AGENT TIER", styles['LABEL'])],
        [Paragraph(evaluated_at, styles['BOLD']), Paragraph(milestone_id, styles['BOLD']),
         Paragraph(short_hash, styles['BOLD']), Paragraph(f"Tier {tier}", styles['BOLD'])]
    ]
    t_meta = Table(meta_data, colWidths=[45*mm, 35*mm, 60*mm, 35*mm])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 8*mm))
    
    # Section 2 — Score summary card
    score = qa_report.get("completion_score", 0.0)
    fg, bg, bd, dark = get_status_colors(qa_report.get("status", "unknown"), score)
    
    deliv_score = qa_report.get("deliverable_presence_score", 0.0)
    crit_score = qa_report.get("criteria_compliance_score", 0.0)
    
    from reportlab.lib.styles import ParagraphStyle
    score_style = ParagraphStyle('score_s', fontName='Helvetica-Bold', fontSize=22, textColor=fg, spaceAfter=4)
    pct_style = ParagraphStyle('pct_s', fontName='Helvetica-Bold', fontSize=16, textColor=INK, spaceAfter=4)
    
    status_str = str(qa_report.get("status", "unknown")).replace("_", " ")
    status_pill = StatusPill(status_str, fg, bg, width=90, height=18)
    
    exec_full = llm_data.get("executive_summary", "")
    exec_short = exec_full.split(". ")[0] + "." if ". " in exec_full else exec_full
    
    s2_data = [
        [
            Paragraph("OVERALL SCORE", styles['LABEL']),
            Paragraph("DELIVERABLE PRESENCE", styles['LABEL']),
            Paragraph("CRITERIA COMPLIANCE", styles['LABEL']),
            Paragraph("STATUS", styles['LABEL'])
        ],
        [
            Paragraph(f"{score:.1f}", score_style),
            Paragraph(f"{deliv_score*100:.0f}%", pct_style),
            Paragraph(f"{crit_score*100:.0f}%", pct_style),
            status_pill
        ],
        [
            ScoreGauge(score, width=40*mm, height=12),
            MiniProgressBar(deliv_score, width=30*mm),
            MiniProgressBar(crit_score, width=30*mm),
            Paragraph(exec_short, styles['Normal_MUTED']) 
        ]
    ]
    
    t_summary = Table(s2_data, colWidths=[45*mm, 45*mm, 45*mm, 50*mm])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), BG_SURFACE),
        ('BOX', (0,0), (-1,-1), 0.5, BORDER),
        ('PADDING', (0,0), (-1,-1), 10),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 6*mm))
    
    # Section 3 — LLM executive summary
    dr_list = qa_report.get("domain_reports", [])
    domains_eval = len(dr_list)
    total_cr = sum(len(d.get("criteria_results", [])) for d in dr_list)
    met_cr = sum(1 for d in dr_list for c in d.get("criteria_results", []) if c.get("met"))
    
    issues_count = len(qa_report.get("issues", []))
    missing_deliv = len(qa_report.get("missing_deliverables", []))
    
    qfacts = [
        [Paragraph("QUICK FACTS", styles['LABEL']), ""],
        [Paragraph("Domains Evaluated:", styles['Normal_MUTED']), Paragraph(str(domains_eval), styles['BOLD'])],
        [Paragraph("Criteria Met:", styles['Normal_MUTED']), Paragraph(f"{met_cr} / {total_cr}", styles['BOLD'])],
        [Paragraph("Issues Found:", styles['Normal_MUTED']), Paragraph(str(issues_count), styles['BOLD'])],
        [Paragraph("Missing Deliverables:", styles['Normal_MUTED']), Paragraph(str(missing_deliv), styles['BOLD'])]
    ]
    t_qf = Table(qfacts, colWidths=[30*mm, 15*mm])
    t_qf.setStyle(TableStyle([
        ('PADDING', (0,0), (-1,-1), 2),
        ('VALIGN', (0,0), (-1,-1), 'TOP')
    ]))
    
    s3_data = [[
        Paragraph(exec_full, styles['Normal_INK']),
        t_qf
    ]]
    t_s3 = Table(s3_data, colWidths=[130*mm, 55*mm])
    t_s3.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0)
    ]))
    story.append(t_s3)
    story.append(Spacer(1, 10*mm))
    
    # Section 4 — Domain analysis overview table
    story.append(Paragraph("Domain Analysis Overview", styles['H2_BRAND']))
    story.append(Spacer(1, 3*mm))
    
    h_data = [
        Paragraph("Domain", styles['LABEL']),
        Paragraph("Model", styles['LABEL']),
        Paragraph("Criteria", styles['LABEL']),
        Paragraph("Confidence", styles['LABEL']),
        Paragraph("Tools run", styles['LABEL']),
        Paragraph("Warnings", styles['LABEL']),
        Paragraph("Status", styles['LABEL'])
    ]
    da_data = [h_data]
    
    for i, dr in enumerate(dr_list):
        dom = str(dr.get("domain", "unknown"))
        d_color, d_bg = get_domain_colors(dom)
        
        tools_run = len([k for k, v in dr.get("tool_results", {}).items() if "status" not in str(v)]) 
        # approximate, just use the keys count
        tools_run = len(dr.get("tool_results", {}).keys())
        
        warns = len(dr.get("warnings", []))
        cr_count = len(dr.get("criteria_results", []))
        conf_pct = int(dr.get("agent_confidence", 0) * 100)
        
        fg_d, bg_d, bd_d, dk_d = get_status_colors("completed" if conf_pct >= 80 and warns==0 else "partial_completion", conf_pct)
        pill = StatusPill("OK" if warns==0 else "WARN", fg_d, bg_d, width=32, height=14)
        
        c_p_s = ParagraphStyle('cs', fontName='Helvetica-Bold', fontSize=9, textColor=fg_d)
        ds = DomainStripe(dom[:12].capitalize(), d_color, d_bg, width=28*mm) # limited length for table
        
        da_data.append([
            ds,
            Paragraph(str(dr.get("model", "qwen3-coder")), styles['Normal_INK']),
            Paragraph(str(cr_count), styles['Normal_INK']),
            Paragraph(f"{conf_pct}%", c_p_s),
            Paragraph(str(tools_run), styles['Normal_INK']),
            Paragraph(str(warns), styles['Normal_INK'] if warns == 0 else ParagraphStyle('warn', parent=styles['Normal_INK'], textColor=AMBER)),
            pill
        ])
        
    t_da = Table(da_data, colWidths=[30*mm, 35*mm, 20*mm, 25*mm, 25*mm, 25*mm, 25*mm])
    t_da_style = [
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('LINEBELOW', (0,0), (-1,0), 0.5, BORDER),
        ('LEFTPADDING', (0,0), (0,-1), 0),
    ]
    for i in range(1, len(da_data)):
        bg_col = WHITE if i % 2 == 1 else BG_SUBTLE
        t_da_style.append(('BACKGROUND', (0, i), (-1, i), bg_col))
        t_da_style.append(('TOPPADDING', (0, i), (-1, i), 4))
        t_da_style.append(('BOTTOMPADDING', (0, i), (-1, i), 4))
        
    t_da.setStyle(TableStyle(t_da_style))
    story.append(t_da)
    story.append(Spacer(1, 10*mm))
    
    # Section 5 — Per-domain deep dive sections
    for dr in dr_list:
        section_story = [] # Keep header and first table together
        dom = str(dr.get("domain", "unknown"))
        d_color, d_bg = get_domain_colors(dom)
        conf_pct = int(dr.get("agent_confidence", 0) * 100)
        
        section_story.append(Spacer(1, 6*mm))
        section_story.append(DomainStripe(f"DOMAIN: {dom}", d_color, d_bg, width=185*mm, confidence_pct=conf_pct))
        section_story.append(Spacer(1, 4*mm))
        
        narrative = llm_data.get("domain_narratives", {}).get(dom, "")
        if narrative:
            section_story.append(Paragraph(narrative, styles['NARRATIVE']))
        
        # Tool results table
        section_story.append(Paragraph("Tool Results", styles['BOLD']))
        section_story.append(Spacer(1, 2*mm))
        
        tr_data = [[Paragraph("Tool", styles['LABEL']), Paragraph("Result", styles['LABEL']), Paragraph("Detail", styles['LABEL'])]]
        
        for t_name, t_val in dr.get("tool_results", {}).items():
            if t_name in ["primary_image"]: continue
            
            # Simple heuristic for pass/fail/unavailable
            status_str = "OK"
            fg_t, bg_t = GREEN, GREEN_BG
            if isinstance(t_val, dict) and "tool_status" in t_val:
                st = str(t_val["tool_status"])
                if "unavailable" in st.lower():
                    status_str = "UNAVAIL"
                    fg_t, bg_t = RED, RED_BG
                elif "error" in st.lower():
                    status_str = "ERROR"
                    fg_t, bg_t = AMBER, AMBER_BG
                    
            pill = StatusPill(status_str, fg_t, bg_t, width=28, height=14)
            
            # Format val
            val_str = json.dumps(t_val) if isinstance(t_val, dict) else str(t_val)
            if len(val_str) > 100:
                val_str = val_str[:97] + "..."
                
            tr_data.append([
                Paragraph(t_name, styles['BOLD']),
                pill,
                Paragraph(val_str, styles['Normal_MUTED'])
            ])
            
        if len(tr_data) > 1:
            t_tool = Table(tr_data, colWidths=[40*mm, 20*mm, 125*mm])
            t_tool.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LINEBELOW', (0,0), (-1,0), 0.5, BORDER),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LEFTPADDING', (0,0), (0,-1), 0),
            ]))
            section_story.append(t_tool)
            section_story.append(Spacer(1, 6*mm))
            
        story.append(KeepTogether(section_story))
            
        # Criterion results table
        cr_list = dr.get("criteria_results", [])
        if cr_list:
            story.append(Paragraph("Criteria Results", styles['BOLD']))
            story.append(Spacer(1, 2*mm))
            
            cr_data = [[Paragraph("Criterion", styles['LABEL']), Paragraph("Result", styles['LABEL']), Paragraph("Confidence", styles['LABEL']), Paragraph("Evidence", styles['LABEL'])]]
            for cr in cr_list:
                met = cr.get("met", False)
                res_p = Paragraph("MET", ParagraphStyle('met', fontName='Helvetica-Bold', fontSize=9, textColor=GREEN)) if met else Paragraph("NOT MET", ParagraphStyle('nmet', fontName='Helvetica-Bold', fontSize=9, textColor=RED))
                conf = f"{int(cr.get('confidence', 0)*100)}%"
                ev = EvidenceBlock(cr.get("evidence", ""), width=65*mm)
                
                cr_data.append([
                    Paragraph(str(cr.get("criterion", "")), styles['Normal_INK']),
                    res_p,
                    Paragraph(conf, styles['Normal_INK']),
                    ev
                ])
                
                fix = cr.get("recommended_fix")
                if fix:
                    # Sub row
                    fix_p = Paragraph(f"<b>FIX:</b> {fix}", ParagraphStyle('fix', fontName='Helvetica', fontSize=8, textColor=AMBER))
                    cr_data.append([fix_p, "", "", ""])
                    
            t_cr = Table(cr_data, colWidths=[70*mm, 20*mm, 25*mm, 70*mm])
            t_cr_style = [
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LINEBELOW', (0,0), (-1,0), 0.5, BORDER),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('LEFTPADDING', (0,0), (0,-1), 0),
            ]
            
            # Span fix rows properly
            # In cr_data we appended a row for criteria. Then if fix, we append another row.
            
            row_idx = 1
            for i, cr in enumerate(cr_list):
                if cr.get("recommended_fix"):
                    t_cr_style.append(('SPAN', (0, row_idx+1), (-1, row_idx+1)))
                    t_cr_style.append(('BACKGROUND', (0, row_idx+1), (-1, row_idx+1), AMBER_BG))
                    t_cr_style.append(('TOPPADDING', (0, row_idx+1), (-1, row_idx+1), 2))
                    row_idx += 2
                else:
                    row_idx += 1
                    
            t_cr.setStyle(TableStyle(t_cr_style))
            story.append(t_cr)
            story.append(Spacer(1, 6*mm))
            
        warns = dr.get("warnings", [])
        if warns:
            warn_p = []
            warn_p.append(Paragraph("Warnings", ParagraphStyle('w_h', fontName='Helvetica-Bold', fontSize=9, textColor=AMBER)))
            for w in warns:
                warn_p.append(Paragraph(str(w), styles['Normal_INK']))
                
            w_block = [[var] for var in warn_p]
            t_w = Table(w_block, colWidths=[185*mm])
            t_w.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), AMBER_BG),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,-1), (-1,-1), 6),
            ]))
            story.append(t_w)
            story.append(Spacer(1, 6*mm))
            
        story.append(SectionDivider(185*mm))
        
    story.append(Spacer(1, 10*mm))
    
    # Section 6 — Recommended actions
    story.append(Paragraph("Recommended Actions", styles['H2_BRAND']))
    story.append(Spacer(1, 3*mm))
    
    actions = llm_data.get("actions", [])
    if actions:
        # Sort by priority
        pri_map = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        actions.sort(key=lambda x: pri_map.get(str(x.get("priority", "low")).upper(), 4))
        
        for a in actions:
            pri = str(a.get("priority", "low")).upper()
            dom = str(a.get("domain", "all")).capitalize()
            ttl = str(a.get("title", ""))
            det = str(a.get("detail", ""))
            
            p_fg, p_bg = MUTED, BG_SUBTLE
            if pri == "CRITICAL": p_fg, p_bg = RED, RED_BG
            elif pri == "HIGH": p_fg, p_bg = AMBER, AMBER_BG
            elif pri == "MEDIUM": p_fg, p_bg = BLUE, BLUE_BG
            
            d_col, d_bg = get_domain_colors(dom)
            
            a_data = [[
                StatusPill(pri, p_fg, p_bg, width=22*mm, height=14),
                Paragraph(dom, ParagraphStyle('ac_d', fontName='Helvetica-Bold', fontSize=8, textColor=d_col)),
                Paragraph(f"<b>{ttl}</b><br/><font color='{MUTED.hexval()}'>{det}</font>", styles['Normal_INK'])
            ]]
            t_a = Table(a_data, colWidths=[25*mm, 25*mm, 135*mm])
            t_a.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('LINEBELOW', (0,0), (-1,-1), 0.5, BORDER),
                ('PADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('LEFTPADDING', (0,0), (0,-1), 0),
            ]))
            story.append(t_a)
    else:
        story.append(Paragraph("No critical actions recommended.", styles['Normal_MUTED']))
        
    story.append(Spacer(1, 15*mm))
    
    # Section 7 — Report integrity block
    story.append(Paragraph("Report Integrity", styles['BOLD']))
    story.append(Spacer(1, 2*mm))
    
    ri_data = [
        [Paragraph("Submission Hash:", styles['LABEL']), Paragraph(sub_hash, ParagraphStyle('mono', fontName='Courier', fontSize=8, textColor=INK))],
        [Paragraph("Evaluated At:", styles['LABEL']), Paragraph(evaluated_at, styles['Normal_INK'])],
        [Paragraph("Agent Tier:", styles['LABEL']), Paragraph(tier, styles['Normal_INK'])],
        [Paragraph("Idempotency:", styles['LABEL']), Paragraph("Result is deterministic for this submission state.", styles['Normal_INK'])],
    ]
    t_ri = Table(ri_data, colWidths=[35*mm, 150*mm])
    t_ri.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('PADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING', (0,0), (0,-1), 0),
    ]))
    story.append(t_ri)
    story.append(Spacer(1, 10*mm))
    
    # Section 8 — Final verdict card
    vd = llm_data.get("verdict", {})
    verdict_text = str(vd.get("verdict", "Evaluation Complete."))
    pay_action = str(vd.get("payment_action", "Hold payment"))
    
    fv_data = [[
        [Paragraph("FINAL VERDICT", ParagraphStyle('fvl', fontName='Helvetica-Bold', fontSize=8, textColor=dark, spaceAfter=4)),
         Paragraph(verdict_text, ParagraphStyle('fvv', fontName='Helvetica-Bold', fontSize=14, textColor=dark, spaceAfter=4, leading=16)),
         Paragraph(f"Score: {score:.1f}/100", ParagraphStyle('fvp', fontName='Helvetica', fontSize=9, textColor=dark))],
        
        [Paragraph("PAYMENT RECOMMENDATION", ParagraphStyle('fpl', fontName='Helvetica-Bold', fontSize=8, textColor=dark, spaceAfter=4)),
         Paragraph(pay_action.upper(), ParagraphStyle('fpv', fontName='Helvetica-Bold', fontSize=11, textColor=dark))]
    ]]
    
    t_fv = Table(fv_data, colWidths=[110*mm, 75*mm])
    t_fv.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), bg),
        ('BOX', (0,0), (-1,-1), 1, fg),
        ('PADDING', (0,0), (-1,-1), 12),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(t_fv)
    story.append(Spacer(1, 12*mm))
    
    # Closing disclaimer
    disclaimer = ("This report was generated automatically by VaultedEscrow QA Agent. "
                  "All evidence strings are traceable to specific tool outputs. "
                  "The submission hash and report are stored in the VaultedEscrow audit ledger "
                  "and cannot be modified retroactively.")
    story.append(Paragraph(disclaimer, ParagraphStyle('disc', fontName='Helvetica', fontSize=7, textColor=MUTED, alignment=1)))
    
    return story
