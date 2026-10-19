import io
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle


def _clean(v):
    """Standard PDF fonts are Latin-1 only: emoji / non-Latin characters are dropped."""
    s = "" if v is None else str(v)
    return s.encode("latin-1", "ignore").decode("latin-1").strip()


def table_pdf(title, subtitle, headers, rows):
    buf = io.BytesIO()
    size = landscape(A4) if len(headers) > 6 else A4
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=_clean(title))
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=8, leading=10)
    head = ParagraphStyle("head", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")

    story = [Paragraph(escape(_clean(title)), styles["Title"])]
    if subtitle:
        story.append(Paragraph(escape(_clean(subtitle)), styles["Normal"]))
    story.append(Paragraph(f"Generated {datetime.now():%d %b %Y, %I:%M %p} - SnapClass", styles["Italic"]))
    story.append(Spacer(1, 8 * mm))

    if not rows:
        story.append(Paragraph("No data.", styles["Normal"]))
    else:
        data = [[Paragraph(escape(_clean(h)), head) for h in headers]]
        for r in rows:
            data.append([Paragraph(escape(_clean(c)), cell) for c in r])
        avail = size[0] - 28 * mm
        table = Table(data, repeatRows=1, colWidths=[avail / len(headers)] * len(headers))
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5865F2")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F3FF")]),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CCF5")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(table)

    doc.build(story)
    return buf.getvalue()


def df_pdf(df, title, subtitle=""):
    headers = [str(c) for c in df.columns]
    rows = df.fillna("").astype(str).values.tolist()
    return table_pdf(title, subtitle, headers, rows)


def sections_pdf(title, meta_lines, sections):
    """sections: list of {heading, headers, rows} (table) or {heading, lines} (text)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm, title=_clean(title))
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("cell2", parent=styles["BodyText"], fontSize=8, leading=10)
    head = ParagraphStyle("head2", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    story = [Paragraph(escape(_clean(title)), styles["Title"])]
    for line in meta_lines:
        story.append(Paragraph(escape(_clean(line)), styles["Normal"]))
    story.append(Paragraph(f"Generated {datetime.now():%d %b %Y, %I:%M %p} - SnapClass", styles["Italic"]))
    story.append(Spacer(1, 6 * mm))
    avail = A4[0] - 28 * mm
    for sec in sections:
        story.append(Paragraph(escape(_clean(sec["heading"])), styles["Heading3"]))
        if "image" in sec:
            try:
                from reportlab.platypus import Image as RLImage
                from PIL import Image as PILImage
                w, h = PILImage.open(io.BytesIO(sec["image"])).size
                width = min(avail, 170 * mm)
                story.append(RLImage(io.BytesIO(sec["image"]), width=width, height=width * h / w))
            except Exception:
                story.append(Paragraph("Chart image could not be embedded.", cell))
        elif "lines" in sec:
            for ln in sec["lines"]:
                story.append(Paragraph(escape(_clean(ln)), cell))
        elif not sec["rows"]:
            story.append(Paragraph("No data.", cell))
        else:
            headers = sec["headers"]
            data = [[Paragraph(escape(_clean(h)), head) for h in headers]]
            for r in sec["rows"]:
                data.append([Paragraph(escape(_clean(c)), cell) for c in r])
            table = Table(data, repeatRows=1, colWidths=[avail / len(headers)] * len(headers))
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5865F2")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F3FF")]),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CCF5")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            story.append(table)
        story.append(Spacer(1, 5 * mm))
    doc.build(story)
    return buf.getvalue()
