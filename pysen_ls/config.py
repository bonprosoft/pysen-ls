from typing import List

from pygls.lsp.types import Model


class LanguageServerConfiguration(Model):  # type: ignore
    enable_lint_on_save: bool
    enable_code_action: bool
    lint_targets: List[str]
    format_targets: List[str]

    @classmethod
    def default(cls) -> "LanguageServerConfiguration":
        return cls(
            enable_lint_on_save=True,
            enable_code_action=True,
            lint_targets=["lint"],
            format_targets=["format", "lint"],
        )
