import logging
from typing import List, cast

from pygls.lsp.types import MessageType
from pygls.server import LanguageServer

from pysen_ls.logger import LanguageServerLogHandler, _convert_loglevel


class FakeServer:
    def __init__(self) -> None:
        self.received: List[str] = []

    def show_message_log(self, message: str, severity: MessageType) -> None:
        self.received.append(f"{severity.name}: {message}")


def test__convert_loglevel() -> None:
    assert _convert_loglevel(logging.DEBUG) == MessageType.Log
    assert _convert_loglevel(logging.INFO) == MessageType.Info
    assert _convert_loglevel(logging.WARN) == MessageType.Warning
    assert _convert_loglevel(logging.WARNING) == MessageType.Warning
    assert _convert_loglevel(logging.ERROR) == MessageType.Error
    assert _convert_loglevel(logging.CRITICAL) == MessageType.Error

    assert _convert_loglevel(logging.DEBUG - 1) == MessageType.Info
    assert _convert_loglevel(logging.CRITICAL + 1) == MessageType.Info
    assert _convert_loglevel(logging.NOTSET) == MessageType.Info


def test_emit() -> None:
    logger = logging.getLogger("temp")
    logger.setLevel(logging.DEBUG)

    handler = LanguageServerLogHandler()
    logger.addHandler(handler)

    logger.error("japan")

    server = FakeServer()
    handler.server = cast(LanguageServer, server)

    logger.debug("tokyo")
    logger.info("kyoto")
    logger.warning("osaka")
    logger.error("sendai")
    logger.critical("hokkaido")

    assert server.received == [
        "Log: tokyo",
        "Info: kyoto",
        "Warning: osaka",
        "Error: sendai",
        "Error: hokkaido",
    ]

    server.received.clear()
    handler.server = None

    logger.error("nippon")
    assert server.received == []
