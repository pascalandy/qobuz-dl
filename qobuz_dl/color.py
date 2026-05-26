import logging

DF = "\033[22m"
BG = "\033[1m"
RESET = "\033[0m"
OFF = "\033[2m"
RED = "\033[31m"
BLUE = "\033[34m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"

_ANSI_MARKER = "\033["
_FACTORY_INSTALLED_ATTR = "_qobuz_dl_color_reset_factory"


def _install_logging_autoreset() -> None:
    """Append RESET to colored log messages.

    This preserves the old colorama autoreset behavior for the project's logging
    output without keeping colorama as a runtime dependency.
    """
    current_factory = logging.getLogRecordFactory()
    if getattr(current_factory, _FACTORY_INSTALLED_ATTR, False):
        return

    def record_factory(*args, **kwargs):
        record = current_factory(*args, **kwargs)
        if (
            isinstance(record.msg, str)
            and _ANSI_MARKER in record.msg
            and not record.msg.endswith(RESET)
        ):
            record.msg = f"{record.msg}{RESET}"
        return record

    setattr(record_factory, _FACTORY_INSTALLED_ATTR, True)
    logging.setLogRecordFactory(record_factory)


_install_logging_autoreset()
