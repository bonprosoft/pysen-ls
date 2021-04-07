import collections
import enum
import logging
import pathlib
from typing import Any, Callable, DefaultDict, List, Optional, Sequence, Union

from pydantic import ValidationError
from pygls import lsp
from pygls.server import LanguageServer

from .config import LanguageServerConfiguration
from .diagnostic import Diagnostic
from .runtime import FileRuntime, WorkspaceRuntime
from .workspace import Workspace

_logger = logging.getLogger(__name__)

CONFIGURATION_SECTION_NAME = "pysen.server"


class Commands:
    ReloadServerConfiguration = "pysen.reloadServerConfiguration"
    LintDocument = "pysen.callLintDocument"
    FormatDocument = "pysen.callFormatDocument"
    LintWorkspace = "pysen.callLintWorkspace"
    FormatWorkspace = "pysen.callFormatWorkspace"


class ConnectionMethod(enum.Enum):
    IO = "io"
    TCP = "tcp"


def _get_request_params(
    params: Any,
) -> Optional[str]:
    if (
        not isinstance(params, list)
        or len(params) != 1
        or not isinstance(params[0], str)
    ):
        # TODO(igarashi): should return response?
        return None

    uri: str = params[0]
    return uri


class Server:
    def __init__(
        self, method: ConnectionMethod, host: Optional[str], port: Optional[int]
    ) -> None:
        self._method = method
        self._host = host
        self._port = port

        if self._method == ConnectionMethod.TCP:
            if host is None or port is None:
                raise ValueError("host and port is required when method is TCP")

        self._server = LanguageServer()
        self._config = LanguageServerConfiguration.default()
        self._workspace = Workspace(self._server)

        self._register_command(
            Commands.ReloadServerConfiguration,
            self._on_reload_server_config,
        )
        self._register_command(
            Commands.LintDocument,
            self._on_lint_document,
        )
        self._register_command(
            Commands.FormatDocument,
            self._on_format_document,
        )
        self._register_command(
            Commands.LintWorkspace,
            self._on_lint_workspace,
        )
        self._register_command(
            Commands.FormatWorkspace,
            self._on_format_workspace,
        )

        self._register_feature("$/setTrace", None, lambda *args, **kwargs: None)
        self._register_feature(
            lsp.methods.INITIALIZE,
            None,
            self._on_initialize,
        )
        self._register_feature(
            lsp.methods.WORKSPACE_DID_CHANGE_CONFIGURATION,
            None,
            self._on_workspace_did_change_configuration,
        )
        self._register_feature(
            lsp.methods.FORMATTING,
            lsp.types.DocumentFormattingOptions(),
            self._on_formatting,
        )
        self._register_feature(
            lsp.methods.TEXT_DOCUMENT_DID_SAVE,
            None,
            self._on_text_document_did_save,
        )
        self._register_feature(
            lsp.methods.TEXT_DOCUMENT_DID_OPEN,
            None,
            self._on_text_document_did_open,
        )
        self._register_feature(
            lsp.methods.TEXT_DOCUMENT_DID_CLOSE,
            None,
            self._on_text_document_did_close,
        )
        self._register_feature(
            lsp.methods.TEXT_DOCUMENT_DID_CHANGE,
            None,
            self._on_text_document_did_change,
        )
        self._register_feature(
            lsp.methods.CODE_ACTION,
            lsp.types.CodeActionOptions(
                code_action_kinds=[lsp.types.CodeActionKind.QuickFix]
            ),
            self._provide_code_action,
        )

    def _register_command(self, command_name: str, handler: Callable[..., Any]) -> None:
        @self._server.command(command_name)
        def cb(*args: Any, **kwargs: Any) -> Any:
            return handler(*args, **kwargs)

    def _register_feature(
        self, feature_name: str, option: Any, handler: Callable[..., Any]
    ) -> None:
        # NOTE: pygls calls setattr in `feature` decorator to add their own field.
        # Since a method doesn't allow setattr for undefined fields,
        # we cannot use it for the decorator.
        # Thus We define temporary function instead.
        @self._server.feature(feature_name, option)
        def cb(*args: Any, **kwargs: Any) -> Any:
            return handler(*args, **kwargs)

    def _on_config_received(self, data: Any) -> None:
        try:
            self._config = LanguageServerConfiguration.parse_obj(data[0])
        except ValidationError as e:
            self._server.show_message_log(f"Error occurred: {e}")
        except Exception as e:
            self._server.show_message_log(f"Error occurred: {e}")

    def _request_config(self) -> None:
        self._server.get_configuration(
            lsp.types.ConfigurationParams(
                items=[
                    lsp.types.ConfigurationItem(
                        scope_uri="", section=CONFIGURATION_SECTION_NAME
                    )
                ]
            ),
            self._on_config_received,
        )

    def _on_initialize(self, params: lsp.types.InitializeParams) -> None:
        # NOTE: The return value from this method will be ignored.
        # pygls.LanguageServerProtocol provides some predefined lsp features.
        # It calls methods starting with `bf_`, then call use defined methods.
        # User defined methods are wrapped by the decorator in pygls,
        # and it doesn't use the return values from the methods.
        # See: https://github.com/openlawlibrary/pygls/blob/b5dcfa36ee3fab2cd0f3bf29248d58f5ad3b6796/pygls/protocol.py#L62-L75  # NOQA
        options = params.initialization_options
        if options is not None:
            config = options.get("config", None)
            if config is not None:
                self._on_config_received([config])

    def _on_workspace_did_change_configuration(
        self, params: lsp.types.DidChangeConfigurationParams
    ) -> None:
        settings = params.settings
        if settings is not None and isinstance(settings, dict):
            config = settings.get("config", None)
            if config is not None:
                self._on_config_received([config])

    def _publish_file_diagnostics(
        self,
        targets: Sequence[str],
        runtime: FileRuntime,
    ) -> None:
        for target in targets:
            runtime.update_diagnostics(target, None)

        diagnostics = runtime.get_diagnostics()
        self._server.publish_diagnostics(
            runtime.uri,
            diagnostics,
        )

    def _publish_workspace_diagnostics(
        self,
        targets: Sequence[str],
        runtime: WorkspaceRuntime,
    ) -> None:
        for target in targets:
            runtime.update_diagnostics(target)

        to_publish: DefaultDict[str, List[Diagnostic]] = collections.defaultdict(list)
        data = list(runtime.iter_diagnostics())

        for d in data:
            to_publish[d.uri].append(d.diagnostic)

        for uri, diagnostics in to_publish.items():
            self._server.publish_diagnostics(
                uri,
                diagnostics,
            )

    def _on_reload_server_config(self, *args: Any) -> None:
        self._request_config()

    def _handle_document_command(self, request: Any, targets: Sequence[str]) -> None:
        uri = _get_request_params(request)
        if uri is None:
            return

        runtime = self._workspace.create_file_runtime(uri, force=True)
        if runtime is None:
            return

        self._publish_file_diagnostics(targets, runtime)

    def _on_formatting(self, params: lsp.types.DocumentFormattingParams) -> None:
        # TODO: Consider adding unregistration config of this capability
        # for someone who wants opt-out this feature.
        uri = params.text_document.uri
        self._handle_document_command([uri], self._config.format_targets)

    def _on_lint_document(self, args: Any) -> None:
        self._handle_document_command(args, self._config.lint_targets)

    def _on_format_document(self, args: Any) -> None:
        self._handle_document_command(args, self._config.format_targets)

    def _handle_workspace_command(self, request: Any, targets: Sequence[str]) -> None:
        root_uri = self._server.workspace.root_uri
        root_path = self._server.workspace.root_path
        if root_uri is None or root_path is None:
            self._server.show_message(
                "workspace is not opened", lsp.types.MessageType.Error
            )
            return

        runtime = self._workspace.get_workspace_runtime(
            root_uri, pathlib.Path(root_path)
        )
        if runtime is None:
            return

        self._publish_workspace_diagnostics(targets, runtime)

    def _on_lint_workspace(self, args: Any) -> None:
        self._handle_workspace_command(args, self._config.lint_targets)

    def _on_format_workspace(self, args: Any) -> None:
        self._handle_workspace_command(args, self._config.format_targets)

    def _on_text_document_did_open(
        self, params: lsp.types.DidOpenTextDocumentParams
    ) -> None:
        uri = params.text_document.uri
        runtime = self._workspace.create_file_runtime(uri)
        if runtime is None:
            return

        self._publish_file_diagnostics(self._config.lint_targets, runtime)

    def _on_text_document_did_close(
        self, params: lsp.types.DidCloseTextDocumentParams
    ) -> None:
        pass

    def _on_text_document_did_save(
        self, params: lsp.types.DidSaveTextDocumentParams
    ) -> None:
        if not self._config.enable_lint_on_save:
            return None

        runtime = self._workspace.get_file_runtime(params.text_document.uri)
        if runtime is None:
            return

        self._publish_file_diagnostics(self._config.lint_targets, runtime)

    def _on_text_document_did_change(
        self,
        params: lsp.types.DidChangeTextDocumentParams,
    ) -> None:
        runtime = self._workspace.get_file_runtime(params.text_document.uri)
        if runtime is None:
            return

        changes = params.content_changes
        for change in changes:
            if not isinstance(change, lsp.types.TextDocumentContentChangeEvent):
                continue
            change_range = change.range

            if change_range is None:
                continue

            runtime.update_diagnostics_range(change_range, change.text)

    def _provide_code_action(
        self, params: lsp.types.CodeActionParams
    ) -> Optional[Sequence[Union[lsp.types.Command, lsp.types.CodeAction]]]:
        if not self._config.enable_code_action:
            return None

        runtime = self._workspace.get_file_runtime(params.text_document.uri)
        if runtime is None:
            return []

        return runtime.query_code_actions(params.range)

    def start(self) -> None:
        _logger.info("starting server")
        if self._method == ConnectionMethod.IO:
            _logger.info("use stdio for the communication")
            self._server.start_io()
        else:
            assert self._method == ConnectionMethod.TCP, self._method
            _logger.info("use tcp for the communication")
            assert self._host is not None
            assert self._port is not None
            self._server.start_tcp(self._host, self._port)
