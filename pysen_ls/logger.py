import logging
from typing import Optional

from pygls.lsp.types import MessageType
from pygls.server import LanguageServer

_LogLevelMap = {
    logging.DEBUG: MessageType.Log,
    logging.INFO: MessageType.Info,
    logging.WARNING: MessageType.Warning,
    logging.ERROR: MessageType.Error,
    logging.CRITICAL: MessageType.Error,
}


def _convert_loglevel(loglevel: int) -> MessageType:
    return _LogLevelMap.get(loglevel, MessageType.Info)


class LanguageServerLogHandler(logging.Handler):
    @property
    def server(self) -> Optional[LanguageServer]:
        return self._server

    @server.setter
    def server(self, server: LanguageServer) -> None:
        self._server = server

    def emit(self, record: logging.LogRecord) -> None:
        server = self.server
        if server is None:
            return

        server.show_message_log(str(record.msg), _convert_loglevel(record.levelno))
