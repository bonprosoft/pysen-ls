# pysen-ls: A language server implementation for pysen

pysen-ls is a language server implementation for [pysen](https://github.com/pfnet/pysen).

```sh
$ pip install pysen-ls
```

## Supported Features

- Diagnostics
  - Triggers `pysen run lint` on save
- Code action
  - Supports incremental document updates

## Editor setups

### VSCode

- [pysen-vscode](https://github.com/bonprosoft/pysen-vscode)


## Provided Custom Commands

- `pysen.callLintDocument`
- `pysen.callFormatDocument`
- `pysen.callLintWorkspace`
- `pysen.callFormatWorkspace`
- `pysen.reloadServerConfiguration`
