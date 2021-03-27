import abc
import dataclasses
import logging
import os
import pathlib
import threading
from itertools import chain
from typing import Dict, Iterable, List, Optional, Tuple

import pysen
import tomlkit
from pygls.lsp.types import CodeAction, Diagnostic, Range, TextDocumentEdit
from pysen import load_manifest
from pysen.pyproject_model import has_tool_section

from .diagnostic import create_code_action, create_diagnostic, has_overlap
from .types import DocumentVersionType

_logger = logging.getLogger(__name__)


def _get_uri(base_uri: str, base_path: pathlib.Path, path: pathlib.Path) -> str:
    relpath = ""
    if not path.is_absolute():
        relpath = str(path)
    else:
        relpath = os.path.relpath(path, base_path)

    return os.path.join(base_uri, relpath)


def _find_pyproject(find_base: pathlib.Path) -> pathlib.Path:
    current = find_base

    while True:
        path = current / "pyproject.toml"
        if path.exists() and path.is_file():
            pyproject = tomlkit.loads(path.read_text())
            if has_tool_section("jiro", pyproject) or has_tool_section(
                "pysen", pyproject
            ):
                return path

        # reached root
        if current.parent == current:
            raise FileNotFoundError(find_base)

        current = current.parent


def reset_cache() -> None:
    import pysen.git_utils

    pysen.git_utils.list_indexed_files.cache_clear()


@dataclasses.dataclass
class DiagnosticWithUri:
    uri: str
    diagnostic: Diagnostic


class Runtime(abc.ABC):
    def __init__(
        self, base_uri: str, target_path: pathlib.Path, find_base: pathlib.Path
    ) -> None:
        self._lock = threading.Lock()

        self._base_uri = base_uri
        self._target_path = target_path

        self._project_path = _find_pyproject(find_base)
        # get mtime to detect whether the project is out-dated
        self._base_dir = self._project_path.parent
        self._manifest = load_manifest(self._project_path)
        self._runner = pysen.Runner(self._manifest)
        self._args = self._runner.parse_manifest_arguments([])

        self._diagnostics: Dict[str, List[DiagnosticWithUri]] = {}
        self._code_actions: Dict[str, List[CodeAction]] = {}

    @property
    def base_uri(self) -> str:
        return self._base_uri

    @abc.abstractmethod
    def get_uri(self, path: pathlib.Path) -> str:
        ...

    @abc.abstractmethod
    def get_version(self, uri: str) -> Optional[DocumentVersionType]:
        ...

    def _run_pysen(
        self, command: str, target_files: Optional[List[pathlib.Path]]
    ) -> pysen.ReporterFactory:
        reporter_factory = pysen.ReporterFactory(
            pretty=False, process_output=False, loglevel=logging.CRITICAL
        )
        options = pysen.RunOptions(require_diagnostics=True)

        self._runner.run(
            command,
            self._base_dir,
            self._args,
            reporter_factory,
            options,
            files=target_files,
        )

        return reporter_factory

    def _convert_reports(
        self,
        command: str,
        reporter_factory: pysen.ReporterFactory,
    ) -> Tuple[List[DiagnosticWithUri], List[CodeAction]]:
        diagnostics: List[DiagnosticWithUri] = []
        code_actions: List[CodeAction] = []

        for reporter in reporter_factory.reporters:
            for diagnostic in reporter.diagnostics:
                uri = self.get_uri(diagnostic.file_path)
                lsp_diagnostic = create_diagnostic(
                    diagnostic,
                    f"Incompatible with {reporter.name}",
                    None,
                    f"{reporter.name}(pysen)",
                )

                diagnostics.append(DiagnosticWithUri(uri, lsp_diagnostic))
                action = create_code_action(
                    f"Apply suggestion from {reporter.name} (pysen)",
                    uri,
                    self.get_version(uri),
                    diagnostic,
                    [
                        lsp_diagnostic,
                    ],
                )
                if action is not None:
                    code_actions.append(action)

        return diagnostics, code_actions

    def _update_diagnostics(
        self,
        command: str,
        target_files: Optional[List[pathlib.Path]],
    ) -> None:
        reporter_factory = self._run_pysen(command, target_files)
        diagnostics, code_actions = self._convert_reports(command, reporter_factory)
        with self._lock:
            self._diagnostics[command] = diagnostics
            self._code_actions[command] = code_actions

    def iter_diagnostics(self) -> Iterable[DiagnosticWithUri]:
        return chain.from_iterable(self._diagnostics.values())

    def iter_code_actions(self) -> Iterable[CodeAction]:
        return chain.from_iterable(self._code_actions.values())


class WorkspaceRuntime(Runtime):
    def __init__(self, base_uri: str, target_path: pathlib.Path) -> None:
        path = target_path.resolve()
        super().__init__(base_uri, path, path)

    def get_uri(self, path: pathlib.Path) -> str:
        return _get_uri(self._base_uri, self._target_path, path)

    def get_version(self, uri: str) -> Optional[DocumentVersionType]:
        return None

    def update_diagnostics(
        self,
        command: str,
    ) -> None:
        self._update_diagnostics(command, None)


class FileRuntime(Runtime):
    def __init__(self, base_uri: str, target_path: pathlib.Path) -> None:
        path = target_path.resolve()
        self._version: Optional[DocumentVersionType] = None
        super().__init__(base_uri, path, path.parent)

    @property
    def uri(self) -> str:
        return self._base_uri

    def get_uri(self, path: pathlib.Path) -> str:
        if self._target_path != path:
            _logger.warning("got different path")

        return self._base_uri

    def get_version(self, uri: str) -> Optional[DocumentVersionType]:
        return self._version

    def update_diagnostics_range(self, updated_range: Range, update_text: str) -> None:
        """Incremental diagnostic update"""
        # NOTE: splitlines() ignores the last line if empty while split() doesn't
        # e.g. '' -> [], 'a\n' -> ['a']
        # Here we need the split() behavior while splitlines() can split lines with
        # unversal newlines.
        # Hence we add character 'a' to the given text, then remove it after we call
        # splitlines() so that we can get the last empty line
        to_add = (update_text + "a").splitlines()
        to_add[-1] = to_add[-1][:-1]
        num_remove_lines = updated_range.end.line - updated_range.start.line
        num_add_lines = len(to_add) - 1
        num_updated_lines = num_add_lines - num_remove_lines
        num_add_characters_last_line = len(to_add[-1])

        def update_logic(target_range: Range) -> bool:
            if target_range.end < updated_range.start:
                return True

            if target_range.start.line >= updated_range.end.line:
                # update position
                target_range.start.line += num_updated_lines
                target_range.end.line += num_updated_lines
                if target_range.start.line == updated_range.end.line:
                    if target_range.start.character <= updated_range.end.character:
                        return False

                    target_range.start.character += num_add_characters_last_line
                return True

            return False

        for command, code_actions in self._code_actions.items():
            for code_action in code_actions:
                if code_action.edit is None:
                    continue

                keep = True
                for change in code_action.edit.document_changes:
                    if not isinstance(change, TextDocumentEdit):
                        continue

                    for edit in change.edits:
                        keep = keep and update_logic(edit.range)

                if code_action.diagnostics is not None:
                    for diagnostic in code_action.diagnostics:
                        keep = keep and update_logic(diagnostic.range)

                if not keep:
                    code_action.edit = None

            self._code_actions[command] = [
                c for c in code_actions if c.edit is not None
            ]

    def update_diagnostics(
        self,
        command: str,
        document_version: Optional[DocumentVersionType],
    ) -> None:
        self._version = document_version
        self._update_diagnostics(command, [self._target_path])

    def get_diagnostics(self) -> List[Diagnostic]:
        diagnostics = self.iter_diagnostics()
        return [d.diagnostic for d in diagnostics]

    def query_code_actions(
        self,
        target_range: Range,
    ) -> List[CodeAction]:
        code_actions = self.iter_code_actions()
        if target_range is None:
            return list(code_actions)

        filtered: List[CodeAction] = []
        for code_action in code_actions:
            if code_action.diagnostics is None or len(code_action.diagnostics) == 0:
                continue

            if any(has_overlap(d.range, target_range) for d in code_action.diagnostics):
                filtered.append(code_action)

        return filtered
