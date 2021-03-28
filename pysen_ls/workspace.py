import logging
import pathlib
import threading
from typing import Dict, Optional

from pygls.lsp.types import MessageType
from pygls.server import LanguageServer
from pysen.exceptions import PysenError

from .runtime import FileRuntime, WorkspaceRuntime

_logger = logging.getLogger(__name__)


class Workspace:
    def __init__(self, server: LanguageServer) -> None:
        self._lock = threading.Lock()
        self._server = server
        self._file_runtimes: Dict[pathlib.Path, FileRuntime] = {}
        self._workspace_runtime: Optional[WorkspaceRuntime] = None

    def _should_create_runtime(self, path: pathlib.Path) -> bool:
        # NOTE: Files with neither extension .py nor .py will
        # be handled only if the user call trigger commands
        return path.suffix in [".py", ".pyc"]

    def _lookup_file_runtime(self, target_file: pathlib.Path) -> Optional[FileRuntime]:
        return self._file_runtimes.get(target_file, None)

    def get_workspace_runtime(
        self,
        base_uri: str,
        base_path: pathlib.Path,
    ) -> Optional[WorkspaceRuntime]:
        with self._lock:
            runtime = self._workspace_runtime
            if runtime is None or runtime.base_uri != base_uri:
                try:
                    _logger.info(f"starting runtime for '{base_path}'")
                    runtime = WorkspaceRuntime(base_uri, base_path)
                    self._workspace_runtime = runtime
                    self._server.show_message_log(
                        f"pysen runtime activated: {base_path}", MessageType.Info
                    )
                except FileNotFoundError:
                    self._server.show_message(
                        f"pysen project not found: {base_path}",
                        MessageType.Error,
                    )
                    return None
                except PysenError:
                    message = (
                        f"an error occurred while opening runtime for path: {base_path}",
                    )
                    self._server.show_message(message, MessageType.Error)
                    _logger.exception(message)
                    return None

        return runtime

    def create_file_runtime(
        self, uri: str, force: bool = False
    ) -> Optional[FileRuntime]:
        with self._lock:
            document = self._server.workspace.get_document(uri)
            path = pathlib.Path(document.path)
            runtime = self._lookup_file_runtime(path)
            if runtime is None and self._should_create_runtime(path):
                try:
                    _logger.info(f"starting runtime for '{path}'")
                    runtime = FileRuntime(uri, path)
                    self._file_runtimes[path] = runtime
                    self._server.show_message_log(
                        f"pysen runtime activated: {path}", MessageType.Info
                    )
                except FileNotFoundError:
                    if force:
                        self._server.show_message(
                            f"pysen project not found: {path}",
                            MessageType.Error,
                        )
                    return None
                except PysenError:
                    message = (
                        f"an error occurred while opening runtime for path: {path}",
                    )
                    self._server.show_message(message, MessageType.Error)
                    _logger.exception(message)
                    return None

        return runtime

    def get_file_runtime(self, uri: str) -> Optional[FileRuntime]:
        with self._lock:
            document = self._server.workspace.get_document(uri)
            path = pathlib.Path(document.path)
            runtime = self._lookup_file_runtime(path)

            return runtime
