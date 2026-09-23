# Protocol-parser bake-off: answer keys

This folder holds the gold-standard answer keys that document parsers are scored against. It covers
five archived Santa Clara County EMS PDFs in `data/protocols/santa_clara/archive/`. The keys were
built by hand, using only CPU tools: poppler-utils (`pdftotext`, `pdftoppm`, `pdffonts`,
`pdfinfo`, `pdfimages`, `pdftohtml -xml`) plus Python (Pillow/numpy for pixel checks). No model,
OCR engine or GPU was used, so no parser output can have leaked into the keys.

| File | What it keys | Size |
|---|---|---|
| `table_b_key.json` | Policy 602 "Table B: Approved In-County Services" (hospital x service grid of check marks) | 12 facilities x 14 service levels = 168 cells, 84 checked |
| `flowchart_700a13_key.json` | 700-A13 page 3 "Stroke Center Transport Determination Flow Chart" (raster image) as a graph | 8 nodes, 7 edges |
| `sections_key.jsonl` | Every numbered section/outline item in the 5 PDFs, plus a few unnumbered headings flagged by `kind` | 600 lines (568 numbered sections + 32 unnumbered title/caption/subhead/box rows) |
| `qa_gold.jsonl` | 25 paramedic-style lookup questions with an exact quote and a citation | 22 answerable + 3 unanswerable |

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

`2026-policy-protocol-changes-summary.pdf` in the archive folder is out of scope and has no key.

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
| `kind` | `section` (a numbered or lettered outline item). The others are included so scorers can filter them: `doc_title` (the big centred document title), `table_caption` (Table A-E captions in Policy 602), `unnumbered_heading` (the 4 bold criteria subheads in Policy 605), `box_item` (the 5 G.F.A.S.T. box rows in 700-A13) |
| `part` | AO file only: which embedded document the entry belongs to (see the page map above) |
| `parent`, `score_as_printed`, `text_layer`, `text_layer_error` | `box_item` rows only (see "Text-layer errors") |

**`number` format.**
- Decimal protocols (700-A13, 700-S04): the printed number without its trailing period, e.g.
  `"3.2.1"`. `level` is the number of components (1 = the grey-bar headings "1." ... "11.",
  2 = "x.y", 3 = "x.y.z").
- Outline policies (501, 440, 602, 605, AO memo): the full hierarchical path joined with dots, e.g.
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

## 4. `qa_gold.jsonl`: 25 lookup questions

### Schema

`{"id", "q", "answer_quote", "doc", "section", "page", ...}` plus `category`, `answer_type`, and where
relevant `alt_pages`, `note`, `answer_set`, `answer_set_full_names` and `answer_cells`.

- `answer_type: "quote"` (19 questions): `answer_quote` is an exact contiguous span of the document.
  It was checked automatically against the cited page's text layer after whitespace collapsing and
  NFKC. The one exception is qa02 (the G.F.A.S.T. box), whose quote uses the correct rendered spelling
  (see below). qa06 is quoted from the flowchart image, which has no text layer.
- `answer_type: "table_lookup"` (3 questions, qa19-qa21): the answer comes from Table B cells, so
  there is no prose to quote. `answer_quote` is a canonical rendering such as
  `"Comprehensive Stroke Center: ECH, GSH, KSC, RSJ, SUH"`. **Score these with `answer_set`** (a set of
  abbreviations; `answer_set_full_names` gives the Table A names) **or `answer_cells`**. `page` is 20
  (clean copy), and `alt_pages: [10]` is the identical redline copy.
- `answer_type: "unanswerable"` (3 questions, qa23-qa25): `answer_quote`, `doc`, `section` and `page`
  are all `null`. The right behaviour is to refuse or say the documents do not cover it. Each was
  checked with a grep over all five text layers.
- `section` uses the same `number` format as `sections_key.jsonl` ("3.2.1", "VI.E.1.c", "III.A.1"),
  plus "7" for the flowchart and "Table B" for table lookups.
- `page` is the physical PDF page. `alt_pages` lists duplicate copies in the AO file (redline versus clean).

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

### Suggested scoring normalisation

Collapse whitespace, apply Unicode NFKC, and treat curly and straight quotes and the en dash and hyphen
as equal. Match quotes by containment or a token-overlap threshold, not strict equality. The gold quotes
are short spans, and a correct answer may quote more around them.

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

## Reproducing

Everything was derived with these commands (N = physical page):

```
pdffonts -f N -l N <pdf>                 # fonts per page (Wingdings2 on Table B pages)
pdftotext -layout|-raw -f N -l N <pdf> - # text layer
pdftotext -bbox-layout -f N -l N <pdf> out.html   # word boxes for glyph/outline keying
pdftohtml -xml -i -f N -l N -stdout <pdf>         # per-run font + colour (R glyph font, blue insertions)
pdftoppm -r 100..200 [-gray] [-x -y -W -H] -f N -l N -png <pdf> out  # renders/crops for visual checks
pdfimages -list | -png -f 3 -l 3 <700-A13 pdf> out                   # raster flowchart at native res
```

Pillow/numpy (already in the `zgx` env; nothing was installed) were used only to composite the
flowchart's soft mask, make zoomed crops and measure cell darkness for the Table B pixel check.
