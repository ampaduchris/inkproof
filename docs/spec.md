# inkproof specification (draft)

Status: adopted on 19 Nov 2026 by session 1.2 from frontload draft F2 (Fable 5.2 / high, 14 Nov 2026). Sources for the identifier rules are recorded in `docs/REASONING_AUDIT.md`. Departures from `BUILD.md` are numbered in `docs/DEVIATIONS.md`.

Evidence: section 12 lists what was measured on 14 Nov 2026 (PyMuPDF 2.1 and pdfminer.six) and on 19 Nov 2026 (pypdf), and what was not checked.

## 1. Purpose

inkproof removes chosen text from a PDF (Portable Document Format) file and then proves, by re-reading the file it is about to write, that the text is gone. It also audits PDFs redacted by other tools.

This document is the sole authority for behaviour. Prompts, README text and tests never override it.

### 1.1 The claim, exactly

After `apply` exits with code 0, no requested term and no requested pattern match can be found in any surface listed in section 4 of the output file, by either of two independent text extraction engines, by a scan of every decoded stream and string in the file, or in any earlier revision of the file.

### 1.2 What is not claimed

| Limit | Meaning |
| --- | --- |
| LIM-1 Images | Text that exists only as pixels is not examined. There is no optical character recognition. |
| LIM-2 Accents | `Müller` does not match `Muller` or `Mueller`. List each spelling. |
| LIM-3 Page breaks | A match split across two pages is not found. |
| LIM-4 Reading order | Matching follows the order in which each engine returns text. Text that an engine returns in scattered order (some multi-column or rotated layouts) can be missed by that engine. |
| LIM-5 Meaning | The tool finds strings. It does not know that "the claimant" refers to a named person. |
| LIM-6 Custom font encodings in the raw scan | The raw scan (section 6, check V4) decodes strings with standard encodings only. Text in fonts with private encodings is covered by the extraction checks V1 and V2, not by V4. |

The README repeats this table. The words "text layer" are used wherever the claim is stated; the words "the document is clean" are never used.

## 2. Conventions

- MUST, MUST NOT, SHOULD and MAY have their usual specification meaning. Every MUST and MUST NOT has at least one test. A SHOULD without a test is allowed.
- Requirement ids are `REQ-###`. Ids are never reused or renumbered. A removed requirement keeps its row with the text "withdrawn" and the reason.
- Tests are tagged `@pytest.mark.req("REQ-###")`. One test may carry several tags.
- `scripts/trace.py` reads every table row in this file that begins `| REQ-`, reads the tags, prints the matrix, and exits 1 if any MUST or MUST NOT has no test, if a test is tagged with an id that is not in this file, or if a row of section 11.1 names no MUST. Until session 1.8 the continuous integration job runs it with `--report-only`, which prints the same matrix and the same errors but exits 0 for untested requirements (DEV-007).
- Fixture ids (R1, A03, X02 and so on) refer to section 10.

## 3. Definitions

**Unit.** A letter or digit after normalisation (Unicode general categories L and N).

**Normalisation.** Applied to terms and to document text before matching, in this order: Unicode normalisation form NFKC; removal of the soft hyphen (U+00AD) and of zero-width characters (U+200B, U+200C, U+200D, U+2060, U+FEFF); full case folding.

**Term.** One line of the terms file after trimming. Its identity in reports is its line number, never its text.

**Pattern.** A built-in recogniser from section 5.2, named `iban`, `de-tax-id`, `uk-ni` or `email`.

**Source.** A term or a pattern. Every match has exactly one source.

**Exact match.** The normalised term occurs in the normalised text, where each run of white space in the term matches any non-empty run of white space in the text (line breaks included), and the character before and the character after the match are not units.

**Loose match.** As an exact match, with two relaxations: a run of white space may occur between any two adjacent characters of the term; and a hyphen followed by a line break may occur between any two adjacent units. A loose match that is also an exact match is reported as exact.

Loose matching exists because PDF text is often stored in fragments. A measured example: the fragments `HO`, `TEL-SE`, `CRET` with a wide gap after the first are returned by both engines as `HO TEL-SECRET`.

**Match kind.** `exact` or `loose`.

**Surface.** A place in a PDF where text can live. Section 4 lists them.

**Revision.** A PDF may hold earlier versions of itself, appended as incremental updates. Each version is a revision. The last is the current revision.

**Leak.** A match of a requested source found on any surface. In `apply`, a leak found by verification is a survivor.

**Leak class.** How a page-text match is hidden, from section 7.2.

**Canary.** A unique synthetic string planted in a test fixture as a term or pattern value, used to prove that a value does or does not appear somewhere.

## 4. Surfaces

| Id | Surface | Contents examined |
| --- | --- | --- |
| S1 | Page text | All text drawn by page content, including text inside nested form objects; regardless of position, colour, render mode, size, clipping or layer visibility |
| S2 | Annotations | Contents, rich text, title, subject, appearance text and link targets of every annotation, pop-ups included |
| S3 | Form fields | Field names, values, default values, choices and tooltips |
| S4 | Metadata | The document information dictionary and the XMP (Extensible Metadata Platform) packet |
| S5 | Navigation | Outline (bookmark) titles, named destination names, page labels |
| S6 | Embedded files | File names, descriptions and decoded file contents |
| S7 | Actions | Script source and target addresses of document, page and annotation actions |
| S8 | Earlier revisions | Surfaces S1 to S7 of every revision before the current one |
| S9 | Structure | Alternative text, actual text and expansion text in the structure tree |
| S10 | Layer names | Names of optional content groups |
| S11 | Raw objects | Every stream after decoding, and every string object, in the whole file |

Images are not a surface (LIM-1).

## 5. Inputs

### 5.1 Command line

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-001 | MUST | `inkproof apply IN --terms FILE --patterns LIST -o OUT` runs the apply procedure of section 6 on `IN` and writes the result to `OUT`. | `test_cli_apply_happy_path` on R1: exit 0, `OUT` exists, report result `clean`. |
| REQ-002 | MUST | `inkproof audit FILE --terms FILE --patterns LIST` runs the audit procedure of section 7 on `FILE`. | `test_cli_audit_happy_path` on A01: exit 1, one finding. |
| REQ-003 | MUST | At least one of `--terms` and `--patterns` is required in both commands. With neither, the tool exits 2 and changes nothing. | `test_cli_requires_a_source`. |
| REQ-004 | MUST | `--patterns` takes a comma-separated list of names from section 5.2. An unknown name exits 2 and names the unknown pattern (a pattern name is not a matched value). | `test_cli_unknown_pattern`. |
| REQ-005 | MUST | `--report PATH` writes the JSON report of section 8 to `PATH` in both commands. Without it, `audit` writes the report to standard output and `apply` writes it to `OUT` with `.report.json` appended. | `test_report_destinations`, three cases. |
| REQ-006 | MUST | `apply` refuses to run when `OUT` and `IN` are the same file (compared after resolving links), exit 2. | `test_apply_refuses_in_place`, including a symbolic link case. |
| REQ-007 | MUST | `apply` refuses to overwrite an existing `OUT` unless `--force` is given, exit 2. | `test_apply_no_overwrite_without_force`. |
| REQ-008 | MUST | `--version` prints the tool version and exits 0. `--help` documents every option and every exit code. | `test_cli_version_and_help` checks each exit code number appears in help. |
| REQ-009 | SHOULD | `--substring` disables the rule that a match must not touch a unit on either side. | None required. |

### 5.2 Terms file

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-010 | MUST | The terms file is UTF-8 text, one term per line. A leading byte order mark is ignored. Blank lines and lines whose first non-space character is `#` are ignored. Leading and trailing white space is trimmed. | `test_terms_parsing`, six cases. |
| REQ-011 | MUST | A terms file that cannot be read, is not valid UTF-8, or yields no terms exits 2. | `test_terms_file_errors`, three cases. |
| REQ-012 | MUST | A term with fewer than three units after normalisation exits 2 and reports the line number only, unless `--allow-short-terms` is given. | `test_short_term_rejected` asserts the line number is in the message and the term is not. |
| REQ-013 | MUST | Terms are matched under the normalisation of section 3: case-insensitive, NFKC, soft hyphens and zero-width characters ignored. | `test_term_normalisation`: upper and lower case, a ligature form, a soft hyphen inside the word, a zero-width joiner inside the word. Fixture X01. |
| REQ-014 | MUST | Exact matches are found: white space in a term matches any white space run in the text, a line break included. | `test_term_across_line_break` on R1 (two-word term split over two lines). |
| REQ-015 | MUST | Loose matches are found: stray white space inside a word, and a word hyphenated at a line end. | `test_term_loose_match` on X01 (fragmented text) and R5 (hyphenated at line end). |
| REQ-016 | MUST | A match never begins or ends inside a longer run of units: the term `ann` does not match inside `annual`. | `test_term_boundaries`, plus Hypothesis property P1. |
| REQ-017 | MUST | Duplicate terms (equal after normalisation) are treated as one source, identified by the first line number. | `test_duplicate_terms`. |

### 5.3 Built-in patterns

Every pattern is matched on normalised text. Between the groups shown, a pattern accepts no separator or one space (exact), or any white space run including a line break (loose). A pattern match never touches a unit on either side.

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-020 | MUST | `iban` (International Bank Account Number): two letters, two check digits, then 11 to 30 letters or digits, written without separators or in groups of four. The country code must be in the embedded length table and the total length must equal that country's length. The value must pass the ISO 13616 check: move the first four characters to the end, replace each letter by its number (A is 10, Z is 35), and the resulting integer modulo 97 equals 1. | `test_iban_pattern`: published example values for Germany (22 characters) and the United Kingdom (22 characters) match in compact and grouped form; one changed digit does not match; wrong length for the country does not match. Property P2. |
| REQ-021 | MUST | The length table is a data file that records the registry release it was taken from. Germany and the United Kingdom are fixed at 22 by test. | `test_iban_length_table_has_source_and_fixed_rows`. |
| REQ-022 | MUST | `de-tax-id` (German tax identification number, Steuer-Identifikationsnummer): 11 digits, written without separators or grouped 2-3-3-3; the first digit is not 0; the eleventh digit is the ISO 7064 MOD 11,10 check digit of the first ten (section 5.4). | `test_de_tax_id_pattern`: the five published values of section 5.4 that start with a non-zero digit match in both forms; the published test number that starts with 0 does not match; a changed check digit does not match; a 12-digit run does not match. Property P3. |
| REQ-023 | SHOULD | `de-tax-id` also applies the issuer's structure rule: among the first ten digits exactly one digit occurs twice or three times, and where it occurs three times the three are not at consecutive positions. The rule is confirmed from the issuer's own document (`docs/REASONING_AUDIT.md`, RA-2). The filter is off in 1.0: the wider match of REQ-022 stands, because a missed identifier is worse than an extra redaction. | None required. |
| REQ-024 | MUST | `uk-ni` (United Kingdom National Insurance number): two letters, six digits, one letter from A to D, written without separators or as `LL DD DD DD L`. The first letter is not D, F, I, Q, U or V. The second letter is not D, F, I, O, Q, U or V. The prefix is not BG, GB, KN, NK, NT, TN or ZZ. | `test_uk_ni_pattern`: valid shapes match in both forms; each excluded first letter, second letter and prefix does not match; suffix E does not match. Property P4. |
| REQ-025 | MUST | `email`: a local part of 1 to 64 characters from letters, digits and `. _ % + -`, not starting or ending with a dot; `@`; a domain of one or more labels of letters, digits and inner hyphens separated by dots; a final label of at least two letters. | `test_email_pattern`, ten cases, addresses on reserved example domains only. Property P5. |
| REQ-026 | MUST | On a fixed synthetic corpus of 10,000 words of plain prose with no planted identifiers, all four patterns together produce zero matches. The corpus is committed and generated from a seed. | `test_patterns_no_false_positives_on_corpus`. |
| REQ-027 | MUST | Where matches overlap, the union of their extents is treated as one removal area and each source is counted once. | `test_overlapping_matches` (an email address that contains a listed term). |

### 5.4 The tax number check digit

Start with `product = 10`. For each of the first ten digits `d`, left to right: `sum = (d + product) mod 10`; if `sum` is 0, set it to 10; `product = (2 * sum) mod 11`. The check digit is `11 - product`, or 0 when that gives 10.

The issuer publishes the same procedure as code (n = 11, m = 10) and six example numbers: 02476291358 (marked as a test number, leading 0), 86095742719, 47036892816, 65929970489, 57549285017 and 25768131411. Checked on 19 Nov 2026: this procedure accepts all six. The issuer marks five of them as illustrations that must not be used in real or test transmissions to the tax authority. inkproof never transmits anything, so it uses them as fixture canaries only (RA-2, RA-3).

The issuer's structure rule (REQ-023) was also run on all six. All pass when the rule is read as "the three equal digits are not all adjacent". 65929970489 has the digit 9 at positions 3, 5 and 6, so a reading of "no two equal digits adjacent" would reject an example the issuer lists.

## 6. Apply

Apply runs four steps: find, remove, serialise, verify. The file reaches `OUT` only if verification passes.

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-030 | MUST | Every exact and loose match on S1 is removed from the page content: the glyphs are deleted from the text layer, not covered. | `test_removal_matrix`: 4 patterns and 2 terms on each of R1 to R5 (30 cases). Each asserts the canary is absent from both engines' text and from the text returned by pypdf, the third cross-check engine. |
| REQ-031 | MUST | Removal is by whole glyph. Any glyph whose box intersects a match is removed entirely. | `test_whole_glyph_removal` on R5 (kerned text): no partial word remnant containing a canary character run of three or more. |
| REQ-032 | MUST | Matches on S1 are found and removed wherever the text sits: outside the page boxes, in white or any other colour, in invisible render mode, under shapes or images, inside nested form objects. | `test_removal_of_hidden_text` on A01, A03, A05, A06, A09 and X05. Measured need: the default page text call of the first engine does not return off-page text; the text trace does. |
| REQ-033 | MUST | A filled black rectangle is drawn over each removal area unless `--no-mark` is given. | `test_mark_drawn` and `test_no_mark`. |
| REQ-034 | MUST | All annotations (S2) and all form fields (S3) are removed from the output. The report counts them by type. | `test_annotations_and_fields_stripped` on A08 and A10. |
| REQ-035 | MUST | The information dictionary is emptied and the XMP packet is removed (S4). | `test_metadata_stripped` on A10: every information field empty, no XMP stream in the file. |
| REQ-036 | MUST | Embedded files (S6) and all scripts and actions (S7) are removed. The report counts them. | `test_embedded_files_and_actions_stripped` on A10. |
| REQ-037 | MUST | An outline title (S5) that contains a match is replaced by the fixed text `[REDACTED]`. Other outline entries are kept. | `test_outline_titles_redacted` on A10. |
| REQ-038 | MUST | If any match is found on S9, the structure tree is removed from the output and the report says so. | `test_structure_tree_dropped_on_match` on X07. |
| REQ-039 | MUST | The output is written as a complete new file, never as an incremental update. It contains exactly one revision and no unreferenced objects. | `test_output_single_revision` on R1 and on A07 as input: one revision by the engine's count and one end-of-file marker in the bytes. |
| REQ-040 | SHOULD | Image pixels under a removal area are blanked. | None required. |
| REQ-041 | SHOULD | The same input and arguments give a byte-identical output file. | None required. |

### 6.1 Verification

Verification runs on the serialised bytes of the candidate output, re-opened from those bytes. It never runs on the in-memory document that was edited.

| Check | What it does |
| --- | --- |
| V1 | Engine A (PyMuPDF text trace, which is not clipped to the page) extracts S1; the matcher runs on the result |
| V2 | Engine B (pdfminer.six) extracts S1; the matcher runs on the result |
| V3 | S2 to S7, S9 and S10 are enumerated through the document structure; the matcher runs on every string found |
| V4 | S11: every stream is decoded and every string object is decoded from literal or hexadecimal form as PDFDocEncoding, UTF-16 and UTF-8; the strings of one text-showing operator are joined before matching |
| V5 | S8: the file has exactly one revision |

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-045 | MUST | Verification cannot be skipped. There is no option that writes `OUT` without it. | `test_no_skip_verify_option` inspects the command's options; `test_verify_always_runs` counts calls. |
| REQ-046 | MUST | Checks V1 to V5 all run on the re-opened serialised bytes, with the same sources and both match kinds. | `test_verify_uses_serialised_bytes` (the in-memory document is poisoned after serialisation; verification still passes). |
| REQ-047 | MUST | V1 and V2 use two extraction engines that share no parsing code. pypdf is a third engine used only by the test suite (REQ-030); it is a development dependency, not a runtime one. | `test_two_engines_listed_in_report`; `test_each_engine_catches_alone` (each engine in turn is stubbed to return nothing; the other still catches a planted survivor). |
| REQ-048 | MUST | V4 finds a match stored as a hexadecimal string, as UTF-16, and split across the elements of one text-showing operator. | `test_raw_scan_encodings` on X02. Measured need: a plain byte search does not find text stored as a hexadecimal string. |
| REQ-049 | MUST | If any check finds a survivor, `apply` exits 1, no file exists at `OUT`, and the report lists each survivor by surface, page, source and count. | `test_survivor_fails_closed`, one case per check V1 to V5, each with the removal step stubbed to leave one canary on one surface. |
| REQ-050 | MUST | A match on a surface that apply does not edit (named destinations, page labels, layer names) is therefore a survivor and fails the run. | `test_verify_only_surfaces_fail_closed` on X08. |
| REQ-051 | MUST | The report records each check with its engine name, engine version and result. | `test_report_checks_section`. |

## 7. Audit

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-055 | MUST | Audit never changes the audited file. | `test_audit_does_not_modify`: SHA-256, size and modification time equal before and after, on a read-only file and a writable one. |
| REQ-056 | MUST | Audit examines every surface S1 to S11 with both match kinds and reports each leak with surface, leak class (S1 only), page, revision, source and count. | `test_audit_surfaces`: one planted canary per surface. |
| REQ-057 | MUST | Audit exits 1 when at least one leak is found and 0 when none is found. | `test_audit_exit_codes` on A01 and on control C01. |
| REQ-058 | MUST | Audit of control fixture C01 (correctly redacted, single revision) reports no leaks. | `test_audit_control_is_clean`. |

### 7.1 Earlier revisions

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-060 | MUST | Audit counts the revisions in the file and reports the number. | `test_revision_count` on A07 (2) and R1 (1). |
| REQ-061 | MUST | Audit reconstructs every earlier revision and examines S1 to S7 of each. A match present in an earlier revision is reported with that revision's number and class `earlier-revision`. | `test_incremental_update_leak` on A07: text removed in revision 2 is reported in revision 1. Measured need: both engines return clean text for the current revision of such a file, and a byte search finds nothing. |

### 7.2 Leak classes for page text

Each S1 match in the current revision gets exactly one class. Where several apply, the first in this order wins.

| Class | Rule |
| --- | --- |
| `off-page` | Every glyph box of the match lies wholly outside the crop box, or outside the media box where no crop box is set |
| `invisible` | The text is drawn in a render mode that neither fills nor strokes, or with zero opacity |
| `covered` | A filled path with opacity 1, or an image, drawn later than the text covers at least 90% of the area of the match |
| `same-colour` | The fill colour of the text equals, within 0.02 per channel, the colour directly beneath it: the fill of the nearest earlier covering path, or white where there is none |
| `visible` | None of the above |

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-065 | MUST | Text under a filled shape is classed `covered`. | `test_class_covered_shape` on A01. |
| REQ-066 | MUST | Text under an image is classed `covered`. | `test_class_covered_image` on A02. |
| REQ-067 | MUST | White text on a white page is classed `same-colour`. | `test_class_white_on_white` on A03. |
| REQ-068 | MUST | Text whose colour equals a coloured panel beneath it is classed `same-colour`. | `test_class_same_colour_panel` on A04. |
| REQ-069 | MUST | Text outside the media box, and text inside the media box but outside the crop box, are classed `off-page`. | `test_class_off_page` on A05 and A06. |
| REQ-070 | MUST | Text in invisible render mode is classed `invisible`. | `test_class_invisible` on A09. |
| REQ-071 | MUST | Matches in annotations are reported with surface S2, for free-text annotations and for pop-up notes. | `test_annotation_leaks` on A08. |
| REQ-072 | MUST | Matches in metadata, outline titles, form field values and embedded files are reported with surfaces S4, S5, S3 and S6. | `test_non_page_surface_leaks` on A10. |
| REQ-073 | SHOULD | Further classes: `tiny` (effective font size under 1 point), `clipped` (outside the active clipping path), `hidden-layer` (in a layer that is off by default). | None required. |
| REQ-074 | MUST | The report lists pages that contain images and pages that contain images but no text, under `limits`. The one-line summary on standard error says the check covers the text layer only. | `test_image_limits_reported` on X06. |

## 8. Report

The report is one JSON object. It conforms to the JSON Schema in section 8.1, which ships in the package as `report.schema.json`.

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-075 | MUST | Every report validates against the shipped schema. | `test_report_validates`, run on the report of every other test through a fixture. |
| REQ-076 | MUST | The report contains no matched value, no term text, no text taken from the document, no file path and no file name. Files are identified by SHA-256 only. | `test_report_has_no_values`: canary search over the report for every fixture; `test_report_has_no_paths`. |
| REQ-077 | MUST | Locations are given as surface, page number and revision number only. No coordinates and no character offsets. | Schema forbids extra properties; `test_report_location_fields`. |
| REQ-078 | MUST | The report is deterministic: the same input bytes, arguments and tool version give a byte-identical report. It carries no timestamp. Keys are sorted; lists are sorted by surface, page, revision, source. | `test_report_deterministic` (two runs, equal bytes). |
| REQ-079 | MUST | `schema_version` is `1.0`. Any change that removes or renames a field raises the major number. | `test_schema_version`. |

### 8.1 Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "inkproof report",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "tool", "mode", "input", "output", "request",
               "removed", "actions", "findings", "checks", "limits", "result", "exit_code"],
  "properties": {
    "schema_version": {"const": "1.0"},
    "tool": {
      "type": "object", "additionalProperties": false,
      "required": ["name", "version"],
      "properties": {"name": {"const": "inkproof"}, "version": {"type": "string"}}
    },
    "mode": {"enum": ["apply", "audit"]},
    "input": {"$ref": "#/$defs/file"},
    "output": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/file"}]},
    "request": {
      "type": "object", "additionalProperties": false,
      "required": ["terms_count", "patterns", "options"],
      "properties": {
        "terms_count": {"type": "integer", "minimum": 0},
        "patterns": {"type": "array", "items": {"enum": ["iban", "de-tax-id", "uk-ni", "email"]}, "uniqueItems": true},
        "options": {"type": "array", "items": {"enum": ["substring", "allow-short-terms", "no-mark", "force"]}, "uniqueItems": true}
      }
    },
    "removed": {"type": "array", "items": {"$ref": "#/$defs/match"}},
    "actions": {
      "type": "object", "additionalProperties": false,
      "required": ["annotations_removed", "form_fields_removed", "metadata_removed",
                   "embedded_files_removed", "actions_removed", "outline_titles_redacted",
                   "structure_tree_removed"],
      "properties": {
        "annotations_removed": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
        "form_fields_removed": {"type": "integer", "minimum": 0},
        "metadata_removed": {"type": "boolean"},
        "embedded_files_removed": {"type": "integer", "minimum": 0},
        "actions_removed": {"type": "integer", "minimum": 0},
        "outline_titles_redacted": {"type": "integer", "minimum": 0},
        "structure_tree_removed": {"type": "boolean"}
      }
    },
    "findings": {"type": "array", "items": {"$ref": "#/$defs/match"}},
    "checks": {
      "type": "array",
      "items": {
        "type": "object", "additionalProperties": false,
        "required": ["id", "engine", "engine_version", "result"],
        "properties": {
          "id": {"enum": ["V1", "V2", "V3", "V4", "V5"]},
          "engine": {"type": "string"},
          "engine_version": {"type": "string"},
          "result": {"enum": ["pass", "fail", "not-run"]}
        }
      }
    },
    "limits": {
      "type": "object", "additionalProperties": false,
      "required": ["pages_with_images", "image_only_pages", "notes"],
      "properties": {
        "pages_with_images": {"type": "array", "items": {"type": "integer", "minimum": 1}},
        "image_only_pages": {"type": "array", "items": {"type": "integer", "minimum": 1}},
        "notes": {"type": "array", "items": {"enum": ["LIM-1", "LIM-2", "LIM-3", "LIM-4", "LIM-5", "LIM-6"]}}
      }
    },
    "result": {"enum": ["clean", "leaks-found", "error"]},
    "exit_code": {"enum": [0, 1, 2, 3, 4]}
  },
  "$defs": {
    "file": {
      "type": "object", "additionalProperties": false,
      "required": ["sha256", "pages", "revisions"],
      "properties": {
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "pages": {"type": "integer", "minimum": 0},
        "revisions": {"type": "integer", "minimum": 1}
      }
    },
    "match": {
      "type": "object", "additionalProperties": false,
      "required": ["surface", "page", "revision", "source", "match_kind", "count"],
      "properties": {
        "surface": {"enum": ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S9", "S10", "S11"]},
        "class": {"enum": ["visible", "covered", "same-colour", "off-page", "invisible",
                           "tiny", "clipped", "hidden-layer", "earlier-revision"]},
        "page": {"oneOf": [{"type": "null"}, {"type": "integer", "minimum": 1}]},
        "revision": {"type": "integer", "minimum": 1},
        "source": {
          "type": "object", "additionalProperties": false,
          "required": ["type", "id"],
          "properties": {
            "type": {"enum": ["term", "pattern"]},
            "id": {"type": ["integer", "string"]}
          }
        },
        "match_kind": {"enum": ["exact", "loose"]},
        "count": {"type": "integer", "minimum": 1}
      }
    }
  }
}
```

Field notes. `removed` is empty in audit mode. `findings` holds survivors in apply mode and leaks in audit mode. `output` is null in audit mode and whenever apply fails. `actions` holds zeros and false in audit mode. A match in an earlier revision carries that revision's number, the surface it was found on, and class `earlier-revision`; S8 is therefore not a value of `surface`. `page` is null for surfaces with no page. `source.id` is the terms file line number for a term and the pattern name for a pattern.

## 9. Output hygiene, exit codes and safety

### 9.1 Output hygiene

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-080 | MUST | No matched value and no term text is written to standard output, standard error, the report, or any log, at any verbosity, in any mode, on any exit path. | `test_no_value_in_any_output`: six cases (apply success, apply survivor, audit leaks, bad terms file, corrupt input, forced internal error). Each captures both streams and the report and searches for every canary in raw, normalised and space-stripped form. |
| REQ-081 | MUST | Error messages and tracebacks never contain document text or term text. An unexpected error prints a fixed message and an error code, and exits 4. `--debug` prints a traceback with all local values masked. | `test_internal_error_is_masked`, with and without `--debug`. |
| REQ-082 | MUST | Temporary files are created in a private directory readable by the current user only and are removed on every exit path. | `test_temp_files_cleaned`: directory listing before and after, for exit codes 0, 1, 3 and 4. |
| REQ-083 | MUST | The tool makes no network connection. | `test_no_network`: the socket layer is blocked for the whole suite. |

### 9.2 Exit codes

| Code | Meaning | `apply` | `audit` |
| --- | --- | --- | --- |
| 0 | Clean | Output written and verified | No leak found in the text layer |
| 1 | Leaks found | A survivor was found; no output written | At least one leak found |
| 2 | Usage or input error | Bad arguments, bad terms file, unsafe output path | Bad arguments, bad terms file |
| 3 | Document cannot be processed | Not a PDF, damaged, or needs a password | Same |
| 4 | Internal error | Unexpected failure; no output written | Unexpected failure |

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-085 | MUST | The tool exits only with the codes in this table, with these meanings. | `test_exit_codes`, one case per cell of the table (10 cases). |
| REQ-086 | MUST | Whenever `apply` exits with a code other than 0, no file exists at `OUT`, and a file that existed there before (with `--force`) is unchanged. | `test_no_output_on_failure`, for codes 1, 2, 3 and 4. |
| REQ-087 | MUST | `OUT` is written by renaming a fully written temporary file in the same directory, after verification has passed. | `test_atomic_write` (a failure injected before the rename leaves no partial file). |
| REQ-088 | MUST | A file that needs a password to open exits 3. A file that is not a PDF or cannot be parsed exits 3. | `test_unreadable_documents` on X03 and X04. |
| REQ-089 | MUST | `apply` never changes `IN`. | `test_apply_does_not_modify_input` (SHA-256 equal before and after, for exit codes 0 and 1). |

### 9.3 Platform and quality

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-090 | MUST | The tool runs on every Python version in the continuous integration matrix, on Linux. | The matrix itself; `test_cli_version_and_help` runs in each cell. |
| REQ-091 | MUST | Every fixture is generated by code in the repo from fixed seeds. No PDF from outside the repo is committed. Generating all fixtures twice gives byte-identical files. | `test_fixtures_regenerate_identically`. |
| REQ-092 | MUST | Mutation testing of the matcher and the verifier scores at least 80%. | The mutation job; the score is recorded in `docs/` with its date. |
| REQ-093 | SHOULD | A 100-page text document is processed in under 30 seconds on the continuous integration runner. | None required. |
| REQ-094 | SHOULD | The tool runs on macOS and Windows. | None required. |

## 10. Fixtures

All values planted in fixtures are canaries: synthetic, unique per fixture, and valid for the pattern they exercise. Email canaries use reserved example domains. Bank account canaries use published example numbers (the table of lengths and the examples come from session 1.4, N3). Tax and insurance numbers are taken only from values that their issuers publish as examples, listed in `docs/REASONING_AUDIT.md` RA-3:

- `de-tax-id`: the five published numbers of section 5.4 that start with a non-zero digit, plus the published test number starting with 0 as a negative case.
- `uk-ni`: `AA123456A`, `AB123456D` and `AA111111A` (HMRC Developer Hub sandbox examples); `QQ123456A` (the HMRC manual's own example, which has an excluded prefix) as a negative case.

No such number can be proved unissued. The audit entry says so.

### 10.1 Removal layouts (5)

Each holds one value per pattern and two terms, at known counts.

| Id | Layout |
| --- | --- |
| R1 | One column of prose, one page; one two-word term split across a line break |
| R2 | Two columns |
| R3 | A table with values in cells |
| R4 | Three pages with the values repeated in header and footer |
| R5 | Embedded subset font, justified and kerned text, one term hyphenated at a line end |

### 10.2 Audit fixtures (10)

| Id | Planted failure |
| --- | --- |
| A01 | Black rectangle drawn over live text |
| A02 | Image placed over live text |
| A03 | White text on a white page |
| A04 | Text in the colour of a coloured panel beneath it |
| A05 | Text outside the media box |
| A06 | Text inside the media box, outside the crop box |
| A07 | Two revisions: the text is present in the first and removed in the second |
| A08 | A free-text annotation and a pop-up note, each holding a value |
| A09 | Text in invisible render mode |
| A10 | Values in the information dictionary, the XMP packet, an outline title, a form field value and an embedded text file |

### 10.3 Control and edge fixtures (9)

| Id | Purpose |
| --- | --- |
| C01 | Control: correctly redacted, one revision, no leak on any surface |
| X01 | Fragmented text that extracts with a stray space inside a word; soft hyphen and zero-width characters inside a term |
| X02 | A value stored as a hexadecimal string, one as UTF-16, one split across the elements of one text-showing operator |
| X03 | A file that needs a password |
| X04 | A truncated file and a file that is not a PDF |
| X05 | A value inside a form object nested two levels deep |
| X06 | One page with an image and no text; one page with both |
| X07 | A tagged document with a value in alternative text |
| X08 | Values in a named destination name, a page label and a layer name |

This is 24 fixtures, not the 15 that session 1.1 lists (DEV-004).

## 11. Traceability

### 11.1 Scope bullets in BUILD.md

| Scope bullet | MUST requirements |
| --- | --- |
| `apply`: removes matches from the text layer | REQ-001, 030, 031, 032 |
| `apply`: strips metadata and annotations | REQ-034, 035, 036 |
| `apply`: re-scans extracted text | REQ-046, 047 |
| `apply`: re-scans raw byte strings | REQ-048 |
| `apply`: re-scans incremental-update history | REQ-039, 046 (check V5) |
| `apply`: fails if anything survives | REQ-045, 049, 050, 086 |
| `audit`: reports leaks without changing the file | REQ-002, 055, 056, 057 |
| Pattern: IBAN with checksum | REQ-020, 021 |
| Pattern: German tax identification number | REQ-022 |
| Pattern: UK National Insurance number | REQ-024 |
| Pattern: email | REQ-025 |
| Detects text hidden under shapes | REQ-065, 066 |
| Detects white text | REQ-067, 068 |
| Detects off-page text | REQ-069 |
| Detects incremental updates | REQ-060, 061 |
| JSON audit report | REQ-005, 075, 079 |
| Never prints a matched value, only counts and page numbers | REQ-076, 077, 080, 081 |
| Out of scope: optical character recognition | REQ-074 (the limit is reported) |

Every scope bullet maps to at least one MUST.

### 11.2 Test plan rows in BUILD.md

| Test plan row | Requirements | Count in this spec |
| --- | --- | --- |
| Removal: 4 patterns x 5 layouts | REQ-030 | 30 cases (terms added: 6 sources x 5 layouts) |
| Audit: 10 planted fixtures | REQ-061, 065 to 072 | 10 fixtures |
| Patterns: 8 properties | REQ-016, 020, 022, 024, 025, 026 | P1 to P8, section 11.3 |
| Output hygiene: 6 cases | REQ-080 | 6 cases |
| Mutation at least 80% | REQ-092 | matcher and verifier |
| Traceability 100% | Section 2 | `scripts/trace.py` |

### 11.3 Properties (Hypothesis)

| Id | Property |
| --- | --- |
| P1 | For any term and any text built by surrounding the term with units, there is no match; surrounded by non-units, there is exactly one |
| P2 | Any generated valid IBAN matches; changing any single character makes it not match |
| P3 | Any 10 digits with a non-zero first digit plus the computed check digit match `de-tax-id`; any other eleventh digit does not |
| P4 | Any string built from the allowed National Insurance alphabet matches; replacing the prefix with any excluded prefix does not |
| P5 | Any generated address from the email grammar matches as one whole match |
| P6 | Normalisation is idempotent: normalising twice equals normalising once |
| P7 | Inserting white space runs between the words of a term in the text never removes an exact match; inserting white space inside words yields a loose match |
| P8 | For any text and sources, every reported match extent contains only characters of the text, and removing all extents leaves a text with no match (the matcher and the remover agree) |

## 12. Evidence and open points

### 12.1 Measured on 14 Nov 2026 (PyMuPDF 2.1 on MuPDF 1.28.6, pdfminer.six, Python 3.12)

| # | Observation | Consequence in this spec |
| --- | --- | --- |
| E1 | The first engine's ordinary page text call returns white, invisible, covered and tiny text, but not text placed outside the page, with or without its clip flag. Its text trace and pdfminer.six both return the off-page text. | V1 uses the text trace (REQ-032, REQ-046) |
| E2 | The first engine's search call does not find off-page text. Redacting by the box taken from the text trace removes it. | Removal locates glyphs from the trace, not from search (REQ-032) |
| E3 | Text inserted by the engine is stored as a hexadecimal string. A byte search of the raw file and of the decompressed streams does not find it. | V4 decodes string objects (REQ-048) |
| E4 | After an incremental save that redacts a term, both engines return clean text for the file, and a byte search finds nothing. Cutting the file at its first end-of-file marker and opening that part returns the term and the old author field. | Earlier revisions are reconstructed and examined (REQ-061); output is a single revision (REQ-039) |
| E5 | The engine reports the revision count (2 after an incremental save, 1 after a full save with garbage collection). A full save with garbage collection leaves one end-of-file marker and no old metadata. | V5 (REQ-039, REQ-060) |
| E6 | Fragments with a wide gap extract as text with a space inside the word, in both engines, and search does not find the unbroken word. | Loose matching (REQ-015) |
| E7 | Free-text annotation and form field text appear in the first engine's page text but not in pdfminer.six. Pop-up contents, outline titles and embedded file contents appear in neither. All are reachable through the document structure. | S2 to S7 are enumerated explicitly (V3) |
| E8 | The trace gives each span a render type (3 for invisible), colour, opacity and drawing sequence number; drawings carry fill colour and sequence number. | The leak classes of section 7.2 are computable |
| E9 | The check digit procedure of section 5.4 accepts three published test values. The two example IBANs pass the modulo 97 check and a one-digit change fails. | REQ-020, REQ-022 |

### 12.2 Third engine: pypdf, measured on 19 Nov 2026

Versions: pypdf 7.1.1, PyMuPDF 2.1 on MuPDF 1.28.6, pdfminer.six 20260107, Python 3.11.15. Synthetic one-page files generated by PyMuPDF.

The owner decided on 15 Nov 2026 to use pypdf in place of the `pdftotext` system binary that `BUILD.md` names. Reasons recorded here:

- pypdf is pure Python. It installs with `uv sync` on every platform, so the third check runs on a developer machine as well as in continuous integration. `pdftotext` was not installed on the build machine, so REQ-030's third check had never run (the former N6).
- It removes the `apt-get install poppler-utils` step from the CI workflow and one unpinned system package from the supply chain.
- Its parser is separate from PyMuPDF (MuPDF, C) and from pdfminer.six, so it is an independent third reading of the same bytes.

| # | Observation | Consequence |
| --- | --- | --- |
| E10 | pypdf returned the canary for plain text, white text, text covered by a black rectangle, text in invisible render mode (3) and text placed outside the page. Text written by PyMuPDF is stored as a hexadecimal string (E3); pypdf decoded it. | pypdf is a usable third reader for the removal matrix (REQ-030). |
| E11 | Fragments `HO`, `TEL-SE`, `CRET` with a gap came back from pypdf and from pdfminer.six as text with a space inside the word. The unbroken word was not returned by either. | The third check uses the same loose matcher as V1 and V2 (REQ-015). |
| E12 | For a file saved as an incremental update after a redaction, pypdf returned clean text for the current revision. Cut at the first end-of-file marker, the first revision returned the term. pdfminer.six and PyMuPDF behaved the same. | Consistent with E4. pypdf is not a substitute for V5. |

Not checked with pypdf: subset fonts and private encodings, rotated and multi-column reading order, annotations, form fields, nested form objects, tagged files, speed on a 100-page file. A failure found when the fixtures exist becomes a deviation or a spec change.

### 12.3 NOT VERIFIED and settled points

| # | Point | Status |
| --- | --- | --- |
| N1 | The National Insurance prefix rules in REQ-024 were from memory. | Settled 19 Nov 2026. The HMRC National Insurance manual (NIM39110) states the same letter and prefix rules and suffix A to D. RA-1. |
| N2 | The tax number digit-frequency rule (REQ-023) was from memory. | Settled 19 Nov 2026, with a correction: the issuer also bars three equal digits at consecutive positions. Filter stays off in 1.0. RA-2. |
| N3 | The IBAN country length table is not drafted here. | Open. Taken from the registry and its release recorded in the session that implements the `iban` pattern (1.4; the 1.3 session text lists no such step). |
| N4 | No synthetic tax or insurance number can be guaranteed unissued. | Settled as far as it can be. Fixture values are issuer-published examples (section 10, RA-3). Not proved unissued. |
| N5 | Behaviour of the engines on a nested form object, a tagged file and layer names (X05, X07, X08) was not probed. | Open. The fixture session probes it; a failure becomes a deviation or a spec change. |
| N6 | `pdftotext` was not available locally, so the third cross-check in REQ-030 was untested. | Closed. `pdftotext` is replaced by pypdf (section 12.2). |
