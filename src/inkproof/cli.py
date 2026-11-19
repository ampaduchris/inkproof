"""Command line entry point. Stub: commands arrive in later sessions."""

import typer

from inkproof import __version__

app = typer.Typer(help="Redact PDFs and prove the text layer is gone.", no_args_is_help=True)


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


if __name__ == "__main__":
    app()
