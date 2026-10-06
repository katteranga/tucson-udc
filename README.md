# The Open Codes Project

**The Open Codes Project** is a project of **Tucson for Everyone**. It tests whether public codes and related texts can be kept as open-source Markdown and maintained like software: collaboratively, with versions and in the open. Over time the project will add more codes and texts so they can be compared with each other.

**Open UDC** is the project's first code. It converts the City of Tucson's **Unified Development Code (UDC)** from its current home on [American Legal Publishing](https://codelibrary.amlegal.com/) into this repository. Everything here is currently Open UDC.

The rendered site is published at **<https://katteranga.github.io/tucson-udc/>**.

> **Status:** Early proof of concept. The text in this repository is **not** the official UDC. Until the verification work described below is complete, rely on the City's published version for anything that matters.

## Why

The UDC is already public, but in its current form it is hard to work on together. Open UDC tests whether putting the code under version control can:

1. **Make the code easier to collaborate on and update.** Anyone can propose a change as a reviewable edit, not a memo or a marked-up PDF.
2. **Make it easier to track versions.** The published code and draft amendments live side by side, and every change has a full history and a diff.
3. **Track public feedback openly.** Comments are attached to specific proposals and sections, where anyone can see them.

Most of this can be handled by GitHub's existing features, so very little custom tooling is needed.

## How GitHub maps to the code process

| Need | GitHub feature | How it's used here |
|---|---|---|
| The adopted, published code | `main` branch | Must match the currently published UDC word for word (see [Challenges](#current-challenges)). |
| A draft amendment | Branch + **pull request** | Each proposed amendment is a branch. Its pull request shows the exact text changes and holds the review discussion. |
| Public feedback | **Discussions** and PR comments | Open threads per topic or proposal. Comments are public and linked to the text they're about. *(Planned.)* |
| Known problems or to-do work | **Issues** | Errors in the conversion, missing tables and backlog items. |
| A published edition | **Tags / Releases** | A snapshot of `main` each time the City adopts changes, so any past edition can be viewed or compared. *(Planned.)* |
| Decision record | PR history | Who proposed what, what was discussed, and what was merged and when. |

## Milestones

1. **Baseline match** *(current)*. `main` contains the currently published UDC, verified to match word for word, with every table rebuilt. This is the foundation for everything after it, and it depends on the two challenges below.
2. **Amendment workflow.** Draft amendments are proposed and reviewed as pull requests against the verified baseline. Published editions are tagged as releases.
3. **Public feedback.** Discussions are opened and set up so public comments can be tracked openly.
4. **More codes.** Other codes and texts are added to the Open Codes Project for cross-comparison.

## Current challenges

### 1. `main` must match the published code exactly

The value of this repository depends on trusting that `main` is the current UDC. Every section must be checked against the version on American Legal, and that check must be repeatable whenever the City publishes an update.

Known sources of drift:
- Formatting changes made to build the site (spacing, indentation, heading levels, file names). These are listed on the site's [home page](docs/index.md).
- Conversion artifacts from the export, such as stray spaces left where defined-term links were removed (`zone ’s`).
- Edits made on working branches that must not reach `main` until they're adopted.

**How the match is verified:** [tools/verify_baseline.py](tools/verify_baseline.py) compares every section in `docs/unified_development_code/` with the HTML export from American Legal (`tucson-az-2.html`, "Last Revision — February 9, 2026"). Both sides are reduced to their words and punctuation, so spacing, line breaks and Markdown syntax don't count. Any change to wording, punctuation, numbering, quote marks or images is reported, section by section, with the file and line. In headings only, the documented conventions are allowed: letter case, the word "Article", and the period after a section number.

```sh
python3 tools/verify_baseline.py              # writes baseline-report.md; exit status 1 if anything differs
python3 tools/verify_baseline.py --skip-toc   # ignore the article tables of contents
```

When the City publishes a new revision, download a fresh export, replace `tucson-az-2.html` and run the script again. Every section that changed will be listed.

### 2. Tables

The UDC's tables (use tables, dimensional standards, parking ratios and others) come from a word-processor format, and the original export flattened them so that each cell became its own paragraph.

All 98 tables have been rebuilt from the structure in `tucson-az-2.html` by [tools/convert_tables.py](tools/convert_tables.py):

- **29 simple tables** are Markdown pipe tables.
- **69 tables with merged cells** (`colspan`/`rowspan`) are minimal HTML tables, with one cell per line and no styling, because pipe tables can't merge cells.
- A table's title row becomes a bold line above it, and its note rows become paragraphs below it.

A table was only replaced where its flattened text matched the export word for word, so the rebuild didn't change any text.

American Legal's HTML repeats each table's header rows in a separate "sticky header" copy. The old flattened text included both copies, so 49 tables had their headers printed twice. The checker now ignores the sticky copy, and the rebuilt tables show each header once.

`convert_tables.py` is a one-time migration. To edit a table now, edit the Markdown or HTML directly. When writing an HTML table by hand, put each `<table>` at the start of a line; the checker reads everything from there to `</table>` as raw HTML, so Markdown characters like `*` are taken literally.

## Repository layout

```
docs/                          Site content (MkDocs source)
  index.md                     Site home page: project summary and conversion notes
  unified_development_code/    One Markdown file per UDC article/section, e.g. "4.9 Use-Specific Standards.md"
  ordinances/                  Placeholder for adopted ordinances
  assets/                      Logo and images
tucson-az-1.txt                Original export from American Legal: plain text
tucson-az-2.html               Original export from American Legal: HTML
tucson-az-3.md                 Original export from American Legal: Markdown
tools/verify_baseline.py       Checks docs/ against the published export (see Milestone 1)
tools/convert_tables.py        One-time rebuild of the tables from the export
mkdocs.yml                     Site configuration (MkDocs Material theme)
.github/workflows/ci.yml       Builds and deploys the site to GitHub Pages on every push to main
```

File names start with the article and section number, so they sort in code order. The word "Article" is left out of titles for the same reason.

## Working locally

Requires Python 3.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install mkdocs-material
mkdocs serve        # preview at http://127.0.0.1:8000
```

Pushing to `main` rebuilds and publishes the site automatically.

## Contributing

- **Found an error in the conversion?** Open an issue, or a pull request with the fix. Name the section and link the matching page on American Legal.
- **Proposing an amendment?** Create a branch, edit the relevant section file and open a pull request that explains the intent of the change. Don't merge amendments into `main` until they're adopted.
- **Want to comment?** Use Discussions or comment on the relevant pull request.

## Progress log

Keep this section updated as development progresses. Newest entries go first.

- **2026-10-06** – Rebuilt all 98 tables (29 pipe, 69 HTML) and removed the duplicated headers in 49 of them. Still 106 of 112 sections matching, with the same open items.
- **2026-10-06** – Added `tools/verify_baseline.py`. The first run found 20 of 112 sections differing from the February 9, 2026 export. Fixed conversion errors, bringing it to 106 of 112:
  - list numbers reset to "1." in 2.2, 3.7 and 5.12, with `sane_lists` turned on so the site shows the published numbers
  - straight quotes in 1.1
  - stray `$$` in 2.2 and 4.9
  - "DC" for "UDC" in 4.3
  - a duplicated copy of the export at the end of References to Ordinances
  - Article 1's missing table of contents
  - the Article 6 page missing from the site (its file had no `.md` extension)
  - a stray partial export in `docs/`

  Still open: draft edits in 3.4–3.7, and two heading punctuation marks in 7.4 and 7A.11.
- **2026-10-06** – README added to record the project's purpose, goals, milestones and open challenges. Work on Milestone 1 (baseline match) begins on `main`.
- **2026-09-04** – Formatting conventions recorded in `docs/index.md` (spacing, capitalization and dropping "Article" from titles).
- **2026-07-20** – UDC text downloaded from American Legal, converted to HTML and Markdown, and split by section.
