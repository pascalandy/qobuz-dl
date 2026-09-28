from .qopy import Client as Client


def main():
    """Run the qobuz-dl command line and return its exit code.

    The CLI is imported only when called, so ``import qobuz_dl`` configures
    nothing and ``python -m qobuz_dl.cli`` runs without a runpy warning.
    """
    from .cli import main as cli_main

    return cli_main()


__all__ = ["Client", "main"]
