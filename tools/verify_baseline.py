#!/usr/bin/env python3
"""Compare the Markdown UDC in docs/ against the American Legal HTML export.

The export (tucson-az-2.html) is treated as the published text. Both sides are
reduced to a stream of words and punctuation marks, so spacing, line breaks,
and Markdown syntax are ignored, while any change to wording, punctuation,
numbering, or images is reported. Comparison is done section by section
(e.g. 4.9), using the export's section anchors and the repo's numbered
headings.

Formatting conventions documented in docs/index.md are allowed in headings
only: letter case, the word "ARTICLE", and the "." or ":" after a number.
Case differences in body text are reported separately.

Usage:
    python3 tools/verify_baseline.py [--source tucson-az-2.html]
        [--docs docs/unified_development_code] [--report baseline-report.md]
        [--skip-toc]

Exit status is 0 when every section matches, 1 otherwise.
"""

import argparse
import difflib
import html
import re
import string
import sys
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

TOKEN_RE = re.compile(r"\w+|[^\w\s]")
SECTION_ID_RE = re.compile(r"^JD_UDC(?:Art|Sec)\.(\d+A?(?:\.\d+)?)$")
DOC_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
DOC_SECTION_RE = re.compile(r"^(\d+A?(?:\.\d+)?)[.:]?(?:\s|$)")
REFERENCES = "References to Ordinances"


def normalize(text):
    return unicodedata.normalize("NFKC", html.unescape(text))


def normalize_heading(text):
    """Apply the heading conventions from docs/index.md to either side."""
    text = re.sub(r"^\s*ARTICLE\s+", "", text, flags=re.I)
    text = re.sub(r"^(\s*\d+A?(?:\.\d+)*)[.:](?=\s|$)", r"\1", text)
    return text


class Token:
    __slots__ = ("text", "heading", "where")

    def __init__(self, text, heading, where):
        self.text, self.heading, self.where = text, heading, where


def tokenize(text, heading, where):
    return [Token(t, heading, where) for t in TOKEN_RE.findall(text)]


# --- Published text (HTML export) -------------------------------------------

class ExportParser(HTMLParser):
    def __init__(self, skip_toc):
        super().__init__(convert_charrefs=True)
        self.skip_toc = skip_toc
        self.started = False
        self.section = None
        self.sections = {}      # section id -> [Token]
        self.order = []
        self.buf = []
        self.in_heading = 0
        self.toc_depth = 0      # >0 while inside an article table of contents
        self.div_stack = []

    def _flush(self):
        if not self.buf or self.section is None:
            self.buf = []
            return
        text = "".join(self.buf)
        if self.in_heading:
            text = normalize_heading(text)
        self.sections[self.section].extend(
            tokenize(normalize(text), bool(self.in_heading), self.section))
        self.buf = []

    def _enter(self, section):
        self._flush()
        self.started = True
        self.section = section
        if section not in self.sections:
            self.sections[section] = []
            self.order.append(section)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        anchor = a.get("id") or a.get("name") or ""
        m = SECTION_ID_RE.match(anchor)
        if m:
            self._enter(m.group(1))
        elif anchor == "JD_UDCPROrdinances":
            self._enter(REFERENCES)
        if tag == "div":
            cls = a.get("class", "")
            is_toc = cls in ("ChapAn", "ChapAn-center")
            self.div_stack.append(is_toc)
            if is_toc:
                self._flush()
                self.toc_depth += 1
        if re.fullmatch(r"h[1-6]", tag):
            self._flush()
            self.in_heading += 1
        if tag == "img" and self.started and a.get("src"):
            self._flush()
            if self.section is not None:
                name = a["src"].rsplit("/", 1)[-1]
                self.sections[self.section].append(
                    Token(f"[image:{name}]", False, self.section))
        if tag in ("div", "td", "th", "tr", "p", "br", "li"):
            self.buf.append(" ")

    def handle_endtag(self, tag):
        if re.fullmatch(r"h[1-6]", tag) and self.in_heading:
            self._flush()
            self.in_heading -= 1
        if tag == "div" and self.div_stack:
            if self.div_stack.pop():
                if self.skip_toc:
                    self.buf = []
                else:
                    self._flush()
                self.toc_depth -= 1
        if tag in ("td", "th", "p", "li"):
            self.buf.append(" ")

    def handle_data(self, data):
        if self.started:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def load_published(path, skip_toc):
    parser = ExportParser(skip_toc)
    # Text before the first article anchor (cover page, master contents) is
    # ignored because ExportParser only starts collecting at a section anchor.
    parser.feed(Path(path).read_text(encoding="utf-8"))
    parser.close()
    return parser.sections, parser.order


# --- Repository text (Markdown) ----------------------------------------------

ESCAPABLE = string.punctuation  # CommonMark: any ASCII punctuation
# Escaped characters are swapped for private-use placeholders while markup is
# stripped, so "\*" survives as a literal asterisk.
HIDE = {c: chr(0xE000 + i) for i, c in enumerate(ESCAPABLE)}
SHOW = {v: k for k, v in HIDE.items()}


def strip_markdown(line):
    line = re.sub(r"\\(.)", lambda m: HIDE.get(m.group(1), m.group(0)), line)
    line = re.sub(r"^(\s*>)+", "", line)                     # blockquote
    line = re.sub(r"^(\s*)[-*+](\s+)", "\\1•\\2", line)       # bullet -> •
    line = re.sub(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)",
                  lambda m: f" [image:{m.group(1).rsplit('/', 1)[-1]}] ", line)
    line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)   # links -> text
    line = re.sub(r"<[^>]+>", " ", line)                     # inline HTML
    if re.fullmatch(r"\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*", line):
        return ""                                            # table rule
    line = re.sub(r"(?<!\\)\|", " ", line)                   # table pipes
    line = re.sub(r"\*\*|__|(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", line)
    return "".join(SHOW.get(c, c) for c in line)


IMAGE_TOKEN_RE = re.compile(r"\[image:[^\]\s]+\]")


def tokenize_doc_text(text, heading, where):
    tokens, pos = [], 0
    for m in IMAGE_TOKEN_RE.finditer(text):
        tokens += tokenize(normalize(text[pos:m.start()]), heading, where)
        tokens.append(Token(m.group(0), False, where))
        pos = m.end()
    tokens += tokenize(normalize(text[pos:]), heading, where)
    return tokens


def section_sort_key(path):
    m = re.match(r"(\d+)(A?)(?:\.(\d+))?", path.name)
    if not m:
        return (999, 0, 0, path.name)
    return (int(m.group(1)), 1 if m.group(2) else 0,
            int(m.group(3) or 0), path.name)


def load_repo(docs_dir):
    """Return (sections, order, files, sources); sources maps each section to
    the files its text came from, so stray copies in other files are caught."""
    sections, order, files, sources = {}, [], [], {}
    for path in sorted(Path(docs_dir).iterdir(), key=section_sort_key):
        if not path.is_file() or path.suffix != ".md":
            continue
        files.append(path)
        section = None
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            where = f"{path.as_posix()}:{lineno}"
            heading = DOC_HEADING_RE.match(raw)
            text = raw
            if heading:
                text = normalize_heading(heading.group(2))
                m = DOC_SECTION_RE.match(text)
                if m:
                    section = m.group(1)
                elif text.strip().lower() == REFERENCES.lower():
                    section = REFERENCES
            if section is None:
                continue
            if section not in sections:
                sections[section] = []
                order.append(section)
            tokens = tokenize_doc_text(strip_markdown(text), bool(heading), where)
            sections[section].extend(tokens)
            if tokens:
                where_from = sources.setdefault(section, {})
                where_from.setdefault(path.as_posix(), lineno)
    return sections, order, files, sources


# --- Comparison ---------------------------------------------------------------

def excerpt(tokens, lo, hi, width=12):
    a, b = max(lo - width, 0), min(hi + width, len(tokens))
    before = " ".join(t.text for t in tokens[a:lo])
    middle = " ".join(t.text for t in tokens[lo:hi])
    after = " ".join(t.text for t in tokens[hi:b])
    return f"…{before} **⟦{middle}⟧** {after}…"


def compare_section(pub, repo):
    """Return (wording_diffs, case_diffs) for one section."""
    matcher = difflib.SequenceMatcher(
        None, [t.text.lower() for t in pub], [t.text.lower() for t in repo],
        autojunk=False)
    wording, case = [], []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                p, r = pub[i1 + k], repo[j1 + k]
                if p.text != r.text and not (p.heading or r.heading):
                    case.append((p, r))
        else:
            wording.append((op, i1, i2, j1, j2))
    return wording, case


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", default="tucson-az-2.html")
    ap.add_argument("--docs", default="docs/unified_development_code")
    ap.add_argument("--report", default="baseline-report.md")
    ap.add_argument("--skip-toc", action="store_true",
                    help="ignore the article tables of contents in the export")
    args = ap.parse_args()

    pub, pub_order = load_published(args.source, args.skip_toc)
    repo, repo_order, files, sources = load_repo(args.docs)

    order = pub_order + [s for s in repo_order if s not in pub]
    rows, details = [], []
    totals = dict(match=0, differs=0, missing=0, extra=0)
    for sec in order:
        p, r = pub.get(sec), repo.get(sec)
        if r is None:
            status, note = "missing", f"{len(p)} published tokens not in repo"
        elif p is None:
            status, note = "extra", f"{len(r)} tokens not in the published code"
        else:
            wording, case = compare_section(p, r)
            spread = sources.get(sec, {})
            if not wording and not case and len(spread) <= 1:
                status, note = "match", ""
            else:
                status = "differs"
                ratio = difflib.SequenceMatcher(
                    None, [t.text.lower() for t in p], [t.text.lower() for t in r],
                    autojunk=False).ratio() if len(p) + len(r) < 60000 else None
                note = f"{len(wording)} wording, {len(case)} case"
                if ratio is not None:
                    note += f" ({ratio:.1%} similar)"
                lines = [f"### {sec}", ""]
                if len(spread) > 1:
                    note += f"; text found in {len(spread)} files"
                    lines.append("- **split across files** (one is probably a stray copy):")
                    lines += [f"  - `{f}:{n}`" for f, n in spread.items()]
                for op, i1, i2, j1, j2 in wording:
                    where = r[j1].where if j1 < len(r) else r[-1].where
                    lines.append(f"- **{op}** at `{where}`")
                    lines.append(f"  - published: {excerpt(p, i1, i2)}")
                    lines.append(f"  - repo: {excerpt(r, j1, j2)}")
                for pt, rt in case[:50]:
                    lines.append(f"- **case** at `{rt.where}`: published `{pt.text}`, repo `{rt.text}`")
                if len(case) > 50:
                    lines.append(f"- … {len(case) - 50} more case differences")
                details.append("\n".join(lines))
        totals[status] += 1
        rows.append(f"| {sec} | {status} | {note} |")

    summary = (f"{totals['match']} match, {totals['differs']} differ, "
               f"{totals['missing']} missing from repo, "
               f"{totals['extra']} only in repo ({len(order)} sections)")
    report = [
        "# Baseline verification report", "",
        f"Published source: `{args.source}`  ",
        f"Repository text: `{args.docs}` ({len(files)} files)  ",
        f"Tables of contents: {'skipped' if args.skip_toc else 'compared'}", "",
        f"**{summary}**", "",
        "Differences are shown as …context **⟦changed tokens⟧** context…",
        "", "## Summary", "",
        "| Section | Status | Notes |", "|---|---|---|", *rows, "",
        "## Details", "", *details, "",
    ]
    Path(args.report).write_text("\n".join(report), encoding="utf-8")
    print(summary)
    print(f"Report written to {args.report}")
    return 0 if totals["match"] == len(order) else 1


if __name__ == "__main__":
    sys.exit(main())
