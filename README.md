# Zxoos Macros

Windows macro and overlay app.

Join the [Discord server](https://discord.gg/HkyW7sEZT9) for updates.

## Overlays

- Enable **Macro Overlay** and **Keystrokes Overlay** independently in Settings.
- Drag either window by its title bar and resize it from a window edge.
- Turn **Roblox Auto-Sync** off to place the windows freely. With Auto-Sync on,
  the overlays follow the Roblox window; keystrokes are displayed only while
  Roblox is focused.

## Build

Build the single-file Windows app from the project folder:

```powershell
pyinstaller --noconfirm Zxoos.spec
```

The build includes `ui-click.mp3` and `keystroke-click.mp3`.
