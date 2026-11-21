# Licences

inkproof is licensed under AGPL-3.0-or-later (GNU Affero General Public Licence, version 3 or any later version). The full text is in `../LICENSE`.

## Why AGPL

PyMuPDF is a runtime dependency. Its upstream source declares its licence as `AGPL-3.0-only OR LicenseRef-Artifex-Commercial-License` (a dual licence: GNU Affero General Public Licence version 3 only, or a commercial licence from Artifex). inkproof uses PyMuPDF under the AGPL-3.0 option, so inkproof is also AGPL.

Checked on 19 November 2026 against PyMuPDF 2.1: the PyPI metadata reads "Dual Licensed - GNU AFFERO GPL 3.0 or Artifex Commercial License", and the commented `license_expression` in the upstream `setup.py` reads `AGPL-3.0-only OR LicenseRef-Artifex-Commercial-License`.

## Dependency licences

| Dependency | Licence identifier | Used for |
| --- | --- | --- |
| PyMuPDF | AGPL-3.0-only (option of a dual licence) | PDF parsing, editing, first text engine |

| pdfminer.six | MIT | Second text engine |
| Typer | MIT | Command line |

pdfminer.six and Typer identifiers read from the installed package metadata on 21 November 2026. Further rows are added by the sessions that add dependencies.
