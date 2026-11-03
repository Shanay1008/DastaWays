from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import ReadinessReport

NAVY = colors.HexColor("#173638")
TEAL = colors.HexColor("#39746D")
MUTED = colors.HexColor("#687A75")
PALE = colors.HexColor("#F1F5F1")
LINE = colors.HexColor("#DDE5DE")
STATUS_COLORS = {
    "VERIFIED": colors.HexColor("#367252"),
    "MISSING": colors.HexColor("#A34F40"),
    "UNCERTAIN": colors.HexColor("#8B7137"),
    "NOT_APPLICABLE": colors.HexColor("#707C76"),
}


def _text(value: object) -> str:
    """Escape user/report text for ReportLab's paragraph markup."""
    normalized = str(value).replace("\u2019", "'").replace("\u2018", "'")
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-").replace("\u2011", "-")
    normalized = normalized.replace("\u2026", "...")
    return escape(normalized).replace("\n", "<br/>")


def render_readiness_report(report: ReadinessReport, profile: dict) -> bytes:
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BrandTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=22, leading=26, textColor=NAVY, alignment=0, spaceAfter=3))
    styles.add(ParagraphStyle(name="Tagline", parent=styles["Normal"], fontName="Helvetica",
                              fontSize=9, leading=13, textColor=MUTED, spaceAfter=12))
    styles.add(ParagraphStyle(name="SectionTitle", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=16, textColor=NAVY, spaceBefore=12, spaceAfter=7,
                              keepWithNext=True))
    styles.add(ParagraphStyle(name="BodyDW", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=9, leading=13, textColor=NAVY, spaceAfter=2))
    styles.add(ParagraphStyle(name="SmallDW", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=7.5, leading=10, textColor=MUTED))
    styles.add(ParagraphStyle(name="StatusDW", parent=styles["BodyText"], fontName="Helvetica-Bold",
                              fontSize=8, leading=10, alignment=TA_CENTER, textColor=colors.white))
    def page_chrome(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 10 * mm, width, 10 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(18 * mm, height - 6.7 * mm, "DASTAWAYS")
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(width - 18 * mm, height - 6.7 * mm, "APPLICATION READINESS REPORT")
        canvas.setStrokeColor(LINE)
        canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(18 * mm, 10 * mm, "Advisory demo report - not an official eligibility decision")
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                            topMargin=17 * mm, bottomMargin=21 * mm,
                            title="DastaWays Application Readiness Report",
                            author="DastaWays")
    story = [
        Paragraph("Readiness report", styles["BrandTitle"]),
        Paragraph("From paperwork to possibilities.", styles["Tagline"]),
    ]

    overall_color = STATUS_COLORS.get(report.overall_status, TEAL)
    overall = Table([[Paragraph(_text(report.overall_status.replace("_", " ")), styles["StatusDW"]),
                      Paragraph("SYNTHETIC DEMO - advisory only", styles["BodyDW"])]],
                    colWidths=[43 * mm, 120 * mm])
    overall.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), overall_color),
        ("BACKGROUND", (1, 0), (1, 0), PALE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([overall, Spacer(1, 5 * mm), Paragraph("Applicant and scheme", styles["SectionTitle"])])

    fields = [
        ("Applicant", profile.get("applicant_name", "Not provided")),
        ("Education", profile.get("education_level", "Not provided")),
        ("Course", profile.get("course", "Not provided")),
        ("Academic year", profile.get("academic_year", "Not provided")),
        ("Scheme", "DastaWays Sample Scholarship (synthetic demo)"),
        ("Generated", report.generated_at.strftime("%Y-%m-%d %H:%M UTC")),
    ]
    profile_table = Table([[Paragraph(f"<b>{_text(label)}</b>", styles["SmallDW"]),
                            Paragraph(_text(value), styles["BodyDW"])] for label, value in fields],
                          colWidths=[35 * mm, 128 * mm])
    profile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), PALE),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([profile_table, Paragraph("Requirement review", styles["SectionTitle"])])

    for item in report.requirements:
        color = STATUS_COLORS.get(item.status, TEAL)
        top = Table([[Paragraph(_text(item.status.replace("_", " ")), styles["StatusDW"]),
                      Paragraph(f"<b>{_text(item.title)}</b>", styles["BodyDW"])]],
                    colWidths=[32 * mm, 117 * mm])
        top.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), color),
            ("BACKGROUND", (1, 0), (1, 0), PALE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        explanation = Paragraph(_text(item.explanation), styles["BodyDW"])
        evidence = Paragraph("Evidence references: " + _text(", ".join(item.evidence_documents) or "None attached"), styles["SmallDW"])
        block = Table([[[top, explanation, evidence]]], colWidths=[163 * mm], splitByRow=0)
        block.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, LINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(KeepTogether([block, Spacer(1, 2.5 * mm)]))

    story.append(Paragraph("Suggested next steps", styles["SectionTitle"]))
    for index, step in enumerate(report.next_steps, start=1):
        story.append(Paragraph(f"<b>{index}.</b> {_text(step)}", styles["BodyDW"]))
        story.append(Spacer(1, 2 * mm))
    story.extend([Spacer(1, 4 * mm), Paragraph(_text(report.disclaimer), styles["SmallDW"])])
    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
    return output.getvalue()
