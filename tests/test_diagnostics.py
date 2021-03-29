import pathlib
from typing import List, Optional, Tuple

import pysen.diagnostic
import pytest
from pygls.lsp.types import (
    CodeActionKind,
    DiagnosticSeverity,
    OptionalVersionedTextDocumentIdentifier,
    Position,
    Range,
    TextDocumentEdit,
    WorkspaceEdit,
)

from pysen_ls.diagnostic import (
    _has_deletion,
    create_code_action,
    create_diagnostic,
    create_text_edit,
    get_diagnostic_range,
    has_overlap,
)

BASE_DIR = pathlib.Path(__file__).resolve().parent


def get_range(start: Tuple[int, int], end: Tuple[int, int]) -> Range:
    return Range(
        start=Position(line=start[0], character=start[1]),
        end=Position(line=end[0], character=end[1]),
    )


def get_pysen_diagnostic(
    start_line: Optional[int] = None,
    start_column: Optional[int] = None,
    end_line: Optional[int] = None,
    message: Optional[str] = None,
    diff: Optional[str] = None,
) -> pysen.diagnostic.Diagnostic:
    if message is None and diff is None:
        message = "test"
    return pysen.diagnostic.Diagnostic(
        file_path=BASE_DIR,
        start_line=start_line,
        end_line=end_line,
        start_column=start_column,
        message=message,
        diff=diff,
    )


def test__has_deletion() -> None:
    assert not _has_deletion("hello")
    assert not _has_deletion("+hello")
    assert _has_deletion("-hello")
    assert not _has_deletion("+ hello\n+world\n jiro-ls!")
    assert _has_deletion("+ hello\n-world\n jiro-ls!")


def test_get_diagnostic_range() -> None:
    diagnostic = get_pysen_diagnostic()
    assert get_diagnostic_range(diagnostic) == get_range((0, 0), (0, 0))

    # diagnostics which tools like black, isort provides
    diagnostic = get_pysen_diagnostic(start_line=10, start_column=1, end_line=20)
    assert get_diagnostic_range(diagnostic) == get_range((9, 0), (19, 0))

    diagnostic = get_pysen_diagnostic(
        start_line=10, start_column=1, end_line=10, diff="-\n-\n"
    )
    assert get_diagnostic_range(diagnostic) == get_range((9, 0), (10, 0))

    # diagnostics which tools like mypy, flake8 provides
    diagnostic = get_pysen_diagnostic(start_line=10, start_column=20, end_line=10)
    assert get_diagnostic_range(diagnostic) == get_range((9, 19), (9, 19))

    diagnostic = get_pysen_diagnostic(start_line=10, start_column=20, end_line=11)
    assert get_diagnostic_range(diagnostic) == get_range((9, 19), (10, 0))


def test_has_overlap() -> None:
    # r1: [0, 0] -> [9, 30]
    # r2: [10, 10] -> [20, 0]
    # r3: [15, 0] -> [16, 0]
    # r4: [15, 0] -> [15, 0]
    r1 = get_range((0, 0), (9, 30))
    r2 = get_range((10, 10), (20, 0))
    r3 = get_range((15, 0), (16, 0))
    r4 = get_range((15, 0), (15, 0))
    ranges = [r1, r2, r3, r4]

    for r in ranges:
        assert has_overlap(r, r)

    assert not has_overlap(r1, r2) and not has_overlap(r2, r1)
    assert has_overlap(r2, r3) and has_overlap(r3, r2)

    def get_overlapped_ranges(selection: Range) -> List[Range]:
        return [r for r in ranges if has_overlap(selection, r)]

    # normal cursor (no range selection)
    assert get_overlapped_ranges(get_range((0, 0), (0, 0))) == [r1]
    assert get_overlapped_ranges(get_range((10, 10), (10, 10))) == [r2]
    assert get_overlapped_ranges(get_range((15, 0), (15, 0))) == [r2, r3, r4]
    assert get_overlapped_ranges(get_range((16, 0), (16, 0))) == [r2, r3]
    assert get_overlapped_ranges(get_range((20, 1), (20, 1))) == []
    assert get_overlapped_ranges(get_range((21, 0), (21, 0))) == []

    # range selection
    assert get_overlapped_ranges(get_range((9, 30), (19, 30))) == [r1, r2, r3, r4]
    assert get_overlapped_ranges(get_range((9, 30), (10, 9))) == [r1]
    assert get_overlapped_ranges(get_range((15, 0), (16, 0))) == [r2, r3, r4]
    assert get_overlapped_ranges(get_range((15, 10), (16, 0))) == [r2, r3]
    assert get_overlapped_ranges(get_range((21, 0), (22, 0))) == []


def test_create_text_edit() -> None:
    with pytest.raises(AssertionError):
        create_text_edit(
            get_pysen_diagnostic(
                start_line=10, start_column=20, end_line=11, message="hello"
            )
        )

    diagnostic = get_pysen_diagnostic(
        start_line=10,
        start_column=20,
        end_line=11,
        diff="-aaa\n bbb  \n+ccc\n+ddd\n eee\n-fff",
    )
    edit = create_text_edit(diagnostic)
    assert edit.range == get_range((9, 19), (11, 0))
    assert edit.new_text == "bbb  \nccc\nddd\neee\n"

    diagnostic = get_pysen_diagnostic(
        start_line=10,
        start_column=20,
        end_line=11,
        diff="-aaa\n-bbb\n",
    )
    edit = create_text_edit(diagnostic)
    assert edit.range == get_range((9, 19), (11, 0))
    assert edit.new_text == ""


def test_create_diagnostic() -> None:
    pysen_diagnostic = get_pysen_diagnostic(
        start_line=10, start_column=20, end_line=11, message="hello"
    )
    lsp_diagnostic = create_diagnostic(
        pysen_diagnostic, "default", "E01", "pysen source"
    )
    assert lsp_diagnostic.range == get_range((9, 19), (10, 0))
    assert lsp_diagnostic.message == "hello"
    assert lsp_diagnostic.severity == DiagnosticSeverity.Warning
    assert lsp_diagnostic.code == "E01"
    assert lsp_diagnostic.source == "pysen source"

    pysen_diagnostic = get_pysen_diagnostic(
        start_line=10,
        start_column=20,
        end_line=11,
        diff="-\n",
    )
    lsp_diagnostic = create_diagnostic(
        pysen_diagnostic, "default", "E01", "pysen source"
    )
    assert lsp_diagnostic.message == "default"


def test_create_code_action() -> None:
    pysen_diagnostic = get_pysen_diagnostic(
        start_line=10, start_column=20, end_line=11, message="hello"
    )
    assert (
        create_code_action(
            "Format with pysen",
            "file://source/pysen.py",
            None,
            pysen_diagnostic,
            [],
        )
        is None
    )

    pysen_diagnostic = get_pysen_diagnostic(
        start_line=10,
        start_column=20,
        end_line=11,
        diff="+aaa\n bbb\n-ccc",
    )
    lsp_diagnostic = create_diagnostic(
        pysen_diagnostic, "Error from pysen", None, "pysen"
    )
    action = create_code_action(
        "Format with pysen",
        "file://source/pysen.py",
        1,
        pysen_diagnostic,
        [lsp_diagnostic],
    )
    assert action is not None
    assert action.title == "Format with pysen"
    assert action.kind == CodeActionKind.QuickFix
    assert action.diagnostics == [lsp_diagnostic]
    assert isinstance(action.edit, WorkspaceEdit)
    changes = action.edit.document_changes
    assert changes is not None and len(changes) == 1
    change = changes[0]
    assert isinstance(change, TextDocumentEdit)
    assert isinstance(change.text_document, OptionalVersionedTextDocumentIdentifier)
    assert change.text_document.uri == "file://source/pysen.py"
    assert change.text_document.version == 1
    assert change.edits == [create_text_edit(pysen_diagnostic)]
