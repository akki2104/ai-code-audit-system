"""Convert INTERVIEW_PREP.md to PDF reusing the existing converter logic."""
import os
import re
from fpdf import FPDF

SRC = r"c:\Users\Akash Yadav\Desktop\gen-z-on services\domaindatams\Afters\multi-agent\code-audit-agent\INTERVIEW_PREP.md"
DST = r"c:\Users\Akash Yadav\Desktop\gen-z-on services\domaindatams\Afters\multi-agent\code-audit-agent\INTERVIEW_PREP.pdf"


UNICODE_MAP = {
    '\u2014': '--',   # em dash
    '\u2013': '-',    # en dash
    '\u2018': "'",    # left single quote
    '\u2019': "'",    # right single quote
    '\u201c': '"',    # left double quote
    '\u201d': '"',    # right double quote
    '\u2026': '...',  # ellipsis
    '\u2192': '->',   # right arrow
    '\u2190': '<-',   # left arrow
    '\u2264': '<=',   # less than or equal
    '\u2265': '>=',   # greater than or equal
    '\u2260': '!=',   # not equal
    '\u00d7': 'x',    # multiplication sign
    '\u2248': '~=',   # approximately equal
    '\u221e': 'inf',  # infinity
    '\u2211': 'Sum',  # summation
    '\u2202': 'd',    # partial derivative
    '\u25b6': '>',    # right-pointing triangle
    '\u25bc': 'v',    # down-pointing triangle
    '\u25cf': '*',    # black circle
    '\u2588': '#',    # full block
    '\u2502': '|',    # box drawing vertical
    '\u2500': '-',    # box drawing horizontal
    '\u250c': '+',    # box drawing corner
    '\u2510': '+',
    '\u2514': '+',
    '\u2518': '+',
    '\u251c': '+',
    '\u2524': '+',
    '\u252c': '+',
    '\u2534': '+',
    '\u253c': '+',
    '\u2591': '.',    # light shade
    '\u25a0': '#',    # black square
    '\u25a1': '[ ]',  # white square
    '\u2610': '[ ]',  # ballot box
    '\u2611': '[x]',  # ballot box with check
    '\u2713': '[x]',  # check mark
    '\u2717': '[X]',  # cross mark
    '\u274c': '[X]',  # cross mark
    '\u2705': '[v]',  # white check mark
    '\u23f3': '(time)',  # hourglass
    '\u2b50': '*',    # star
    '\u26a0': '(!)',  # warning
    '\U0001f4cb': '',  # clipboard
}


def sanitize(text):
    """Replace Unicode chars unsupported by Helvetica with ASCII equivalents."""
    # Remove emoji (supplementary plane)
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    for k, v in UNICODE_MAP.items():
        text = text.replace(k, v)
    # Replace any remaining non-latin1 chars
    result = []
    for ch in text:
        try:
            ch.encode('latin-1')
            result.append(ch)
        except UnicodeEncodeError:
            result.append('?')
    return ''.join(result)


class MarkdownPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        self.add_page()
        self.set_margins(15, 15, 15)
        self._anchors = {}  # anchor_name -> link_id

    def _make_anchor(self, text):
        """Convert heading text to a slug matching markdown anchor format."""
        slug = text.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        slug = slug.strip('-')
        return slug

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def add_heading(self, text, level):
        sizes = {1: 18, 2: 15, 3: 13, 4: 11}
        colors = {1: (26, 60, 110), 2: (42, 93, 159), 3: (58, 123, 200), 4: (80, 80, 80)}
        size = sizes.get(level, 11)
        color = colors.get(level, (0, 0, 0))
        text = re.sub(r'[🟢🟡🔴]', '', text).strip()
        text = text.lstrip('#').strip()
        # Create anchor for this heading
        anchor = self._make_anchor(text)
        text = sanitize(text)
        if level <= 2:
            self.ln(4)
        self.set_font("Helvetica", "B", size)
        self.set_text_color(*color)
        # Place a named destination (anchor) at this position
        if anchor:
            if anchor in self._anchors:
                # TOC already created a forward-reference link; now set its destination
                self.set_link(self._anchors[anchor], y=self.get_y(), page=self.page)
            else:
                link_id = self.add_link()
                self.set_link(link_id, y=self.get_y(), page=self.page)
                self._anchors[anchor] = link_id
        self.multi_cell(0, size * 0.6, text)
        if level <= 2:
            self.set_draw_color(*color)
            self.set_line_width(0.5 if level == 1 else 0.3)
            self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
            self.ln(2)
        self.ln(2)

    def add_text(self, text):
        text = sanitize(text)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        parts = re.split(r'(\*\*.*?\*\*)', text)
        for part in parts:
            if part.startswith('**') and part.endswith('**'):
                self.set_font("Helvetica", "B", 10)
                self.write(5, part[2:-2])
                self.set_font("Helvetica", "", 10)
            else:
                self.write(5, part)
        self.ln(5)

    def add_code_block(self, code):
        code = sanitize(code)
        self.set_fill_color(40, 40, 40)
        self.set_text_color(212, 212, 212)
        self.set_font("Courier", "", 8)
        y = self.get_y()
        lines = code.split('\n')
        block_h = len(lines) * 4 + 6
        if y + block_h > self.h - 20:
            self.add_page()
            y = self.get_y()
        self.rect(self.l_margin, y, self.w - self.l_margin - self.r_margin, block_h, 'F')
        self.set_xy(self.l_margin + 3, y + 3)
        for i, line in enumerate(lines):
            max_chars = 105
            if len(line) > max_chars:
                line = line[:max_chars] + "..."
            self.cell(0, 4, line)
            if i < len(lines) - 1:
                self.ln(4)
                self.set_x(self.l_margin + 3)
        self.ln(8)
        self.set_text_color(30, 30, 30)

    def add_table(self, header, rows):
        header = [sanitize(h) for h in header]
        rows = [[sanitize(c) for c in row] for row in rows]
        self.set_font("Helvetica", "", 8)
        n_cols = len(header)
        avail = self.w - self.l_margin - self.r_margin
        col_w = avail / n_cols
        if col_w < 15:
            col_w = 15

        self.set_fill_color(42, 93, 159)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        for h in header:
            txt = h.strip()[:int(col_w / 1.8)]
            self.cell(col_w, 6, txt, border=1, fill=True)
        self.ln()

        self.set_font("Helvetica", "", 7.5)
        for i, row in enumerate(rows):
            if self.get_y() > self.h - 25:
                self.add_page()
            if i % 2 == 0:
                self.set_fill_color(244, 247, 251)
            else:
                self.set_fill_color(255, 255, 255)
            self.set_text_color(30, 30, 30)
            for cell in row:
                txt = cell.strip()
                max_c = int(col_w / 1.6)
                if len(txt) > max_c:
                    txt = txt[:max_c - 2] + ".."
                self.cell(col_w, 5.5, txt, border=1, fill=True)
            self.ln()
        self.ln(3)

    def add_hr(self):
        self.set_draw_color(200, 200, 200)
        self.set_line_width(0.3)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def add_toc_entry(self, number, display_text, anchor):
        """Render a clickable TOC line that links to an internal anchor."""
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        prefix = f"{number}. "
        self.write(6, prefix)
        # Write the link text in blue
        self.set_text_color(42, 93, 159)
        self.set_font("Helvetica", "U", 10)
        # Lookup or pre-create anchor link
        if anchor not in self._anchors:
            link_id = self.add_link()
            self._anchors[anchor] = link_id
        self.write(6, sanitize(display_text), self._anchors[anchor])
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.ln(6)

    def add_bullet(self, text, indent=0):
        text = sanitize(text)
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(30, 30, 30)
        x = self.l_margin + indent * 5
        self.set_x(x)
        bullet = "*  " if indent == 0 else "-  "
        clean = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
        clean = re.sub(r'`(.*?)`', r'\1', clean)
        self.multi_cell(self.w - x - self.r_margin, 5, bullet + clean)
        self.ln(1)


def parse_and_render(pdf, md_text):
    lines = md_text.split('\n')
    i = 0
    in_code = False
    code_buf = []
    in_table = False
    table_header = []
    table_rows = []

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith('```'):
            if in_code:
                pdf.add_code_block('\n'.join(code_buf))
                code_buf = []
                in_code = False
            else:
                if in_table:
                    pdf.add_table(table_header, table_rows)
                    in_table = False
                    table_header = []
                    table_rows = []
                in_code = True
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if all(re.match(r'^[-: ]+$', c) for c in cells):
                i += 1
                continue
            if not in_table:
                in_table = True
                table_header = cells
            else:
                table_rows.append(cells)
            i += 1
            continue
        else:
            if in_table:
                pdf.add_table(table_header, table_rows)
                in_table = False
                table_header = []
                table_rows = []

        stripped = line.strip()

        if stripped.startswith('#'):
            m = re.match(r'^(#{1,4})\s+(.*)', stripped)
            if m:
                level = len(m.group(1))
                pdf.add_heading(m.group(2), level)
                i += 1
                continue

        if stripped in ('---', '***', '___') and len(stripped) >= 3:
            pdf.add_hr()
            i += 1
            continue

        if re.match(r'^[-*]\s', stripped):
            text = re.sub(r'^[-*]\s+', '', stripped)
            pdf.add_bullet(text, indent=0)
            i += 1
            continue

        if re.match(r'^\s{2,}[-*]\s', line):
            text = re.sub(r'^\s+[-*]\s+', '', line)
            pdf.add_bullet(text, indent=1)
            i += 1
            continue

        if re.match(r'^\d+\.\s', stripped):
            # Check if it's a TOC entry like "1. [Display Text](#anchor)"
            toc_match = re.match(r'^(\d+)\.\s+\[(.+?)\]\(#(.+?)\)', stripped)
            if toc_match:
                number = toc_match.group(1)
                display_text = toc_match.group(2)
                anchor = toc_match.group(3)
                pdf.add_toc_entry(number, display_text, anchor)
                i += 1
                continue
            text = re.sub(r'^\d+\.\s+', '', stripped)
            pdf.add_bullet(text, indent=0)
            i += 1
            continue

        if stripped.startswith('>'):
            text = stripped.lstrip('>').strip()
            text = sanitize(text)
            pdf.set_font("Helvetica", "I", 9.5)
            pdf.set_text_color(80, 80, 80)
            pdf.set_x(pdf.l_margin + 5)
            pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 5, 5, text)
            pdf.ln(2)
            i += 1
            continue

        if not stripped:
            pdf.ln(2)
            i += 1
            continue

        pdf.add_text(stripped)
        i += 1

    if in_code:
        pdf.add_code_block('\n'.join(code_buf))
    if in_table:
        pdf.add_table(table_header, table_rows)


if __name__ == "__main__":
    with open(SRC, encoding="utf-8") as f:
        md_text = f.read()

    pdf = MarkdownPDF()
    pdf.alias_nb_pages()
    parse_and_render(pdf, md_text)
    pdf.output(DST)
    print(f"PDF saved to: {DST}")
