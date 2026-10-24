# Zxoos Macros

Zxoos is a Windows desktop macro utility. The `v2` release includes the
controller interface, configurable ping estimation, and a small version
indicator that checks the GitHub repository for newer releases or version
tags. The version check only notifies you; it does not download or install
updates automatically.

## Download

Download **Zxoos latest.exe** from the [GitHub Releases](https://github.com/iki8181/Zxoos-macros/releases) page.

## Run

Run the downloaded executable on Windows. The application uses Windows input
APIs and may need to be run with the same privilege level as the target
application for its input controls to work.

## Build from source

The Python app requires Python 3 and the `keyboard` package. To build the
packaged application, install PyInstaller and run:

```powershell
python -m pip install keyboard pyinstaller
pyinstaller --clean --noconfirm Zxoos.spec
```

The AutoHotkey controller source is provided separately as `zxoos.ahk` and
requires AutoHotkey v2.

## Security

The executable is unsigned. Review the source and scan downloaded files with
your security software before running them. A SHA-256 checksum is provided
with each release asset when available.
