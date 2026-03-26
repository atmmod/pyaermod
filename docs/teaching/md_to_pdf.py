#!/usr/bin/env python3
"""Convert student-guide.md to a well-formatted PDF using reportlab."""

import re
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, grey
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable,
)


def build_styles():
    """Create all paragraph styles used in the document."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "DocTitle",
        parent=styles["Title"],
        fontSize=22,
        leading=28,
        spaceAfter=6,
        textColor=HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=12,
        leading=16,
        spaceAfter=12,
        textColor=HexColor("#555555"),
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontSize=18,
        leading=24,
        spaceBefore=24,
        spaceAfter=10,
        textColor=HexColor("#1a1a2e"),
    ))
    styles.add(ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontSize=15,
        leading=20,
        spaceBefore=18,
        spaceAfter=8,
        textColor=HexColor("#2d3a4a"),
    ))
    styles.add(ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontSize=13,
        leading=17,
        spaceBefore=14,
        spaceAfter=6,
        textColor=HexColor("#3a4a5a"),
    ))
    styles.add(ParagraphStyle(
        "H4",
        parent=styles["Heading4"],
        fontSize=11,
        leading=15,
        spaceBefore=10,
        spaceAfter=4,
        textColor=HexColor("#4a5a6a"),
    ))
    styles.add(ParagraphStyle(
        "BodyText2",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "BulletItem",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        leftIndent=20,
        bulletIndent=8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "NumberedItem",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        leftIndent=20,
        bulletIndent=8,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "CodeBlock",
        parent=styles["Code"],
        fontSize=8.5,
        leading=11,
        leftIndent=12,
        rightIndent=12,
        spaceBefore=4,
        spaceAfter=4,
        backColor=HexColor("#f5f5f5"),
        borderColor=HexColor("#dddddd"),
        borderWidth=0.5,
        borderPadding=6,
        fontName="Courier",
    ))
    styles.add(ParagraphStyle(
        "BlockQuote",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        leftIndent=20,
        rightIndent=12,
        spaceBefore=6,
        spaceAfter=6,
        textColor=HexColor("#555555"),
        borderColor=HexColor("#cccccc"),
        borderWidth=0,
        borderPadding=4,
    ))
    styles.add(ParagraphStyle(
        "CheckItem",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        leftIndent=20,
        spaceAfter=2,
    ))
    return styles


def escape_xml(text):
    """Escape XML special characters for reportlab Paragraph."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def format_inline(text):
    """Convert markdown inline formatting to reportlab XML tags."""
    # Bold+italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    # Inline code
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9">\1</font>', text)
    # Links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def parse_table(lines):
    """Parse markdown table lines into a list of rows (each row is a list of cells)."""
    rows = []
    for line in lines:
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            # Skip separator rows
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue
            rows.append(cells)
    return rows


def make_table_flowable(rows, styles):
    """Convert parsed table rows into a reportlab Table."""
    if not rows:
        return None

    cell_style = ParagraphStyle(
        "TableCell",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
    )
    header_style = ParagraphStyle(
        "TableHeader",
        parent=cell_style,
        fontName="Helvetica-Bold",
    )

    table_data = []
    for i, row in enumerate(rows):
        style = header_style if i == 0 else cell_style
        table_data.append([Paragraph(format_inline(c), style) for c in row])

    ncols = max(len(r) for r in table_data)
    # Pad short rows
    for row in table_data:
        while len(row) < ncols:
            row.append(Paragraph("", cell_style))

    avail_width = letter[0] - 2 * inch
    col_width = avail_width / ncols

    t = Table(table_data, colWidths=[col_width] * ncols)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e8edf2")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#1a1a2e")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#ffffff"), HexColor("#f9f9f9")]),
    ]))
    return t


def convert_md_to_pdf(md_path, pdf_path):
    """Main conversion function."""
    md_text = Path(md_path).read_text(encoding="utf-8")
    lines = md_text.split("\n")

    styles = build_styles()
    story = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            i += 1
            continue

        # Horizontal rules -> page section divider
        if re.match(r"^---+$", stripped):
            story.append(Spacer(1, 6))
            story.append(HRFlowable(
                width="100%", thickness=1,
                color=HexColor("#cccccc"), spaceAfter=6, spaceBefore=6,
            ))
            i += 1
            continue

        # Headings
        heading_match = re.match(r"^(#{1,4})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()

            # Special case: main title
            if level == 1 and i < 5:
                story.append(Spacer(1, 40))
                story.append(Paragraph(format_inline(text), styles["DocTitle"]))
                # Check for subtitle line
                if i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].strip().startswith("#"):
                    i += 1
                    # Collect subtitle lines until empty line
                    subtitle_lines = []
                    while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith("#"):
                        subtitle_lines.append(lines[i].strip())
                        i += 1
                    story.append(Paragraph(
                        format_inline(" ".join(subtitle_lines)),
                        styles["Subtitle"],
                    ))
                    continue
                i += 1
                continue

            style_name = {1: "H1", 2: "H2", 3: "H3", 4: "H4"}.get(level, "H4")

            # Add page break before major sections
            if level == 2 and len(story) > 3:
                story.append(PageBreak())

            story.append(Paragraph(format_inline(text), styles[style_name]))
            i += 1
            continue

        # Code blocks
        if stripped.startswith("```"):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            code_text = escape_xml("\n".join(code_lines))
            code_text = code_text.replace("\n", "<br/>")
            code_text = code_text.replace("  ", "&nbsp;&nbsp;")
            story.append(Paragraph(code_text, styles["CodeBlock"]))
            continue

        # Tables
        if stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            rows = parse_table(table_lines)
            tbl = make_table_flowable(rows, styles)
            if tbl:
                story.append(Spacer(1, 4))
                story.append(tbl)
                story.append(Spacer(1, 4))
            continue

        # Blockquotes
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and (lines[i].strip().startswith(">") or
                                       (lines[i].strip() and not lines[i].strip().startswith("#") and
                                        not lines[i].strip().startswith("|") and
                                        i > 0 and lines[i - 1].strip().startswith(">"))):
                text = lines[i].strip().lstrip("> ").strip()
                quote_lines.append(text)
                i += 1
            quote_text = format_inline(" ".join(quote_lines))
            # Add left-bar styling via indentation
            story.append(Paragraph(
                f'<font color="#888888">|</font>&nbsp;&nbsp;{quote_text}',
                styles["BlockQuote"],
            ))
            continue

        # Checkbox items
        if re.match(r"^-\s+\[[ x]\]\s+", stripped):
            check_match = re.match(r"^-\s+\[([ x])\]\s+(.*)", stripped)
            if check_match:
                checked = check_match.group(1) == "x"
                text = check_match.group(2)
                marker = "<font color='#22aa22'>&#x2713;</font>" if checked else "&#x2610;"
                story.append(Paragraph(
                    f"{marker}&nbsp;&nbsp;{format_inline(text)}",
                    styles["CheckItem"],
                ))
            i += 1
            continue

        # Numbered lists
        num_match = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if num_match:
            num = num_match.group(1)
            text = num_match.group(2)
            # Collect continuation lines (indented)
            i += 1
            while i < len(lines) and lines[i].startswith("   ") and not re.match(r"^\d+\.", lines[i].strip()):
                text += " " + lines[i].strip()
                i += 1
            story.append(Paragraph(
                f"<b>{num}.</b>&nbsp;&nbsp;{format_inline(text)}",
                styles["NumberedItem"],
            ))
            continue

        # Bullet lists
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = stripped[2:]
            i += 1
            # Collect continuation lines
            while i < len(lines) and lines[i].startswith("  ") and not lines[i].strip().startswith("- "):
                text += " " + lines[i].strip()
                i += 1
            story.append(Paragraph(
                format_inline(text),
                styles["BulletItem"],
                bulletText="  \u2022",
            ))
            continue

        # Regular paragraph - collect until empty line or special line
        para_lines = [stripped]
        i += 1
        while (i < len(lines) and lines[i].strip()
               and not lines[i].strip().startswith("#")
               and not lines[i].strip().startswith("|")
               and not lines[i].strip().startswith(">")
               and not lines[i].strip().startswith("```")
               and not lines[i].strip().startswith("- ")
               and not lines[i].strip().startswith("* ")
               and not re.match(r"^---+$", lines[i].strip())
               and not re.match(r"^\d+\.\s+", lines[i].strip())):
            para_lines.append(lines[i].strip())
            i += 1

        text = " ".join(para_lines)
        story.append(Paragraph(format_inline(text), styles["BodyText2"]))

    # Build PDF
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="Introduction to Air Dispersion Modeling with PyAERMOD",
        author="PyAERMOD",
    )

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(grey)
        page_num = canvas.getPageNumber()
        text = f"PyAERMOD Student Guide  —  Page {page_num}"
        canvas.drawCentredString(letter[0] / 2.0, 0.5 * inch, text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"PDF created: {pdf_path}")


if __name__ == "__main__":
    base = Path(__file__).parent
    convert_md_to_pdf(
        base / "student-guide.md",
        base / "student-guide.pdf",
    )
