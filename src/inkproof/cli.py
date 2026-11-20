"""Command line entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from inkproof import __version__
from inkproof.apply import Request, run_apply
from inkproof.audit import Request as AuditRequest, run_audit
from inkproof.terms import InputError

app = typer.Typer(help="Redact PDFs and prove the text layer is gone.", no_args_is_help=True,
                  rich_markup_mode=None, pretty_exceptions_enable=False, add_completion=False)

EXIT_CODES = ("Exit codes: 0 clean (output written and verified); 1 leaks found (a survivor was found, "
              "no output written); 2 usage or input error; 3 document cannot be processed (not a PDF, "
              "damaged, or needs a password); 4 internal error (no output written).")


EXIT_CODES_AUDIT = ("Exit codes: 0 clean (no leak found in the text layer); 1 leaks found (at least one leak found); "
                    "2 usage or input error; 3 document cannot be processed (not a PDF, damaged, or needs a password); "
                    "4 internal error.")


def _version(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version, is_eager=True, help="Print the version and exit."
    ),
) -> None:
    """Redact PDFs and prove the text layer is gone."""


@app.command("apply", epilog=EXIT_CODES)
def apply_cmd(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="The PDF to redact."),
    terms: Optional[Path] = typer.Option(None, "--terms", help="UTF-8 file, one term per line."),
    patterns: Optional[str] = typer.Option(None, "--patterns", help="Comma-separated: iban, de-tax-id, uk-ni, email."),
    output: Path = typer.Option(..., "-o", "--output", help="Where to write the redacted PDF."),
    report: Optional[Path] = typer.Option(None, "--report", help="Where to write the JSON report "
                                          "(default: the output path with .report.json appended)."),
    force: bool = typer.Option(False, "--force", help="Replace an existing output file."),
    substring: bool = typer.Option(False, "--substring", help="Let a match touch a letter or digit on either side."),
    allow_short_terms: bool = typer.Option(False, "--allow-short-terms",
                                           help="Accept terms of fewer than three letters or digits."),
    no_mark: bool = typer.Option(False, "--no-mark", help="Do not draw a black rectangle over each removal."),
    debug: bool = typer.Option(False, "--debug", help="On an internal error, print a traceback with values masked."),
) -> None:
    """Remove terms and patterns from the text layer, then prove they are gone. Never prints a matched value."""
    names = [p.strip() for p in patterns.split(",") if p.strip()] if patterns else []
    req = Request(input=input, output=output, terms=terms, patterns=names, report=report, force=force,
                  substring=substring, allow_short_terms=allow_short_terms, no_mark=no_mark, debug=debug)
    try:
        code = run_apply(req)
    except InputError as exc:
        typer.echo(f"inkproof: {exc}", err=True)
        code = 2
    except typer.Exit:
        raise
    except Exception as exc:
        from inkproof.apply import masked_traceback
        typer.echo("inkproof: internal error (E4). No output was written. Run again with --debug for a masked traceback.",
                   err=True)
        if debug:
            typer.echo(masked_traceback(exc), err=True)
        code = 4
    raise typer.Exit(code)


@app.command("audit", epilog=EXIT_CODES_AUDIT)
def audit_cmd(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True, help="The PDF to examine. It is never changed."),
    terms: Optional[Path] = typer.Option(None, "--terms", help="UTF-8 file, one term per line."),
    patterns: Optional[str] = typer.Option(None, "--patterns", help="Comma-separated: iban, de-tax-id, uk-ni, email."),
    report: Optional[Path] = typer.Option(None, "--report", help="Where to write the JSON report (default: standard output)."),
    substring: bool = typer.Option(False, "--substring", help="Let a match touch a letter or digit on either side."),
    allow_short_terms: bool = typer.Option(False, "--allow-short-terms",
                                           help="Accept terms of fewer than three letters or digits."),
    debug: bool = typer.Option(False, "--debug", help="On an internal error, print a traceback with values masked."),
) -> None:
    """Report where terms and patterns can still be found in a PDF. Never changes the file and never prints a matched value."""
    names = [p.strip() for p in patterns.split(",") if p.strip()] if patterns else []
    req = AuditRequest(input=input, terms=terms, patterns=names, report=report, substring=substring,
                       allow_short_terms=allow_short_terms, debug=debug)
    try:
        code = run_audit(req)
    except InputError as exc:
        typer.echo(f"inkproof: {exc}", err=True)
        code = 2
    except typer.Exit:
        raise
    except Exception as exc:
        from inkproof.apply import masked_traceback
        typer.echo("inkproof: internal error (E4). Run again with --debug for a masked traceback.", err=True)
        if debug:
            typer.echo(masked_traceback(exc), err=True)
        code = 4
    raise typer.Exit(code)


if __name__ == "__main__":
    app()
