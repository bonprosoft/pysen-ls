from typing import List, Optional, Sequence, cast

import pysen.diagnostic
from pygls.lsp.types import (
    CodeAction,
    CodeActionKind,
    Diagnostic,
    DiagnosticSeverity,
    OptionalVersionedTextDocumentIdentifier,
    Position,
    Range,
    TextDocumentEdit,
    TextEdit,
    WorkspaceEdit,
)

from .types import DocumentVersionType


def get_diagnostic_range(diagnostic: pysen.diagnostic.Diagnostic) -> Range:
    start_line = diagnostic.start_line or 1
    start_column = diagnostic.start_column or 1
    end_line = diagnostic.end_line or start_line
    if diagnostic.diff is not None:
        has_delection = any(
            line for line in diagnostic.diff.splitlines() if line.startswith("-")
        )
        if has_delection:
            end_line += 1

    end_column = start_column
    if start_line != end_line:
        end_column = 1

    return Range(
        start=Position(line=start_line - 1, character=start_column - 1),
        end=Position(line=end_line - 1, character=end_column - 1),
    )


def has_overlap(lhs: Range, rhs: Range) -> bool:
    """Check if lhs has overlap with rhs"""
    return cast(bool, max(lhs.start, rhs.start) <= min(lhs.end, rhs.end))


def create_diagnostic(
    diagnostic: pysen.diagnostic.Diagnostic,
    default_message: str,
    code: str,
    source: str,
) -> Diagnostic:
    message = diagnostic.message or default_message

    return Diagnostic(
        range=get_diagnostic_range(diagnostic),
        message=message,
        severity=DiagnosticSeverity.Warning,
        code=code,
        source=source,
        related_information=None,
        tags=None,
    )


def create_code_action(
    title: str,
    document_uri: str,
    document_version: Optional[DocumentVersionType],
    diagnostic: pysen.diagnostic.Diagnostic,
    reference_diagnostics: Sequence[Diagnostic],
) -> Optional[CodeAction]:
    if diagnostic.diff is None:
        return None

    # TODO(igarashi): Use unidiff to get hunks
    edit_range = get_diagnostic_range(diagnostic)
    new_text: List[str] = []
    for line in diagnostic.diff.splitlines(keepends=True):
        if line.startswith("+") or line.startswith(" "):
            new_text.append(line[1:])

    return CodeAction(
        title=title,
        kind=CodeActionKind.QuickFix,
        diagnostics=list(reference_diagnostics),
        edit=WorkspaceEdit(
            document_changes=[
                TextDocumentEdit(
                    text_document=OptionalVersionedTextDocumentIdentifier(
                        uri=document_uri,
                        version=document_version,
                    ),
                    edits=[
                        TextEdit(
                            range=edit_range,
                            new_text="".join(new_text),
                        ),
                    ],
                ),
            ],
        ),
    )
