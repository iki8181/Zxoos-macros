# Zxoos Macros

Windows desktop macro and overlay app. The source is published here so users
can inspect what it does; publishing source is not a guarantee or independent
security certification.

## Run from source

Requirements: Windows and Python.

```powershell
py -m pip install -r requirements.txt
py app.py
```

## Build

```powershell
py -m pip install pyinstaller
pyinstaller --noconfirm Zxoos.spec
```

The app uses the `keyboard` package for configured hotkeys and keyboard input.
Its macros also send keyboard and mouse input. Roblox-specific hotkeys check
whether the Roblox process is in the foreground. Presets are read from or
written to a file selected by the user.

## Network and updater behavior

The app checks the GitHub Releases API for release/tag information. When a
newer release is available, the app may offer an update. A required update
downloads a release executable and installs it. On Windows, `updater.py`
starts a hidden PowerShell process to replace/restart the executable and, when
requested, create a desktop shortcut. Review `updater.py` before running a
prebuilt executable if you want to inspect this behavior.

The source does not establish that a release executable was built from these
exact files. Compare release binaries with a build you make yourself if that
matters to you.

## Project files

- `app.py` — application UI, hotkeys, overlays, and macros.
- `updater.py` — GitHub release download and executable update handling.
- `requirements.txt` — Python package needed to run from source.
- `Zxoos.spec` and `circle.ico` — PyInstaller build configuration and icon.

Join the [Discord server](https://discord.gg/HkyW7sEZT9) for updates.
