# Transcribee Audapolis Exporter

A simple scripts that takes a [transcribee][https://github.com/transcribee/transcribee] document and converts it into an audapolis document.

> **Warning**:
> This is very untested.
>
> Known Issues:
>
> - Mediafiles are currently not re-encoded in a way that ensure that audapolis can work with them.

## Usage

This project uses [pdm](https://pdm.fming.dev/) for python package management.
In addition to pdm, you probably also need the following dependencies on your system:

- libiconv
- rustc with a version >= 1.65.0

Now you can install the python dependencies using

```shell
pdm install
```

and then run the tool using the following command.
You need to replace `[TRANSCRIBEE_BASE_URL]` with the correct base url of your transcribee instance.
For example: `http://localhost:8000`

```
pdm run python dump.py [TRANSCRIBEE_BASE_URL]
```

### Nix

The `shell.nix` also contains all dependencies and can be used with `direnv` or via `nix-shell`.
