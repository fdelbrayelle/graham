from __future__ import annotations

import typer

from graham_agent.tui import run_tui

cli = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="graham: KISS fullscreen TUI to scan stocks.",
)


@cli.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Launch the graham TUI."""
    if ctx.invoked_subcommand is None:
        run_tui()


def run() -> None:
    cli()


if __name__ == "__main__":
    run()
