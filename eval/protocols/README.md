# Protocol-parser bake-off: answer keys

This folder holds the gold-standard answer keys that document parsers are scored against. It covers
the Santa Clara County EMS PDFs in `data/protocols/santa_clara/archive/` that Herald indexes: five keyed
on 2026-09-23, and 26 more (32 documents in all, because AO 2025-005 holds Policies 602 and 605) keyed on
2026-09-24 (§3b, §4). The keys were
built by hand, using only CPU tools: poppler-utils (`pdftotext`, `pdftoppm`, `pdffonts`,
`pdfinfo`, `pdfimages`, `pdftohtml -xml`) plus Python (Pillow/numpy for pixel checks). No model,
OCR engine or GPU was used, so no parser output can have leaked into the keys.

| File | What it keys | Size |
|---|---|---|
| `table_b_key.json` | Policy 602 "Table B: Approved In-County Services" (hospital x service grid of check marks) | 12 facilities x 14 service levels = 168 cells, 84 checked |
| `flowchart_700a13_key.json` | 700-A13 page 3 "Stroke Center Transport Determination Flow Chart" (raster image) as a graph | 8 nodes, 7 edges |
| `sections_key.jsonl` | Every numbered section/outline item in the 31 PDFs, plus unnumbered headings and figure pages flagged by `kind` | 1,990 lines: 1,921 numbered sections + 69 other rows (35 `doc_title`, 12 `table_caption`, 9 `unnumbered_heading`, 8 `figure`, 5 `box_item`). The 2026-09-23 part is the first 600 lines plus one `figure` row; §3b has the rest |
| `qa_gold.jsonl` | 59 paramedic-style lookup questions with an exact quote and a citation | 52 answerable + 7 unanswerable (qa01-qa25 on the first five documents, qa26-qa59 on the documents added 2026-09-24) |

`../bench_protocols.py` scores retrieval alone (no model) over `qa_gold.jsonl`; results are in §5.

## Source documents and their currency

All five PDFs are Wayback Machine captures of the county's own URLs (see `../../data/protocols/santa_clara/archive/SOURCES.md`).

| Doc key used in the JSON | Pages | What it is |
|---|---|---|
| `700-A13_stroke_eff-2026-01-01.pdf` | 3 | Protocol 700-A13 Stroke, effective Jan 1 2026. Page 3 is a raster flowchart. |
| `700-S04_routine-medical-care-adult_eff-2026-01-01.pdf` | 3 | Protocol 700-S04 Routine Medical Care Adult, effective Jan 1 2026 |
| `501_hospital-radio-reports_eff-2025-01-01.pdf` | 3 | Policy 501 Hospital Radio Reports, effective Jan 1 2025 |
| `440_stroke-center-standards_eff-2025-02-15.pdf` | 6 | Policy 440 Stroke Center Standards, effective Feb 15 2025 |
| `AO-2025-005_policy-602-destination_eff-2025-04-01.pdf` | 27 | Administrative Order AO 2025-005 (see the page map below) |

**The AO PDF is five documents in one file.** Every key records which part a page belongs to:

| Physical pages | Part (value of `part` in sections_key) | Printed footer |
|---|---|---|
| 1 | AO 2025-005 cover memo (DocuSigned) | Page 1 of 1 |
| 2-11 | Policy 602 911 EMS Patient Destination, **tracked-changes/redline copy** (Word markup: blue insertions, "Deleted:"/"Formatted:" balloons in a grey right margin) | Page 1-10 of 10 |
| 12-21 | Policy 602, **clean copy** | Page 1-10 of 10 |
| 22-24 | Policy 605 Prehospital Trauma Triage, **redline copy** | Page 1-3 of 3 |
| 25-27 | Policy 605, **clean copy** | Page 1-3 of 3 |

Both Policy 602 copies break pages at the same places (redline page N matches clean page N+10), and
their outlines were checked to be identical item for item (119 items each). The two Policy 605
copies were checked the same way (53 items each).

**Page numbers in every key are physical 1-based PDF page indexes** (what `pdftoppm -f N` and
`pdftotext -f N` use), not the printed "Page x of y". For example, Table B is physical page 20 and
printed "Page 9 of 10".

**Currency caveat:** SOURCES.md records that AO 2025-006 (Sept 1 2025) and AO 2025-007 (Oct 16 2025)
amend Policy 602 and are not in the archive. These keys are exact for the documents as archived,
not for the policy currently in force. Do not use them clinically.

The two change memos in the archive folder (`2025-policy-protocol-changes-summary.pdf`,
`2026-policy-protocol-changes-summary.pdf`) are out of scope and have no key. They describe what changed
between protocol versions ("changed X to Y"), so they are reference reading, not protocol text, and Herald
does not index them: a lookup that returned a memo line would present a past change as a current rule (the
2025 memo describes a cycle that the 2026 revisions superseded again, e.g. 700-A04). The superseded copies in
`archive/previous/` (700-A02, 700-A07, 700-A11 and 700-S04, all effective 2025-01-01) are not indexed or keyed
either; `tests/test_knowledge.py` checks both.

The 26 PDFs added on 2026-09-24 (county URL, Wayback capture, effective date, sha256) are listed in
`../../data/protocols/santa_clara/archive/SOURCES.md`; each one's document entry is in
`config/counties/santa_clara.json` (`documents`).

---

## 1. `table_b_key.json`: Policy 602 Table B

### Schema

```json
{
  "source": "AO-2025-005_policy-602-destination_eff-2025-04-01.pdf page 20",
  "columns": ["Emergency Department (Adult)", "Burn Center", ... 14 service levels as printed ...],
  "rows": [{"facility": "El Camino Hospital of Mountain View", "abbrev": "ECH", "city": "Mountain View",
            "checks": {"Emergency Department (Adult)": true, "Burn Center": false, ...}}, ... 12 rows ...],
  "notes": "..."
}
```

The file also has these extra keys, which the requested format does not require:
- `by_service`: the table in the printed orientation, `{service: [checked abbrevs in printed column order]}`.
- `facility_order_as_printed`: the printed column order.
- `check_count` / `cell_count`: 84 / 168.
- `footnote_as_printed`: the asterisk footnote under the table.
- `text_layer_glyphs`: the bounding box of each of the 84 check glyphs and its offset from the column/row centre it was assigned to.
- `source_detail`, `table_title`, `banner`, `printed_orientation`.

**Orientation:** the printed table puts **service levels in rows** and **facilities in columns**
(abbreviations only). The requested format is transposed: `columns` holds the 14 service levels,
exactly as printed (asterisks and `&` kept), and `rows` holds the 12 facilities in printed column
order: EPS, ECH, GSH, KSC, LGH, OCH, PAV, RSJ, SLH, STH, SUH, VMC. Scorers comparing against a parser
that keeps the printed orientation should use `by_service`.

**Facility names:** Table B prints only abbreviations. Full names and cities come from Table A on
the same page, exactly as printed (including the curly apostrophe in "O’Connor Hospital"). Two
special cases:
- **EPS** is not in Table A. Its name, "Emergency Psychiatric Services (EPS)", comes from Policy 602
  V.B.2.a. `city` is `null` because no city is printed for it.
- **STH** is the ID that Table A prints for "Kaiser Foundation San Jose" (not "KSJ"). It is keyed as printed.

### The grid (printed orientation)

| Service (as printed) | n | Checked facilities |
|---|---|---|
| Emergency Department (Adult) | 11 | ECH GSH KSC LGH OCH PAV RSJ SLH STH SUH VMC |
| Burn Center | 1 | VMC |
| Primary Stroke Center | 10 | ECH GSH KSC LGH OCH RSJ SLH STH SUH VMC |
| Comprehensive Stroke Center | 5 | ECH GSH KSC RSJ SUH |
| STEMI Center | 8 | ECH GSH KSC OCH RSJ STH SUH VMC |
| Adult Trauma Center | 3 | RSJ SUH VMC |
| Pediatric Trauma Center | 2 | SUH VMC |
| Advanced Pediatric Center | 3 | KSC SUH VMC |
| General Pediatric Center | 9 | ECH GSH KSC OCH RSJ SLH STH SUH VMC |
| *Psychiatric Facility | 12 | EPS ECH GSH KSC LGH OCH PAV RSJ SLH STH SUH VMC |
| *VAD Center | 2 | KSC SUH |
| *Labor & Delivery | 9 | ECH GSH KSC LGH OCH SLH STH SUH VMC |
| *SAFE Center | 3 | SLH SUH VMC |
| *Helipads | 6 | GSH KSC RSJ SLH SUH VMC |

EPS is checked only for *Psychiatric Facility. PAV is checked only for Emergency Department (Adult) and
*Psychiatric Facility. In particular, PAV is not a stroke center and VMC is not a Comprehensive Stroke Center.

### Glyph-vs-image finding: the check marks are text glyphs

- `pdffonts -f 20 -l 20` lists two embedded subset fonts on the page: `AAAAAX+Wingdings2` (MacRoman,
  no ToUnicode) and `AAAAAY+Wingdings2` (WinAnsi, with ToUnicode).
- `pdftohtml -xml` gives the font of every text run. **All 84 check marks are the character `R`
  (U+0052) set in `AAAAAY+Wingdings2`**, about 22 pt and black. In Wingdings 2, code 0x52 draws a
  ballot box with a check (☑, U+2611). The other font, `AAAAAX+Wingdings2`, carries only space
  characters that pad the empty cells, so **an empty cell contains no glyph at all**.
- As a result, plain `pdftotext` turns every checked cell into a bare `R`
  (`Department (Adult)     R R R R R R R R R R R`). The columns collapse, and in `-layout` mode the
  row of Rs for `*Helipads` is even printed *above* its label. A parser that "reads the text" gets a
  string of Rs, not check marks. A good parser must map Wingdings2 `R` to ☑ (or to true) and keep the
  column positions.
- **How coordinates were used** (text-layer keying): `pdftotext -bbox-layout -f 20 -l 20`. The column
  x-centres are the centres of the header words EPS...VMC (all at yMin 308.92 pt). Each `R` word box
  (about 17.8 x 20.6 pt) goes to the nearest column centre (largest offset 0.70 pt; the columns are
  about 30 pt apart) and to the row label whose vertical centre is nearest (largest offset 1.84 pt; the
  row pitch is about 25 pt). No assignment was anywhere near ambiguous. Every glyph box and its offsets
  are listed in `text_layer_glyphs`.

### How it was keyed (independently, then reconciled)

1. **Text layer / bbox**, as described above: 84 glyphs, one per checked cell.
2. **Rendered image, by eye**: page 20 rendered with `pdftoppm -r 150` for the whole page, then
   200-dpi crops of the top and bottom halves of the table, read row by row and typed in
   before the comparison was run.
3. **Pixel check**: a 200-dpi grayscale render. Table grid lines were found from long dark runs
   (14 row bands and 13 column bands), then the dark-pixel fraction inside each of the 168 cell interiors
   was measured. Checked cells score 0.184-0.205 and empty cells exactly 0.000, with nothing in between.
4. **Cross-copy**: the redline copy of the same table on physical page 10 was keyed from its text
   layer (84 `R` glyphs) and looked at in a render.

**Reconciliation result: all methods agree on all 168 cells. There were no disagreements to reconcile.**

The redline page 10 adds one fact: exactly two of its check glyphs are **blue (#0078d4) and
underlined**, which marks them as tracked insertions: **RSJ / STEMI Center** and **RSJ / Adult Trauma
Center**. This matches the AO cover memo ("designation of Regional Medical Center as an Adult Trauma
Center and STEMI Receiving Center as of April 1, 2025"). On the clean page 20 those two checks are
ordinary black.

---

## 2. `flowchart_700a13_key.json`: 700-A13 page 3 flowchart

### Schema

`nodes: [{id, text, lines, shape, role}]` and `edges: [{from, to, label}]`, plus `node_count`,
`edge_count`, `text_vs_chart_mismatches` and `notes`. `text` joins the printed lines with single
spaces, and `lines` keeps the printed line breaks.

### Graph

```
n1 "Routine Medical Care - Blood Glucose Level"  (start)
 |
 v
n2 <Time Last Known Well> --"More than 24 hours"--> n3 "Continue routine medical care"
 | "Less than 24 hours"
 v
n4 <GFAST Exam> --"GFAST 1-3"--> n5 "Transport to closest Stroke Center"
 | "GFAST 4"
 v
n6 <Transport to Comprehensive Stroke Center in less than 45 minutes?> --"NO"--> n7 "Transport to closest Stroke Center"
 | "YES"
 v
n8 "Transport to Comprehensive Stroke Center"
```

This is 8 nodes (3 decision diamonds and 5 rounded terminators) and 7 edges. Only n1->n2 has no label.

### How it was keyed

The chart is a single embedded raster image: object 37, 1330x2009 px RGB with a soft mask, 318 ppi.
**Page 3 has no text layer for the chart.** Its only text is the header, the heading "7. Stroke Center
Transport Determination Flow Chart", the side tab and the footer, so a parser can recover the chart
only with OCR or vision. The image was extracted at native resolution with `pdfimages -png`,
composited onto white using its mask, and read by eye. Small labels were checked on 3x-4x zoomed
crops. "GFAST 1-3" uses a short hyphen, not an en dash. The n1 sub-line "- Blood Glucose Level"
starts with a hyphen-minus and is set smaller than "Routine Medical Care". n5 and n7 have identical
text but are separate boxes.

### Wording that differs from the protocol text (`text_vs_chart_mismatches`)

1. **The NO branch versus §3.2.1.** The chart says NO -> "Transport to closest Stroke Center". §3.2.1
   says "If transport time to closest Comprehensive Stroke Center is greater than forty-five (45)
   minutes, transport to the closest **Primary** Stroke Center." Policy 602 VI.E.1.c agrees with the
   text. This is the main mismatch.
2. **The 45-minute boundary.** The chart asks "in less than 45 minutes?" while the text says "greater
   than forty-five (45) minutes". At exactly 45 minutes the text sends the patient to the CSC, but the
   chart answers NO. The chart also frames the question as transport *to* the CSC, not as the time to
   the *closest* CSC.
3. **GFAST 0.** The chart edge says "GFAST 1-3", but §3.3 says "three (3) or fewer points", so a score
   of 0 has no branch in the chart. The chart node also leaves out "(Comprehensive or Primary)".
4. **The 24-hour boundary.** The chart edges say "Less than 24 hours" and "More than 24 hours". §3.1
   says "within twenty-four (24) hours". Exactly 24 hours is covered by neither edge, and the chart
   never uses the words "Stroke Alert".
5. **Missing from the chart.** The chart has no seizure exclusion (§2.4 -> 700-A02 and the appropriate
   ED) and no hypoglycemia handoff (§2.2/§4.2 -> 700-A03 when BGL < 60 mg/dL). Its start node only
   says "Routine Medical Care - Blood Glucose Level".
6. **Name spelling.** The section text writes "G.F.A.S.T." in §2.3 and "G.F.A.S.T" (no final period)
   in §3.2 and §3.3. The chart and §6.2 write "GFAST".

---

## 3. `sections_key.jsonl`: numbered sections and headings

### Schema (one JSON object per line, in reading order within each doc)

Required fields, as requested: `doc`, `number`, `title`, `page`, `level`. Extra fields:

| Field | Meaning |
|---|---|
| `label` | The enumerator exactly as printed (`"2.1.1."`, `"VI."`, `"c."`), or `null` for unnumbered entries |
| `kind` | `section` (a numbered or lettered outline item). The others are included so scorers can filter them: `doc_title` (the big centred document title), `table_caption` (Table A-E captions in Policy 602; two table captions in Policy 410), `unnumbered_heading` (the 4 bold criteria subheads in Policy 605; "Patient Eligibility" in 700-M17), `box_item` (the 5 G.F.A.S.T. box rows in 700-A13), `figure` (a page whose content, or part of it, exists only as an image or as a chart drawn in a font without a character map; §3b) |
| `part` | AO file only: which embedded document the entry belongs to (see the page map above) |
| `parent`, `score_as_printed`, `text_layer`, `text_layer_error` | `box_item` rows (see "Text-layer errors"); `parent` also on the Policy 410 table captions; `text_layer`/`text_layer_error` also on 700-A18 6.1.2-6.1.3 (Symbol-font ≥) |
| `text_layer`, `figure` | `figure` rows: `text_layer` is `none` (the page has only its heading as text), `partial` (text and images) or `garbled` (symbol runs); `figure` says what the image shows. `number` is the section the figure belongs to, `level` is `null` |

**`number` format.**
- Decimal protocols (the 700 series): the printed number without its trailing period, e.g.
  `"3.2.1"`. `level` is the number of components (1 = the grey-bar headings "1." ... "15.",
  2 = "x.y", 3 = "x.y.z", 4 = "x.y.z.w").
- Policy 410 (a deeper outline, `I. > A. > 1. > a. > i. > 1. > a.`): the full path joined with dots,
  e.g. `"IV.B.1.b.i.1.a"`; `level` is the depth (1-7), read from the indentation columns (§3b).
- Outline policies (302, 420, 430, 440, 500, 501, 602, 605, AO memo): the full hierarchical path joined with dots, e.g.
  `"VI.E.1.c"`. The printed enumerator alone is in `label`. `level` follows the enumerator type:
  1 = Roman (I., II.), 2 = capital letter (A.), 3 = arabic numeral (1.), 4 = lower-case letter (a.).
  Single letters that could be Roman numerals (I, V, X, L, C, D, M) were resolved from the sequence.
  For example, Policy 602 "I. Incidents Occurring at Acute Care Hospitals" follows H., so it is
  letter VII.I. Policy 605 "I. Active bleeding..." is II.I and "V. Pedestrian..." is II.V.
- `number` is `null` for unnumbered entries (`doc_title`, `table_caption`, `unnumbered_heading`, `box_item`).

**`title` rule.**
- For headings (every level-1 item, i.e. the grey-bar headings in the 700 series and the Roman
  headings in policies), `title` is the heading text on the label's line.
- For every other item, `title` is **the first 10 whitespace-separated words** of the item's text as
  printed, or all of it if it is shorter. The words continue across wrapped lines (a gap of 16.5 pt or
  less counts as a wrapped line). No ellipsis is added, so **score titles by prefix or fuzzy match, not
  exact equality**.
- Five items are standalone heading lines followed directly by a paragraph with no blank line. Their
  titles are the heading line only: 440 VI.B.1-4 ("Stroke Program Medical Director",
  "Stroke Program Manager/Coordinator", "Clinical Stroke Team", "Registrar/Data Analyst") and the AO
  memo's III ("Execution").
- Typography is kept as printed: curly quotes, en dashes ("Routine Medical Care – Adult (700-S04)")
  and typos ("chief compliant" in 501 III.A.2).
- Documents added on 2026-09-24: in 302 and 410 a level-1 heading is followed by its text on the same line
  ("I. Purpose: The purpose of ..."), so the title is the heading up to its colon ("Purpose:"). Standalone
  heading lines followed by a paragraph: 420 VI.C.1-6, 430 VII.B.1-4 (VII.B.3 "Clinical STEMI Team" sits at the
  foot of page 4 with its paragraph on page 5). The rendered text is used where the text layer is wrong: 700-A18
  6.1.2-6.1.3 "≥" (with `text_layer` "³"), 700-M02 3.1.1-3.1.2 "2nd or 3rd" / "4th or 5th" (superscript ordinals
  on a raised baseline), 700-M02 3.3 "90º" as printed. 700-P10 3.3.1.3 holds only a dose table, so its title is
  the table's first words.

### Counts

| Doc | `section` rows | By level | Other rows |
|---|---|---|---|
| 700-A13 | 38 | L1 7, L2 26, L3 5 | 1 doc_title, 5 box_item |
| 700-S04 | 70 | L1 11, L2 46, L3 13 | 1 doc_title |
| 501 | 38 | L1 6, L2 11, L3 10, L4 11 | 1 doc_title |
| 440 | 75 | L1 7, L2 15, L3 44, L4 9 | 1 doc_title |
| AO 2025-005 (all parts) | 347 | see below | 5 doc_title, 10 table_caption, 8 unnumbered_heading |
| of which: AO cover memo (p1) | 3 | L1 3 | 1 doc_title |
| of which: Policy 602 redline (p2-11) | 119 | L1 7, L2 31, L3 52, L4 29 | 1 doc_title, 5 table_caption |
| of which: Policy 602 clean (p12-21) | 119 | L1 7, L2 31, L3 52, L4 29 | 1 doc_title, 5 table_caption |
| of which: Policy 605 redline (p22-24) | 53 | L1 4, L2 31, L3 18 | 1 doc_title, 4 unnumbered_heading |
| of which: Policy 605 clean (p25-27) | 53 | L1 4, L2 31, L3 18 | 1 doc_title, 4 unnumbered_heading |
| **Total** | **568** | | 32 (600 lines in all) |

Every `section` row has a non-null `number`. The AO total is 3 + 119 + 119 + 53 + 53 = 347. The
32 other rows are 9 `doc_title`, 10 `table_caption`, 8 `unnumbered_heading` and 5 `box_item`.

To score only the clean policy text, filter the AO rows with `part` containing "clean" or "cover memo".
The redline copies have the same outline because the tracked deletions live only in margin balloons,
which are not keyed.

### How it was built

1. `pdftotext -bbox-layout` was run on every page. Words were grouped into visual lines by y-position,
   excluding the right-margin side tab (x of 560 pt or more) and, on redline pages, the comment
   balloons (x of 425 pt or more), plus page footers (y of 715 pt or more).
2. A line is an outline item if its first word matches `^\d+(\.\d+)*\.$`, a Roman numeral with a
   period, `^[A-Z]\.$` or `^[a-z]\.$`. Levels and paths were assigned by enumerator type, using the
   sequence to resolve ambiguous letters.
3. The redline and clean copies were extracted separately and compared: the outlines are identical.
   The cut-offs were checked: moving the footer cut-off to 800 pt adds no items, and no item's text
   continues onto the next page except 602 VI.H.2 (already 10 words) and 440 VI.B.2 (a heading-only title).
4. **Every page was checked by eye** against renders: 700-A13 p1-3, 700-S04 p1-3, 501 p1-3,
   440 p1-6, AO p1, p12-19, p20-21, p25-27, plus redline samples p4, p10 and p22. Every numbered item
   in the renders appears in the key with the same number and level.

### Numbering quirks in the sources (keyed as printed, not corrected)

- **Policy 605 (both copies):** under II., the list runs A., B., then **restarts at A.** and goes on
  to X. Four unnumbered bold subheads sit between them: "High Risk Injury Pattern (Red Criteria):",
  "Mental Status and Vital Signs (Red Criteria):", "Moderate Risk Mechanism of Injury (Yellow
  Criteria):" and "Special Considerations (EMS Judgement):". So the paths `II.A` and `II.B` each occur
  twice. The criteria A.-X. are printed at the same indent as II.A/II.B, so they are keyed at level 2
  as peers. The subheads are `unnumbered_heading` rows at level 2.
- **Policy 605:** the Roman numeral **II. is used twice** ("Trauma Alert Patient" and "Trauma Alert –
  Ambulance Transport"), followed by III. "Major Burn Criteria". Logically these should be III. and IV.
- **Policy 602 VI.H.1:** a.-j. list the critically-ill criteria, then an unnumbered line "Shall be
  transported to:" is followed by a new a., b. So `VI.H.1.a` and `VI.H.1.b` each occur twice on
  the same page. `title` tells them apart.
- **Policy 602 VI.E.1.c** says "in accordance with Section (F)(2) of this policy", but F is STEMI; the
  Primary Stroke rule is E.2. This is a cross-reference error in the source.
- **700-A13 2.9** says "transport to the appropriate receiving facility, see section 2". The transport
  rules are in section 3, so this is probably a source error.
- **501 III.A.2** prints "chief compliant" (meaning "complaint"), and the example box prints "Asprin".
- **440** has inconsistent indentation: numbers are sometimes indented more than their parent letters,
  and continuation lines sit left of the item text. Levels were keyed from the enumerator type, which
  is unambiguous.

### Text-layer errors and artifacts, with the correct text

| Where | Text layer says | Correct (rendered) text | Cause |
|---|---|---|---|
| 700-A13 p1, G.F.A.S.T. box, G row | `Gaze Abnormali.es` | Gaze Abnormalities | the "ti" ligature glyph maps to "." |
| 700-A13 p1, A row | `Arm or leg Weakness/Dri9` | Arm or leg Weakness/Drift | the "ft" ligature glyph maps to "9" |
| 700-A13 p1, S row | `Speech Diﬃcul.es` (U+FB03 "ﬃ") | Speech Difficulties | "ffi" comes out as a compatibility ligature (NFKC fixes it), and "ti" maps to "." |
| 700-A13 p1, F/T rows and all (0-1)/(no point) scores | correct | - | - |
| Policy 602 Table B/D check marks (p10, p11, p20, p21) | `R` | ☑ (checked) | Wingdings2 glyphs (see section 1) |
| Side tab on 501, 440 and Policy 602 pages | `POLICY # #102` / `602` / `POLICY` in several pieces | "POLICY # 501" (or 440 / 602), rotated white text on a black tab | a stray " #102" run inside the rotated tab text. It is invisible in the render but present in the text layer. |
| Policy 602/605 redline pages | "Deleted: ..." / "Formatted: ..." lines mixed into body lines | not body text | Word comment balloons in the right margin |

A scan of all five text layers for ligature code points, `letter.letter` inside words and
letter-digit mixes found no other glyph errors. The G.F.A.S.T. rows are in `sections_key.jsonl` as
`kind: "box_item"` with the correct `title` and the faulty `text_layer` string, so scorers can test
whether a parser repairs them.

---

## 3b. Documents added on 2026-09-24

The 26 PDFs archived on 2026-09-24 (every current file in `archive/` except the two change memos), plus
Policy 605 as its own document (AO 2025-005 pages 25-27, already keyed above as "Policy 605 (clean copy)";
no new 605 rows). Rows are appended after the first 600 lines, one document after another, in reading
order; `doc` is the file name, as above.

### Counts

| Document | `section` rows | By level | Other rows |
|---|---|---|---|
| 700-A03 Hypoglycemia | 24 | L1 5, L2 14, L3 5 | 1 doc_title |
| 700-A04 Sepsis | 31 | L1 5, L2 15, L3 11 | 1 doc_title |
| 700-A08 Chest Pain - Suspected Cardiac Ischemia | 43 | L1 8, L2 22, L3 10, L4 3 | 1 doc_title, 1 figure |
| 700-A10 Shock | 32 | L1 5, L2 17, L3 8, L4 2 | 1 doc_title |
| 700-A14 Tachycardia with Pulses | 63 | L1 13, L2 32, L3 18 | 1 doc_title, 1 figure |
| 700-A15 Poisoning and Overdose | 47 | L1 12, L2 30, L3 4, L4 1 | 1 doc_title |
| 700-A16 Trauma Care | 44 | L1 6, L2 25, L3 11, L4 2 | 1 doc_title |
| 700-A18 Gynecological and Obstetrical Emergencies | 77 | L1 13, L2 41, L3 19, L4 4 | 1 doc_title, 1 figure |
| 700-A20 Behavioral Emergency - Combative | 78 | L1 7, L2 31, L3 40 | 1 doc_title |
| 700-M02 Pleural Decompression | 24 | L1 4, L2 7, L3 6, L4 7 | 1 doc_title |
| 700-M09 12-Lead Electrocardiogram | 40 | L1 4, L2 13, L3 21, L4 2 | 1 doc_title, 1 figure |
| 700-M17 Traumatic Hemorrhage Control | 21 | L1 3, L2 11, L3 7 | 1 doc_title, 1 unnumbered_heading |
| 700-P02 Pediatric Seizure | 37 | L1 5, L2 23, L3 9 | 1 doc_title |
| 700-P03 Pediatric Hypoglycemia | 27 | L1 6, L2 16, L3 5 | 1 doc_title |
| 700-P07 Pediatric Cardiac Arrest | 114 | L1 15, L2 61, L3 32, L4 6 | 1 doc_title, 2 figure |
| 700-P10 Pediatric Shock | 32 | L1 5, L2 16, L3 8, L4 3 | 1 doc_title |
| 700-P11 Pediatric Respiratory Distress | 41 | L1 8, L2 25, L3 8 | 1 doc_title |
| 700-P15 Pediatric Poisoning and Overdose | 45 | L1 12, L2 28, L3 5 | 1 doc_title |
| 700-P16 Pediatric Trauma Care | 41 | L1 6, L2 26, L3 9 | 1 doc_title |
| 700-S05 Routine Medical Care Pediatric | 65 | L1 11, L2 34, L3 16, L4 4 | 1 doc_title |
| 700-S06 Falls | 31 | L1 4, L2 18, L3 9 | 1 doc_title, 1 figure |
| 302 Prehospital Care Asset - Minimum Inventory Requirements | 32 | L1 6, L2 26 | 1 doc_title |
| 410 Pediatric Receiving Center Standards | 99 | L1 7, L2 9, L3 8, L4 20, L5 23, L6 25, L7 7 | 1 doc_title, 2 table_caption |
| 420 Trauma Center Standards | 98 | L1 8, L2 16, L3 68, L4 6 | 1 doc_title |
| 430 STEMI Center Standards | 74 | L1 9, L2 21, L3 39, L4 5 | 1 doc_title |
| 500 Electronic Patient Care Record (ePCR) Documentation | 93 | L1 8, L2 33, L3 43, L4 9 | 1 doc_title |
| **Total** | **1,353** | | 26 doc_title, 7 figure, 2 table_caption, 1 unnumbered_heading (1,389 rows) |

One more `figure` row was added to the 2026-09-23 part: 700-A13 page 3 (the stroke flowchart, keyed as a
graph in `flowchart_700a13_key.json`), placed after its section 7 row.

### Figure pages (`kind: "figure"`)

| Document, page | Section | `text_layer` | What is on the page |
|---|---|---|---|
| 700-A13 p3 | 7 | none | stroke center transport flowchart, one raster image (1330x2009) |
| 700-A08 p3 | 8 | none | chest pain treatment flowchart, one raster image (1275x1650) |
| 700-A14 p3 | 13 | none | tachycardia treatment flowchart, one raster image (1867x1268) |
| 700-A18 p4 | 13 | none | pre-eclampsia/eclampsia flowchart, one raster image (1024x768) |
| 700-S06 p2 | 4 | partial | fall flowchart, one raster image (962x757); items 3.4.1-3.4.2 above it are text |
| 700-M09 p2 | 4.10 | partial | lead-placement photo (445x578), 12-lead strip (995x283) and the "STEMI Location Interpretation" region table (642x103) as raster images; items 4.5-4.9.1.2 are text |
| 700-P07 p5 | 15 | garbled | cardiac arrest flowchart drawn as vector boxes; the box text is in a font without a character map, so the text layer reads `!"#$%"&G(##)*+` |
| 700-P07 p6 | 15 | garbled | traumatic cardiac arrest flowchart, same construction |

The research notes (`docs/research/county_protocols_2026-09.md` §11) listed three image-only pages
(700-A08 p3, 700-S06 p2, 700-M09 p2). The CPU checks found four more: 700-A14 p3 and 700-A18 p4 (raster
flowcharts, 35-37 words of text on the page), and 700-P07 p5-6 (vector flowcharts whose words are symbol
runs). Each figure page has a `figures` entry in the county config, so the vision model transcribes it once per
document version and model; 700-M09's chart uses `config/prompts/figure_transcribe_chart.md` because it is a
labeled chart, not a flowchart. `tests/test_knowledge.py` checks that the configured figures equal these rows.

### How it was built

1. `pdftotext -bbox-layout` word boxes for every page, grouped into visual lines by vertical centre (3 pt
   tolerance), with the right-margin side tab (x of 560 pt or more) removed. The header and footer bands were
   read from each document's word boxes: 700 series header y < 70 pt and footer y ≥ 720 pt; 420 and 430
   60/735; 500 70/745; 302 and 410 65/765, and on their page 1 the signature block from 725 pt.
2. A line is an item if its first word is an enumerator: `^\d{1,2}(\.\d{1,2})*\.$` in the 700 series;
   `I.`-style Roman numerals, `A.`, `1.`, `a.` and (410 only) `i.`-style lower-case Roman numerals in the
   policies. Every printed label ends with a period; no decimal label without one exists in these files
   (checked with a grep over the `pdftotext -layout` text).
3. Levels: decimal components in the 700 series; enumerator type in 302, 420, 430 and 500 (Roman 1, capital
   2, digit 3, lower case 4; a single letter that could be a Roman numeral is a numeral only when it is the
   next one in sequence, so 302's "I." and "V." under III are letters). Policy 410 nests a second list type
   under lower-case Roman numerals (`i. > 1. > a.`), so its levels come from the indentation columns in the
   word boxes: Roman I-V right-aligned at 40-48 pt, `A.` at 64.8, `1.` at 79.2, `a.` at 90, `i.`-`viii.`
   right-aligned at 92-103, nested `1.` at 112.5, nested `a.` at 126. Its Roman numbering restarts at
   "I. References:" after V., keyed as printed.
4. Titles by the rules in §3, including the corrections listed there.
5. Checks: every decimal item follows its predecessor (a sibling increment or a first child); every outline
   path is in sequence. Figure pages were found from `pdfimages -list` (raster images of 700 px or more on a
   side), the word count of each page, and the text layer (symbol runs), then looked at in renders.
6. The key was built from word boxes, independently of Herald's splitter (`herald/knowledge/sections.py`
   reads `pdftotext -layout` lines). After the fixes below, the splitter reproduces it exactly for all 32
   documents: 1,746 numbered sections with the same number, page and level, none missing and none extra
   (`test_every_numbered_section_in_the_key_is_found_and_nothing_else`). Every disagreement found on the way
   was settled from the PDF. The key was changed in only four titles, all key-builder artifacts (700-M02
   3.1-3.1.2 superscripts, 430 VII.B.3 heading at a page break); everything else that disagreed was a
   splitter defect:
   - **Repeated body text read as a running header.** 700-A14 prints the SVT definition in §5.1 (page 1) and
     §7.1 (page 2) word for word; 700-A20 repeats the sedation criteria (§4.2.1-3 and §5.1.1-4) and the
     post-sedation care list (§4.4.x and §5.3.x); 700-A18 repeats "Inclusion Criteria:" (§6.1, §7.1) and
     "Secondary Impression – Pregnancy complication" (§12.3.2, §12.5.2, §12.7.2). A line repeated on 2 of 3
     pages passed the old share-only test and was deleted, with its continuation lines ("than 0.12 seconds,
     and absent P waves"). 29 items and their text were lost. A running line must now also sit among the
     first 5 or last 13 non-empty lines of its page in most occurrences, and a numbered line is never one
     (`running_line_band` in `config/knowledge.yaml`). This also keeps 302's table column headers
     ("Minimum Quantities Required", "Transport Non-Transport").
   - **Items indented more than 12 spaces** (700-A10 3.3.1.1-2, 700-P10 3.3.1.1-3, 700-P02 3.1.4) and
     **an item holding only a table** (700-P10 3.3.1.3) were missed. The decimal pattern now allows 24
     spaces and an empty title, and requires the label's trailing period, which is what tells an item from a
     wrapped line that starts with a number ("90 mmHg", "2.5 mg; not to exceed").
   - **Items that start with a dose** (700-A10 3.2 "500 ml Normal Saline", 700-A16 3.3.2, 700-P03 4.2 "3 ml/kg",
     700-P16 3.2.1 "20 ml/kg") were rejected by a dose-word exclusion in the splitter. Across all 32 documents
     that exclusion never rejected a non-item line, so it was removed.
   - **Policy 410's deep outline** needed the new `nested` heading style (the level comes from the label
     sequence: the next label of an open list continues it, the first label of a kind opens a list one level
     down, a Roman `I.` starts a new top-level section).
   - **Policy 605 prints "II." twice.** The second one ("II. Trauma Alert – Ambulance Transport") was folded
     into II.X.7. A repeated Roman numeral of two or more letters (which can't be a letter) is now a heading.

### Numbering and text quirks in the added documents (keyed as printed)

- 700-P02 3.1.4 is printed indented as if under 3.1.3; keyed at level 3 by its number.
- 700-M09 4.1 reads "Endotracheal Obtain first ECG prior to leaving scene" (a stray word); 4.8 is a hyperlink.
- 700-M17 opens with an unnumbered "Patient Eligibility" paragraph before "1." (`unnumbered_heading`). The
  splitter keeps it in the document's preamble section `0`.
- 700-S06 starts at "1. Routine Treatment" (no Patient Care Goals section).
- 700-P11's footer reads "Protocol # 700-A11" on both pages (a source typo; removed as a running line).
- 302 runs its letters A.-X. under III.; 420 VII. has items 1.-4. with no letter level (`VII.1`-`VII.4`, level 3).
- 302 prints its title as "... INVENTORY REQUIRMENTS" (typo kept in the `doc_title` row).

### Text-layer errors in the added documents

| Where | Text layer says | Correct (rendered) text | Cause | What Herald does |
|---|---|---|---|---|
| 700-A18 p1 6.1.2-6.1.3 | `SBP ³ 140 mmHg or DBP ³ 90 mmHg` | SBP ≥ 140 mmHg or DBP ≥ 90 mmHg | SymbolMT glyph 0xB3 (≥) reported as U+00B3 through the WinAnsi encoding | superscripts are no longer NFKC-folded (which read "SBP 3 140"); the section is flagged `text_layer_uncertain`, so the page image is offered |
| 700-M02 p1 3.3 | `90º` | 90° | masculine ordinal used as a degree sign | kept as printed (NFKC would give "90o") |
| 700-M02 p1 3.1.1-3.1.2 | `2`, `nd` on a raised baseline | 2nd | superscript ordinals set as raised text | `pdftotext -layout` joins them correctly |
| 700-P07 p5-6 | runs such as `!"#$%"&G(##)*+` | the flowchart box text | chart words in a font with no character map | section 15 flagged `text_layer_uncertain`; the flowchart is read by the vision model |
| 410 p5 I.A | `pedsready.org` | (correct) | a URL matches the ligature check | flagged `text_layer_uncertain` (harmless false positive in the references) |

---

## 4. `qa_gold.jsonl`: 59 lookup questions

### Schema

`{"id", "q", "answer_quote", "doc", "section", "page", ...}` plus `category`, `answer_type`, and where
relevant `alt_pages`, `note`, `answer_set`, `answer_set_full_names` and `answer_cells`.

- `answer_type: "quote"` (49 questions: 19 in qa01-qa25, all 30 answerable ones in qa26-qa59):
  `answer_quote` is an exact contiguous span of the document. It was checked automatically against the cited
  page's text layer after whitespace collapsing and NFKC. The one exception is qa02 (the G.F.A.S.T. box), whose
  quote uses the correct rendered spelling (see below). qa06 is quoted from the flowchart image, which has no
  text layer. For qa26-qa59 the quote was also checked against the text of the cited section as Herald indexes
  it, and `tests/test_knowledge.py` now checks every quoted answer that way (the cited section and its sub-items;
  figure pages and flagged text layers excepted).
- `answer_type: "table_lookup"` (3 questions, qa19-qa21): the answer comes from Table B cells, so
  there is no prose to quote. `answer_quote` is a canonical rendering such as
  `"Comprehensive Stroke Center: ECH, GSH, KSC, RSJ, SUH"`. **Score these with `answer_set`** (a set of
  abbreviations; `answer_set_full_names` gives the Table A names) **or `answer_cells`**. `page` is 20
  (clean copy), and `alt_pages: [10]` is the identical redline copy.
- `answer_type: "unanswerable"` (7 questions, qa23-qa25 and qa56-qa59): `answer_quote`, `doc`, `section` and
  `page` are all `null`. The right behaviour is to refuse or say the documents do not cover it. qa23-qa25 were
  checked with a grep over the first five text layers; qa56-qa59 over all 31 indexed PDFs (e.g. no "ketamine",
  "cyanide" or "hydroxocobalamin" anywhere). qa23-qa25 were re-checked against the 26 added documents and
  still have no answer.
- `section` uses the same `number` format as `sections_key.jsonl` ("3.2.1", "VI.E.1.c", "III.A.1"),
  plus "7" for the flowchart and "Table B" for table lookups.
- `page` is the physical PDF page. `alt_pages` lists duplicate copies in the AO file (redline versus clean).
  The AO file holds two indexed documents, so a question's document is the one whose page range holds `page`
  (602: pages 12-21, 605: pages 25-27; `herald.knowledge.document_for_page`).
- The questions were written from the PDFs, in the words a paramedic would use on a call ("heads-up",
  "the lungs still sound clear", "Viagra last night"), not in the protocol's wording, so keyword overlap alone
  does not answer them.

### Coverage

| Topic | Questions |
|---|---|
| Stroke alert window (24 h, section text and flowchart) | qa01, qa06 |
| G.F.A.S.T. items and scoring | qa02 |
| G.F.A.S.T. routing: 4 -> CSC, 3 or fewer -> closest SC, 45-minute rule (700-A13 and Policy 602) | qa03, qa04, qa05, qa07 |
| Glucose first and the hypoglycemia handoff to 700-A03 (700-A13 and 700-S04) | qa08, qa09, qa10 |
| Seizure exclusion | qa11 |
| Other stroke BLS/documentation (position, wake-up stroke, historian contact) | qa12, qa13, qa14 |
| Radio report (Policy 501): demographics, alert statement, radio versus phone, timing | qa15, qa16, qa17, qa18 |
| Table B stroke destinations (CSC list, PSC list, a negative cell) | qa19, qa20, qa21 |
| Stroke center levels (Policy 440 definitions) | qa22 |
| Unanswerable: tPA dose, stroke BP target, ringdown channel number | qa23, qa24, qa25 |
| Sepsis (700-A04): pre-notification rule, the EtCO2 SIRS criterion, the blood pressure goal | qa26, qa27, qa28 |
| Shock (700-A10): repeat fluid bolus | qa29 |
| Trauma (700-A16): care en route for a Trauma Alert, target scene time, the TXA injury-age limit | qa30, qa31, qa32 |
| Trauma Alert criteria and burns (Policy 605): fall height, age-65 SBP, major burn destination | qa33, qa34, qa35 |
| Chest pain / STEMI (700-A08, 700-M09): 12-lead timing, transmission, aspirin time, PDE-5 inhibitors, ST-elevation criteria | qa36-qa40 |
| Overdose (700-A15): charcoal contraindication, TCA QRS threshold | qa41, qa42 |
| Falls (700-S06): fall more than 72 hours ago, hip fracture destination, non-transport advice | qa43, qa44, qa45 |
| Hemorrhage control (700-M17): tourniquet over two hours, tourniquet placement, truncal hemorrhage | qa46, qa47, qa48 |
| Pediatrics (700-P10, P07, P02, S05, P03): shock bolus, drowning arrest destination, status epilepticus, age-based hypotension (table row), ROSC destination, neonatal hypoglycemia | qa49-qa54 |
| Documentation (Policy 500): 12-lead waveforms in the ePCR | qa55 |
| Unanswerable: ketamine dose, CPAP pressure, adult cardiac arrest termination, cyanide antidote | qa56-qa59 |

### Notes on specific items

- **qa02 (G.F.A.S.T.)**: the gold quote uses the rendered spelling. A parser that returns the
  text-layer version ("Abnormali.es", "Dri9", "Diﬃcul.es") has a glyph error. Decide whether your
  scorer gives partial credit.
- **qa04**: the answer is §3.2.1 ("closest Primary Stroke Center"), even though the flowchart's NO
  branch says "closest Stroke Center". A system that answers from the chart alone is wrong here.
- **qa06**: answerable only from the raster flowchart (section 7, page 3). This is a direct test of
  image understanding.
- **qa07**: the quote contains the source's own cross-reference error, "(F)(2)".
- **qa15**: the quote keeps the list letters ("a. Unit ID ... d. Patient’s Sex") because that is the
  contiguous text. Scorers may strip enumerators.
- **qa21**: tests reading an **empty** cell. VMC is checked for Primary but not Comprehensive Stroke Center.
- **qa24/qa25** are near misses on purpose: nearby text exists (700-S04 BP measurement, a morphine SBP
  threshold, 605 trauma SBP cut-offs, 501 "designated hospital ringdown channel"), but nothing answers
  the question.
- **qa27** ("Does a low end-tidal CO2 count toward sepsis?"): the answer is the criterion 1.3.4; 1.4 (two or
  more criteria) is the neighbouring rule.
- **qa32**: the question gives a four-hour-old injury; the county text only states the limit ("Injury is
  less than 3 hours old"), and the medic draws the conclusion.
- **qa33/qa34**: Policy 605 criteria restart their lettering under II.B, so II.W and II.N.3 are the printed
  paths (see the 605 quirks above).
- **qa37**: the quote stops before "(700-M09)", which the PDF breaks across a line as "(700-" / "M09)".
- **qa52** is a table-row lookup (700-S05 §11, "≥ 4 yr – 6 yr ... <70 + (age in yr x 2)"). The same threshold is
  also printed in 700-P07 12.1.1 (post-ROSC) and Policy 605 II.N.1 (trauma triage), in other contexts; strict
  scoring accepts only §11.
- **qa56-qa59** are near misses on purpose: 700-A16 3.5 sends pain to 700-S04 (no ketamine), 700-S04 4.4 points
  to 700-M12 for CPAP (not archived), 700-P07 5.2 is the pediatric termination rule while the adult protocol
  700-A07 is only in `archive/previous/` (superseded, not indexed), and 700-A15 covers other toxins.

### Suggested scoring normalisation

Collapse whitespace, apply Unicode NFKC, and treat curly and straight quotes and the en dash and hyphen
as equal. Match quotes by containment or a token-overlap threshold, not strict equality. The gold quotes
are short spans, and a correct answer may quote more around them.

---

## 5. Retrieval without the reranker (`eval/bench_protocols.py`)

`python eval/bench_protocols.py --runs 3` runs every question through `KnowledgeBase.search` (the app's
retrieval: 32 documents, 1,804 passages) in two modes: `bm25` (keyword only) and `hybrid` (BM25 plus
`BAAI/bge-base-en-v1.5` on the CPU, reciprocal-rank fusion, as the app ranks before the local model reranks).
A hit is the cited (document, section). Measured 2026-09-24:

| Mode | Questions | top-1 | top-3 | top-5 | in the 8 the reranker sees | right document first |
|---|---|---|---|---|---|---|
| bm25 | all 52 answerable | 18 (0.346) | 29 (0.558) | 34 (0.654) | 40 (0.769) | 30 (0.577) |
| bm25 | qa01-qa25 (22) | 7 | 13 | 16 | 16 | 12 |
| bm25 | qa26-qa55 (30) | 11 | 16 | 18 | 24 | 18 |
| hybrid | all 52 answerable | 26 (0.500) | 37 (0.712) | 41 (0.788) | 43 (0.827) | 38 (0.731) |
| hybrid | qa01-qa25 (22) | 9 | 15 | 16 | 18 | 15 |
| hybrid | qa26-qa55 (30) | 17 | 22 | 25 | 25 | 23 |

- **Genuine, not noise:** both modes are deterministic on the CPU (3 runs each, identical ranks). The sample is
  small: one question is about 2 points on the full set and 3-5 points on a subset.
- **More documents, more distractors:** scored against the 5-document index, the original 22 questions got
  10 / 17 / 19 (hybrid top-1 / top-3 / in 8) and 7 / 12 / 16 (bm25). With 32 documents: 9 / 15 / 18 and
  7 / 13 / 16. Six of the 22 moved (hybrid rank, 5 → 32 documents): the glucose questions lost ground to the
  new hypoglycemia protocols (qa10 1 → 2 behind 700-A03 2.1; qa08 6 → beyond 8, 700-A13 2.2 pushed out by
  glucose items), qa03 fell 3 → 6 and qa21 3 → 4, and qa02 and qa17 rose 3 → 2 (BM25 term weights change
  with a larger corpus).
- **Where the hybrid misses (not in the top 3):** right document, neighbouring section (qa27 EtCO2 → 1 / 4 /
  1.4 of 700-A04; qa51 → 700-P02 §3); the answer in a figure (qa06, text only after the vision model reads the
  flowchart); a label limit (qa52: 700-P07 12.1.1 and 605 II.N.1 state the same threshold); and genuine
  vocabulary misses: qa26 ("heads-up" for a sepsis patient ranks Policy 605/602 notification text first),
  qa30 (care on scene for a Trauma Alert ranks 602/605 alert definitions first), qa05 and qa08 (stroke routing and
  glucose, pulled to Policy 602 and 700-S04), qa14 (the historian's phone number, pulled to Policy 440).
- The reranker (`vision_bench.py --tasks rerank`) chooses from the 8 passages above, so 43 of 52 is its ceiling
  on this set. Unanswerable questions need its refusal and are not scored here.

---

## Uncertainties and judgement calls (complete list)

1. **Table B: no open uncertainty.** Three independent methods agree on all 168 cells. The only
   judgement calls are (a) naming EPS from the policy text, since it is not in Table A, and (b)
   keeping "STH" for Kaiser Foundation San Jose as printed.
2. **Flowchart, "GFAST 1-3" hyphen versus en dash**: judged a hyphen at 4x zoom (Calibri-like font,
   short dash). If your scorer is strict about characters, normalise dashes.
3. **Flowchart, node text line-joining**: `text` joins lines with single spaces. The n1 sub-line
   keeps its leading "- ". A parser might reasonably drop the hyphen or treat the sub-line as a
   separate note.
4. **Flowchart edge labels**: the labels sit on the connector lines. The label-to-edge assignment is
   unambiguous.
5. **Sections, scope**: every enumerated item is keyed (Roman, letter, number and lower-case letter
   levels), not just bold headings, in all parts of the AO file, including both redline copies. A
   scorer that wants only "headings" can keep level-1 rows plus letter items with short titles, but that
   selection is a scoring choice, not part of the key.
6. **Sections, 605 criteria A.-X.**: printed as level-2 peers of II.A/II.B, even though they are
   logically children of II.B or of the unnumbered subheads. They are keyed as printed (level 2, path
   `II.<letter>`).
7. **Sections, titles** are truncated at 10 words (the "first words" rule). Headings are complete.
8. **Sections, `doc_title`/`table_caption`/`unnumbered_heading`/`box_item` rows** go beyond the
   numbered-section request. They are included for completeness and can be filtered with `kind`.
9. **QA table questions** have no prose quote, so `answer_quote` is a synthetic canonical string.
   Score with `answer_set`/`answer_cells`.
10. **Currency**: the archive predates AO 2025-006 and AO 2025-007, which amend Policy 602. Table B in
    force today may differ from this key.
11. **Added documents, currency**: 700-A08, A03, A15, P03, P11, P15 and P16 are the 2025-01-01 versions (not
    revised for 2026), 700-M09 is 2024-01-01 and was read from the pre-migration county site, and Policy 500
    is 2020-01-01; see `docs/research/county_protocols_2026-09.md` §2 for how "current" was established.
12. **Policy 410 levels** come from indentation (the only outline keyed that way); the enumerator sequence
    gives the same tree (the splitter uses the sequence, and the two agree on all 99 items).
13. **Figure rows** record where image content is, not what it says. Only 700-A13's flowchart has a content
    key (`flowchart_700a13_key.json`); the seven new figures have none yet.
14. **700-A18 "≥"**: judged from the font (SymbolMT, code 0xB3 = greaterequal) and the printed words
    "(greater than or equal to)" next to the first one.
15. **Standalone headings at a page break** (430 VII.B.3) were keyed as heading-only titles by eye; the rule in
    §3 looks at the same page only.

## Reproducing

Everything was derived with these commands (N = physical page):

```
pdffonts -f N -l N <pdf>                 # fonts per page (Wingdings2 on Table B pages)
pdftotext -layout|-raw -f N -l N <pdf> - # text layer
pdftotext -bbox-layout -f N -l N <pdf> out.html   # word boxes for glyph/outline keying
pdftohtml -xml -i -f N -l N -stdout <pdf>         # per-run font + colour (R glyph font, blue insertions)
pdftoppm -r 100..200 [-gray] [-x -y -W -H] -f N -l N -png <pdf> out  # renders/crops for visual checks
pdfimages -list | -png -f 3 -l 3 <700-A13 pdf> out                   # raster flowchart at native res
pdfimages -list <pdf>; pdftotext -layout -f N -l N <pdf> - | wc -w   # figure pages (2026-09-24 part)
python eval/bench_protocols.py --runs 3                              # §5 (CPU only)
```

Pillow/numpy (already in the `zgx` env; nothing was installed) were used only to composite the
flowchart's soft mask, make zoomed crops and measure cell darkness for the Table B pixel check.
