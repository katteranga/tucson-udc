#!/usr/bin/env python3
"""Rebuild the UDC tables in docs/ from the American Legal HTML export.

The export flattens each table into one paragraph per cell. This script reads
the real table structure from tucson-az-2.html, finds each table's flattened
text in the matching docs/ section, and replaces it with:

- a Markdown pipe table, when the table body has no merged cells and at most
  one header row; or
- a minimal HTML table (one cell per line, no styling) otherwise.

Full-width rows at the top of a table (its title) become a bold line above
it, and full-width rows at the bottom (notes) become paragraphs below it.

A table is only replaced when the flattened text matches the export word for
word, so the result still passes tools/verify_baseline.py. Anything that
cannot be matched is listed for manual work.

Usage:
    python3 tools/convert_tables.py [--source tucson-az-2.html]
        [--docs docs/unified_development_code] [--dry-run]
"""

import argparse
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_baseline as vb  # noqa: E402


class Cell:
    def __init__(self, colspan, rowspan):
        self.colspan, self.rowspan = colspan, rowspan
        self.paragraphs = [[]]   # each paragraph is a list of text/image parts
        self.header = False
        self.images = []

    def text_paragraphs(self):
        out = []
        for parts in self.paragraphs:
            text = re.sub(r"\s+", " ", "".join(parts)).strip()
            if text:
                out.append(text)
        return out

    def plain(self):
        return " ".join(self.text_paragraphs())


class Table:
    def __init__(self, section, sticky=False):
        self.section = section
        self.sticky = sticky     # American Legal's duplicate sticky-header copy
        self.rows = []
        self.ncols = 0

    def tokens(self):
        """Tokens in the same order verify_baseline reads them."""
        toks = []
        for row in self.rows:
            for cell in row:
                for para in cell.text_paragraphs():
                    for k, piece in enumerate(IMG_RE.split(para)):
                        if k % 2:    # odd pieces are image sources
                            toks.append(f"[image:{piece.rsplit('/', 1)[-1]}]")
                        else:
                            toks += vb.TOKEN_RE.findall(vb.normalize(piece))
        return toks


class TableParser(HTMLParser):
    """Collect tables and the UDC section each one appears in."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section = None
        self.tables = []
        self.table = None
        self.cell = None
        self.divs = []           # True for each open xsl-table--header div

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        m = vb.SECTION_ID_RE.match(a.get("id") or "")
        if m:
            self.section = m.group(1)
        elif a.get("id") == "JD_UDCPROrdinances":
            self.section = vb.REFERENCES
        if tag == "div" and self.table is None:
            self.divs.append("xsl-table--header" in (a.get("class") or "").split())
        if tag == "table" and self.section:
            self.table = Table(self.section, sticky=any(self.divs))
        elif self.table is None:
            return
        elif tag == "col":
            self.table.ncols += 1
        elif tag == "tr":
            self.table.rows.append([])
        elif tag == "td":
            self.cell = Cell(int(a.get("colspan") or 1), int(a.get("rowspan") or 1))
            self.table.rows[-1].append(self.cell)
        elif self.cell is not None:
            if tag == "div":
                if "Table-Header" in (a.get("class") or ""):
                    self.cell.header = True
                if self.cell.paragraphs[-1]:
                    self.cell.paragraphs.append([])
            elif tag == "br":
                self.cell.paragraphs.append([])
            elif tag == "img" and a.get("src"):
                self.cell.paragraphs[-1].append(f" \0{a['src']}\0 ")

    def handle_endtag(self, tag):
        if self.table is None:
            if tag == "div" and self.divs:
                self.divs.pop()
            return
        if tag == "td":
            self.cell = None
        elif tag == "div" and self.cell is not None:
            self.cell.paragraphs.append([])
        elif tag == "table":
            self.table.rows = [r for r in self.table.rows if r]
            if self.table.rows:
                self.tables.append(self.table)
            self.table = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.paragraphs[-1].append(data)


# --- Rendering ----------------------------------------------------------------

IMG_RE = re.compile(r"\0([^\0]+)\0")


def md_escape(text):
    text = re.sub(r"([\\`*_\[\]|])", r"\\\1", text)
    text = text.replace("<", "&lt;")
    return IMG_RE.sub(lambda m: f"![]({m.group(1)})", text.replace("\\\0", "\0"))


def html_escape(text):
    return IMG_RE.sub(lambda m: f'<img src="{m.group(1)}" alt="">',
                      html.escape(text, quote=False))


def is_full_width(row, ncols):
    return len(row) == 1 and (row[0].colspan >= ncols or ncols <= 1)


def split_table(table):
    ncols = table.ncols or max(sum(c.colspan for c in r) for r in table.rows)
    rows = list(table.rows)
    title, notes = [], []
    while len(rows) > 1 and is_full_width(rows[0], ncols):
        title.append(rows.pop(0)[0])
    while len(rows) > 1 and is_full_width(rows[-1], ncols):
        notes.insert(0, rows.pop()[0])
    return title, rows, notes, ncols


def render(table):
    title, rows, notes, ncols = split_table(table)
    out = []
    for cell in title:
        for para in cell.text_paragraphs():
            out += [f"**{md_escape(para)}**", ""]

    header_rows = 0
    while header_rows < len(rows) and all(c.header for c in rows[header_rows]):
        header_rows += 1
    merged = any(c.colspan > 1 or c.rowspan > 1 for r in rows for c in r)
    widths = {sum(c.colspan for c in r) for r in rows}

    if not merged and header_rows <= 1 and len(widths) == 1:
        kind = "pipe"
        width = widths.pop()
        def line(row):
            return "| " + " | ".join(
                "<br>".join(md_escape(p) for p in c.text_paragraphs()) for c in row) + " |"
        out.append(line(rows[0]))
        out.append("|" + "---|" * width)
        out += [line(r) for r in rows[1:]]
    else:
        kind = "html"
        out.append("<table>")
        for i, row in enumerate(rows):
            out.append("<tr>")
            for c in row:
                tag = "th" if (i < header_rows or c.header) else "td"
                attrs = ""
                if c.colspan > 1:
                    attrs += f' colspan="{c.colspan}"'
                if c.rowspan > 1:
                    attrs += f' rowspan="{c.rowspan}"'
                body = "<br>".join(html_escape(p) for p in c.text_paragraphs())
                out.append(f"  <{tag}{attrs}>{body}</{tag}>")
            out.append("</tr>")
        out.append("</table>")

    for cell in notes:
        out.append("")
        out += sum(([md_escape(p), ""] for p in cell.text_paragraphs()), [])[:-1]
    return out, kind


# --- Locating each table in docs/ --------------------------------------------

def find_span(repo_tokens, table_tokens, start, claimed):
    """Index of table_tokens inside repo_tokens (case-insensitive).

    Searches forward from start first, then from the top of the section,
    skipping spans already claimed by another table."""
    want = [t.lower() for t in table_tokens]
    have = [t.text.lower() for t in repo_tokens]
    n = len(want)
    for lo in (start, 0):
        for i in range(lo, len(have) - n + 1):
            if (have[i] == want[0] and have[i:i + n] == want
                    and not any(i < b and a < i + n for a, b in claimed)):
                return i
    return -1


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default="tucson-az-2.html")
    ap.add_argument("--docs", default="docs/unified_development_code")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    parser = TableParser()
    parser.feed(Path(args.source).read_text(encoding="utf-8"))
    parser.close()
    repo, _, _, _ = vb.load_repo(args.docs)

    edits = {}          # path -> [(first_line, last_line, new_lines)]
    cursor = {}         # section -> next search position
    spans = {}          # section -> token ranges already matched to a table
    counts = {"pipe": 0, "html": 0}
    problems = []
    sticky = None
    for n, table in enumerate(parser.tables, 1):
        if table.sticky:
            sticky = table
            continue
        # The flattened text in docs/ includes the sticky-header copy right
        # before the table, so both are matched and replaced together.
        toks = (sticky.tokens() if sticky else []) + table.tokens()
        sticky = None
        sec_tokens = repo.get(table.section, [])
        label = f"table {n} in {table.section}"
        if not toks:
            problems.append(f"{label}: no text (image-only); left as is")
            continue
        claimed = spans.setdefault(table.section, [])
        i = find_span(sec_tokens, toks, cursor.get(table.section, 0), claimed)
        if i < 0:
            problems.append(f"{label}: flattened text not found word for word")
            continue
        j = i + len(toks) - 1
        first, last = sec_tokens[i], sec_tokens[j]
        path, l1 = first.where.rsplit(":", 1)
        path2, l2 = last.where.rsplit(":", 1)
        before = sec_tokens[i - 1].where if i > 0 else None
        after = sec_tokens[j + 1].where if j + 1 < len(sec_tokens) else None
        if path != path2 or before == first.where or after == last.where:
            problems.append(f"{label}: shares lines with surrounding text at {first.where}")
            continue
        cursor[table.section] = j + 1
        claimed.append((i, j + 1))
        lines, kind = render(table)
        counts[kind] += 1
        edits.setdefault(path, []).append((int(l1), int(l2), lines))

    for path, items in edits.items():
        p = Path(path)
        text = p.read_text(encoding="utf-8").split("\n")
        for l1, l2, lines in sorted(items, reverse=True):
            text[l1 - 1:l2] = [""] + lines + [""]
        out = re.sub(r"\n{3,}", "\n\n", "\n".join(text))
        if not args.dry_run:
            p.write_text(out, encoding="utf-8")

    total = sum(not t.sticky for t in parser.tables)
    done = counts["pipe"] + counts["html"]
    print(f"{done} of {total} tables {'would be ' if args.dry_run else ''}rebuilt "
          f"({counts['pipe']} pipe, {counts['html']} HTML) in {len(edits)} files")
    for line in problems:
        print("  -", line)
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
