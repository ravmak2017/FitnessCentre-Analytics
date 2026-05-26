"""PDF export helpers — markdown reports and Q&A chat transcripts.
Uses ReportLab (pure-Python) so it works on Windows without external binaries.
"""
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Brand-aligned palette (matches theme.py light palette)
_TEXT_HI = colors.HexColor("#0F172A")
_TEXT_MID = colors.HexColor("#334155")
_TEXT_MUTED = colors.HexColor("#64748B")
_ACCENT = colors.HexColor("#0EA5E9")
_ACCENT_DEEP = colors.HexColor("#0369A1")
_BORDER = colors.HexColor("#E2E8F0")
_BG_PANEL = colors.HexColor("#FFFFFF")
_BG_SOFT = colors.HexColor("#F1F5F9")
_USER_BG = colors.HexColor("#E0F2FE")
_BOT_BG = colors.HexColor("#F8FAFC")

_LOGO_PRIMARY = Path(__file__).parent / "assets" / "logo.png"
_LOGO_FALLBACK = Path(__file__).parent / "assets" / "logo.png"


def _logo_path() -> Path | None:
    if _LOGO_PRIMARY.exists():
        return _LOGO_PRIMARY
    if _LOGO_FALLBACK.exists():
        return _LOGO_FALLBACK
    return None


def _make_styles():
    ss = getSampleStyleSheet()
    base = ss["BodyText"]
    return {
        "title": ParagraphStyle(
            "BrandTitle", parent=ss["Title"], fontName="Helvetica-Bold",
            fontSize=22, leading=26, textColor=_TEXT_HI, spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "BrandSubtitle", parent=base, fontName="Helvetica",
            fontSize=10, textColor=_TEXT_MUTED, leading=13, spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "BrandH1", parent=base, fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=_TEXT_HI,
            spaceBefore=14, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "BrandH2", parent=base, fontName="Helvetica-Bold",
            fontSize=14, leading=18, textColor=_ACCENT_DEEP,
            spaceBefore=10, spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "BrandH3", parent=base, fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=_TEXT_HI,
            spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "BrandBody", parent=base, fontName="Helvetica",
            fontSize=10.5, leading=15, textColor=_TEXT_MID,
            spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "BrandBullet", parent=base, fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=_TEXT_MID,
            leftIndent=14, bulletIndent=2, spaceAfter=2,
        ),
        "label": ParagraphStyle(
            "BrandLabel", parent=base, fontName="Helvetica-Bold",
            fontSize=9, leading=11, textColor=_ACCENT_DEEP, spaceAfter=2,
        ),
        "footer": ParagraphStyle(
            "BrandFooter", parent=base, fontName="Helvetica-Oblique",
            fontSize=8, textColor=_TEXT_MUTED, alignment=1,
        ),
    }


_ESC = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def _esc(s: str) -> str:
    return "".join(_ESC.get(ch, ch) for ch in s)


def _inline_md(text: str) -> str:
    """Convert minimal inline markdown (bold, italic, code, links) to ReportLab markup."""
    text = _esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#0369A1">\1</font>', text)
    # Basic markdown link
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                  r'<link href="\2" color="#0369A1"><u>\1</u></link>', text)
    return text


def _markdown_to_flowables(md: str, styles: dict) -> list:
    flow: list = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()

        # Skip code-fence delimiters (render contents as-is monospaced)
        if line.startswith("```"):
            fence_lines = []
            i += 1
            while i < len(lines) and not lines[i].rstrip().startswith("```"):
                fence_lines.append(lines[i])
                i += 1
            if fence_lines:
                joined = "<br/>".join(_esc(x) for x in fence_lines)
                flow.append(Paragraph(
                    f'<font face="Courier" size="9" color="#334155">{joined}</font>',
                    styles["body"],
                ))
            i += 1
            continue

        if not line.strip():
            flow.append(Spacer(1, 4))
            i += 1
            continue

        if line.startswith("# "):
            flow.append(Paragraph(_inline_md(line[2:]), styles["h1"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_inline_md(line[3:]), styles["h2"]))
        elif line.startswith("### "):
            flow.append(Paragraph(_inline_md(line[4:]), styles["h3"]))
        elif line.startswith("---") or line.startswith("***"):
            flow.append(Spacer(1, 4))
            flow.append(HRFlowable(width="100%", color=_BORDER, thickness=0.6))
            flow.append(Spacer(1, 4))
        elif re.match(r"^\s*[-*]\s+", line):
            text = re.sub(r"^\s*[-*]\s+", "", line)
            flow.append(Paragraph(_inline_md(text), styles["bullet"], bulletText="•"))
        elif re.match(r"^\s*\d+\.\s+", line):
            text = re.sub(r"^\s*\d+\.\s+", "", line)
            num_match = re.match(r"^\s*(\d+)\.\s+", raw)
            bullet = f"{num_match.group(1)}." if num_match else "1."
            flow.append(Paragraph(_inline_md(text), styles["bullet"], bulletText=bullet))
        else:
            flow.append(Paragraph(_inline_md(line), styles["body"]))
        i += 1
    return flow


def _header_footer(canvas, doc, footer_text: str):
    canvas.saveState()
    canvas.setFillColor(_TEXT_MUTED)
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.drawCentredString(A4[0] / 2.0, 1.0 * cm,
                             f"{footer_text}  ·  Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _doc_template(buf: io.BytesIO, footer: str) -> SimpleDocTemplate:
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.5 * cm, bottomMargin=1.8 * cm,
        title="ABC Report", author="ABC Fitness Club",
    )
    doc._on_page = lambda c, d: _header_footer(c, d, footer)
    return doc


def _build_header(title: str, subtitle: str, styles: dict) -> list:
    items: list = []
    logo = _logo_path()
    if logo:
        try:
            items.append(Image(str(logo), width=1.4 * cm, height=1.4 * cm))
            items.append(Spacer(1, 4))
        except Exception:
            pass
    items.append(Paragraph(title, styles["title"]))
    if subtitle:
        items.append(Paragraph(subtitle, styles["subtitle"]))
    items.append(HRFlowable(width="100%", color=_ACCENT, thickness=1.2))
    items.append(Spacer(1, 8))
    return items


def markdown_to_pdf(md_text: str, title: str, subtitle: str = "") -> bytes:
    """Convert a markdown report to a styled PDF (returns bytes)."""
    buf = io.BytesIO()
    styles = _make_styles()
    footer = f"ABC Fitness Club ·  · Generated {datetime.now().strftime('%d %b %Y, %H:%M')}"
    doc = _doc_template(buf, footer)
    story = _build_header(title, subtitle, styles)
    story.extend(_markdown_to_flowables(md_text, styles))
    doc.build(story, onFirstPage=lambda c, d: _header_footer(c, d, footer),
              onLaterPages=lambda c, d: _header_footer(c, d, footer))
    return buf.getvalue()


def chat_to_pdf(messages: Iterable[dict], title: str = "Q&A Chat Transcript",
                subtitle: str = "") -> bytes:
    """Convert chat messages (role/content dicts) to a styled PDF (returns bytes)."""
    buf = io.BytesIO()
    styles = _make_styles()
    footer = f"ABC Fitness Club · Q&A Session · {datetime.now().strftime('%d %b %Y, %H:%M')}"
    doc = _doc_template(buf, footer)
    story = _build_header(title, subtitle or footer, styles)

    msg_list = list(messages)
    if not msg_list:
        story.append(Paragraph("(no messages)", styles["body"]))
        doc.build(story)
        return buf.getvalue()

    bubble_user_style = ParagraphStyle(
        "BubbleUser", parent=styles["body"],
        textColor=_ACCENT_DEEP, fontName="Helvetica-Bold", fontSize=10,
    )
    bubble_bot_style = ParagraphStyle(
        "BubbleBot", parent=styles["body"],
        textColor=_TEXT_MID, fontName="Helvetica", fontSize=10.5, leading=14,
    )
    role_label_style = ParagraphStyle(
        "RoleLabel", parent=styles["label"],
        fontSize=8, textColor=_TEXT_MUTED, alignment=0,
    )

    for idx, m in enumerate(msg_list, start=1):
        role = m.get("role", "?")
        content = m.get("content", "")
        is_user = role == "user"
        label = f"#{idx} · {'YOU' if is_user else 'AI ASSISTANT'}"
        bg = _USER_BG if is_user else _BOT_BG
        content_flow = _markdown_to_flowables(content, styles)
        inner = [[Paragraph(label, role_label_style)]]
        for f in content_flow:
            inner.append([f])
        tbl = Table(inner, colWidths=[doc.width - 1.0 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.4, _BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6))

    doc.build(story, onFirstPage=lambda c, d: _header_footer(c, d, footer),
              onLaterPages=lambda c, d: _header_footer(c, d, footer))
    return buf.getvalue()


__all__ = ["markdown_to_pdf", "chat_to_pdf"]
