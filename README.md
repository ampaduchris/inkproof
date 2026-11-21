# inkproof

A black box drawn over text in a PDF (Portable Document Format) file hides the words and leaves them in the file. Select the page, copy, paste, and they come back. inkproof deletes the words from the text layer. Then it re-reads the file it is about to write with two independent text extraction engines and three further checks, and it writes nothing if one match survives.

```console
$ inkproof apply examples/statement.pdf \
    --terms examples/terms.txt \
    --patterns iban,email -o out.pdf
inkproof: clean: 4 match(es) removed and not found again by any
check. The check covers the text layer only; text in images is
not examined.
```

The proof covers the text layer. It does not read images: a scanned page is not examined. The full list is under [Limits](#limits).

Claude Code wrote this code under my direction. On every pull request I approved the change in a comment naming what I checked, then merged it. One example: [pull request 6](https://github.com/ampaduchris/inkproof/pull/6), where the failing tests came first.

## Demo

[A 17-second terminal recording](docs/demo.cast) (asciicast format; play it with `asciinema play docs/demo.cast`). It runs `inkproof audit` on `examples/statement.pdf`, which reports 4 leaks and exits 1. It runs `inkproof apply`, which removes them and exits 0. It runs `inkproof audit` on the output, which finds no leak and exits 0.

`scripts/make_demo.py` makes the recording. It runs the real commands on the example files and writes their real output.

## Install

```bash
pipx install inkproof
```

inkproof needs Python 3.11 or newer. It is tested on Python 3.11, 3.12 and 3.13. It is tested on Linux in continuous integration (CI). It should run on macOS and Windows; that is not tested. It makes no network connection.

## Usage

### Remove text and prove it is gone

```bash
inkproof apply in.pdf --terms terms.txt --patterns iban,de-tax-id,uk-ni,email -o out.pdf
```

`terms.txt` holds one term per line:

```text
# lines that start with # are ignored
Erika Mustermann
Project Heron
```

Terms match in any letter case, across a line break, and when the PDF stores a word in fragments. A term does not match inside a longer word.

| Pattern | Finds |
| --- | --- |
| `iban` | An International Bank Account Number (IBAN) with a valid check sum and the right length for its country |
| `de-tax-id` | A German tax identification number (Steuer-Identifikationsnummer) with a valid check digit |
| `uk-ni` | A United Kingdom National Insurance number |
| `email` | An email address |

`apply` also removes every annotation, form field, embedded file and script, and empties the metadata. It draws a black rectangle where text was removed. It never changes `in.pdf`. It writes `out.pdf` only after every check has passed, and it writes a report beside it as `out.pdf.report.json`.

### Audit a PDF that someone else redacted

```console
$ inkproof audit examples/statement.pdf \
    --terms examples/terms.txt \
    --patterns iban,email --report audit.json
inkproof: leaks found: 4 in 4 place(s). The check covers the text
layer only; text in images is not examined.
$ echo $?
1
```

`audit` changes nothing. It reports text under a shape or an image, text in the colour of its background, text outside the page, invisible text, and text that survives in an earlier saved version of the file. It also looks in annotations, form fields, metadata, bookmarks and embedded files.

### The report

The report is a JSON (JavaScript Object Notation) file. It says where each match was found: the kind of place, the page, the count, and which term (by line number) or pattern matched. It never holds a matched value, a term, any text from the document, a file name or a path. Files are named by their SHA-256 (Secure Hash Algorithm, 256-bit) digest. You can send the report to someone without sending them what you removed. The schema ships in the package as `report.schema.json`.

### Options and exit codes

| Option | Effect |
| --- | --- |
| `--report PATH` | Write the report to `PATH` |
| `--force` | Allow `apply` to replace an existing output file |
| `--no-mark` | Do not draw the black rectangle |
| `--substring` | Let a term match inside a longer word |
| `--allow-short-terms` | Accept terms of fewer than three letters or digits |

| Exit code | Meaning |
| --- | --- |
| 0 | `apply`: output written and verified. `audit`: no leak found in the text layer |
| 1 | `apply`: a match survived and no output was written. `audit`: at least one leak found |
| 2 | Bad arguments, bad terms file, or an unsafe output path |
| 3 | The file is not a PDF, is damaged, or needs a password |
| 4 | Internal error. No output was written |

## How removal is proved

A redaction tool can fail in two ways. It can leave the text in the file. Or it can remove the text and be wrong about having done so. inkproof treats the second as the harder problem.

1. **Find.** inkproof reads every piece of text the page draws, wherever it sits: off the page, in white, invisible, or under a shape.
2. **Remove.** It deletes the matching glyphs from the page content. It does not cover them.
3. **Write a new file.** A PDF can keep earlier versions of itself after a save. inkproof writes one complete new file with no earlier version inside it.
4. **Re-read the bytes.** It opens the bytes it is about to write as if they were a stranger's file. It never checks the copy in memory that it has just edited.
5. **Ask two engines.** PyMuPDF and pdfminer.six each extract the text with their own parser. inkproof searches each result for every term and pattern. The two share no parsing code, so a mistake in one parser is unlikely to be repeated by the other. The test suite adds a third, pypdf, as a cross-check. It is not part of the installed tool.
6. **Look where engines do not.** It walks the annotations, form fields, metadata, bookmarks, embedded files, scripts, tags and layer names. Then it decodes every stream and every string in the file and searches those too, and it counts the revisions in the file.
7. **Fail closed.** If any check finds a match, inkproof exits with code 1 and writes no output file. The report says where the match is, never what it is. There is no option that skips the checks.

How the tool itself is tested:

- 72 requirements marked MUST in the [specification](docs/spec.md). Each has at least one test. `scripts/trace.py` fails the build otherwise.
- 30 removal cases: four patterns and two terms on each of five page layouts.
- 10 PDFs with a planted failed redaction. `audit` must catch each one, and must report nothing on a correctly redacted control file.
- Mutation testing changes the matcher and the verifier in small ways and checks that a test fails. Score: 82.8 per cent (914 of 1,104 changes caught) on 21 November 2026, recorded in [docs/MUTATION.md](docs/MUTATION.md). The floor in the specification is 80 per cent. Survivors are listed there, and most are not individually read.
- Every test PDF is generated by code in this repository. No real document is in it.

## Limits

What inkproof does not do. The same table is in the specification.

| Limit | Meaning |
| --- | --- |
| LIM-1 Images | Text that exists only as pixels is not examined. There is no optical character recognition. |
| LIM-2 Accents | `Müller` does not match `Muller` or `Mueller`. List each spelling. |
| LIM-3 Page breaks | A match split across two pages is not found. |
| LIM-4 Reading order | Matching follows the order in which each engine returns text. Text that an engine returns in scattered order (some multi-column or rotated layouts) can be missed by that engine. |
| LIM-5 Meaning | The tool finds strings. It does not know that "the claimant" refers to a named person. |
| LIM-6 Custom font encodings in the raw scan | The raw scan (section 6, check V4) decodes strings with standard encodings only. Text in fonts with private encodings is covered by the extraction checks V1 and V2, not by V4. |

The checks V1 to V5 are defined in section 6.1 of the [specification](docs/spec.md). The report lists the pages that hold images, and the pages that hold images and no text, so you know which pages to check by eye.

## Verify it yourself

Set up once:

```bash
git clone https://github.com/ampaduchris/inkproof && cd inkproof && uv sync --locked
```

Then three commands. CI runs the same three on every pull request. `scripts/run_blocks.py` runs them from this file.

```bash run
uv run pytest -q
```

Expected last line: `445 passed`

```bash run
uv run python scripts/trace.py
```

Expected last line: `79 requirements, 0 untested MUST`

```bash run
uv run inkproof apply examples/statement.pdf --terms examples/terms.txt --patterns iban,email -o /tmp/out.pdf --force
```

Expected last line: `inkproof: clean: 4 match(es) removed`

The mutation score is not one of the three because the run takes about 8 minutes. The command is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Status

Status: released, dependencies reviewed monthly.

## How this was built

Built by directing Claude Code. No hand-written code. Every pull request was opened by the agent and approved and merged by me. Model and effort for every session are recorded in docs/BUILD-LOG.md.

The record: [build log](docs/BUILD-LOG.md), [specification](docs/spec.md), [deviations from it](docs/DEVIATIONS.md), [independent review](docs/reviews/).

The code here was generated by Claude Code under my direction. I wrote the requirements and approved each change. The law on copyright in machine-generated code is unsettled. I license whatever rights I hold under the licence in this repository.

## Licence

inkproof is licensed under the GNU Affero General Public Licence, version 3 or later (AGPL-3.0-or-later). The reason is one dependency. inkproof finds and removes text with PyMuPDF, and PyMuPDF is offered under the AGPL. A program built on an AGPL library has to carry a compatible licence, so this one carries the same. PyMuPDF's licence is `AGPL-3.0-only` as one option of a dual licence; [LICENSES/README.md](LICENSES/README.md) has the check.

Running inkproof on your own files places no duty on you. If you change it and pass the changed version on, or let others use it over a network, the licence asks you to offer them your source. The second engine, pdfminer.six, carries a permissive licence. pdfminer.six is MIT. The full text is in [LICENSE](LICENSE). This paragraph describes the licence. It is not legal advice.

## Security and contributing

A leak that inkproof misses is a security bug. Report it privately: see [SECURITY.md](SECURITY.md). Never attach a real document to an issue. A generated PDF that shows the problem is enough. For everything else, see [CONTRIBUTING.md](CONTRIBUTING.md).
