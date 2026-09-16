#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""md_to_pdf.py - Markdown to PDF using Chrome headless"""

import html as html_lib
import os, re, subprocess, tempfile
import markdown

STYLE_CSS = """
@page { margin: 20mm 25mm; }
body { font-family: "Times New Roman", serif; font-size: 12pt; line-height: 1.6; color: #222; }
h1 { font-size: 20pt; border-bottom: 2px solid #333; }
h2 { font-size: 16pt; }
table { border-collapse: collapse; width: 100%; margin: 15px 0; font-size: 11pt; }
th { background: #f0f0f0; border: 1px solid #999; padding: 8px; text-align: center; }
td { border: 1px solid #999; padding: 6px; text-align: center; }
tr:nth-child(even) { background: #fafafa; }
p { margin: 8px 0; text-align: justify; }
code { font-family: Consolas; background: #f5f5f5; padding: 1px 4px; border-radius: 3px; }
hr { border: none; border-top: 1px solid #ccc; margin: 25px 0; }
"""

def _find_chrome():
    # Edge is preferred on Windows because it is less likely to share the
    # actively used Chrome profile.  A separate temporary profile is still
    # supplied below for deterministic headless export.
    for c in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if os.path.isfile(c): return c
    return "chrome"

def md_to_html(md_text):
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return "<html><head><meta charset=utf-8><style>" + STYLE_CSS + "</style></head><body>" + body + "</body></html>"


def _inline_markup(text):
    text = html_lib.escape(text.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # Keep inline-code paths in the document font so Chinese path segments do
    # not disappear when Courier lacks CJK glyphs.
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _convert_with_reportlab(md_text, pdf_path):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    font_name = "Helvetica"
    for font_path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.isfile(font_path):
            try:
                pdfmetrics.registerFont(TTFont("ReportCJK", font_path, subfontIndex=0))
                font_name = "ReportCJK"
                break
            except Exception:
                continue

    styles = getSampleStyleSheet()
    normal = ParagraphStyle("ReportNormal", parent=styles["BodyText"], fontName=font_name,
                            fontSize=10.5, leading=16, spaceAfter=5)
    bullet = ParagraphStyle("ReportBullet", parent=normal, leftIndent=12, firstLineIndent=-8)
    headings = {
        1: ParagraphStyle("ReportH1", parent=normal, fontSize=20, leading=25,
                          spaceBefore=4, spaceAfter=12, alignment=TA_CENTER),
        2: ParagraphStyle("ReportH2", parent=normal, fontSize=15, leading=20,
                          spaceBefore=12, spaceAfter=7),
        3: ParagraphStyle("ReportH3", parent=normal, fontSize=12.5, leading=17,
                          spaceBefore=9, spaceAfter=5),
    }
    document = SimpleDocTemplate(
        pdf_path, pagesize=A4, rightMargin=20 * mm, leftMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="Experiment Report",
    )
    story = []
    lines = md_text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line == "---":
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#bbbbbb")))
            index += 1
            continue
        if line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            rows = []
            for table_line in table_lines:
                cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    continue
                rows.append([Paragraph(_inline_markup(cell), normal) for cell in cells])
            if rows:
                table = Table(rows, repeatRows=1, hAlign="LEFT")
                table.setStyle(TableStyle([
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(table)
            continue
        heading_match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            story.append(Paragraph(_inline_markup(heading_match.group(2)), headings[level]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + _inline_markup(line[2:]), bullet))
        else:
            story.append(Paragraph(_inline_markup(line), normal))
        index += 1
    document.build(story)

def convert_md_file(md_path, pdf_path):
    with open(md_path, encoding="utf-8") as f: md_text = f.read()
    html = md_to_html(md_text)
    os.makedirs(os.path.dirname(os.path.abspath(pdf_path)), exist_ok=True)
    try:
        _convert_with_reportlab(md_text, pdf_path)
    except ImportError:
        pass
    else:
        if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) == 0:
            raise RuntimeError(f"ReportLab did not create a PDF: {pdf_path}")
        return pdf_path

    with tempfile.TemporaryDirectory(prefix="clean_number_pdf_") as temp_dir:
        html_path = os.path.join(temp_dir, "report.html")
        profile_dir = os.path.join(temp_dir, "browser-profile")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        cmd = [
            _find_chrome(), "--headless=new", "--disable-gpu",
            "--disable-extensions", "--no-first-run",
            "--no-default-browser-check", "--no-margins",
            "--user-data-dir=" + profile_dir,
            "--print-to-pdf=" + os.path.abspath(pdf_path),
            "file:///" + html_path.replace("\\", "/"),
        ]
        completed = subprocess.run(cmd, capture_output=True, timeout=60)
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"PDF browser export failed ({completed.returncode}): {message}")
    if not os.path.isfile(pdf_path) or os.path.getsize(pdf_path) == 0:
        raise RuntimeError(f"PDF browser export did not create a file: {pdf_path}")
    return pdf_path

if __name__ == "__main__":
    import sys
    convert_md_file(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else sys.argv[1].replace(".md",".pdf"))
    print("PDF:", sys.argv[1].replace(".md",".pdf"))
