import hashlib
import os
import re
import struct
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request


GITHUB_RELEASE_PATH = "/iki8181/Zxoos-macros/releases/download/"
MAX_UPDATE_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
UPDATE_USER_AGENT = "Zxoos-Updater"


def _shortcut_setup_script():
    return """$desktopPath = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$shortcutPath = Join-Path $desktopPath 'Zxoos.lnk'
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $workingDirectory
$shortcut.IconLocation = "$targetPath,0"
$shortcut.Description = "Zxoos $version"
$shortcut.Save()
if ($oldPath -ne $targetPath) {
    Get-ChildItem -LiteralPath $desktopPath -Filter '*.lnk' -File |
        ForEach-Object {
            $existingShortcut = $shell.CreateShortcut($_.FullName)
            if ($existingShortcut.TargetPath -ieq $oldPath) {
                $existingShortcut.TargetPath = $targetPath
                $existingShortcut.WorkingDirectory = $workingDirectory
                $existingShortcut.IconLocation = "$targetPath,0"
                $existingShortcut.Save()
            }
        }
}
"""


def select_update_asset(release, executable_path, fallback_name="zxoos.exe"):
    assets = release.get("assets")
    if not isinstance(assets, list):
        return None

    names = {
        asset.get("name", "").casefold(): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("name"), str)
    }
    executable_name = os.path.basename(executable_path).casefold()
    for name in dict.fromkeys((executable_name, fallback_name.casefold())):
        asset = names.get(name)
        if asset is not None:
            return asset
    return None


def _validate_asset(asset):
    url = asset.get("browser_download_url")
    if not isinstance(url, str):
        raise ValueError("The update release does not include a download URL.")

    parsed_url = urllib.parse.urlparse(url)
    if (parsed_url.scheme != "https"
            or parsed_url.hostname != "github.com"
            or not parsed_url.path.startswith(GITHUB_RELEASE_PATH)):
        raise ValueError("The update download URL is not a trusted GitHub release.")

    expected_size = asset.get("size")
    if (not isinstance(expected_size, int)
            or expected_size <= 0
            or expected_size > MAX_UPDATE_SIZE):
        raise ValueError("The update release has an invalid file size.")

    digest = asset.get("digest")
    if digest is not None and (
            not isinstance(digest, str)
            or re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest) is None):
        raise ValueError("The update release has an invalid SHA-256 digest.")
    return url, expected_size, digest


def _validate_executable(path, size):
    with open(path, "rb") as update_file:
        header = update_file.read(64)
        if len(header) < 64 or header[:2] != b"MZ":
            raise ValueError("The downloaded update is not a Windows executable.")
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        if pe_offset > size - 4:
            raise ValueError("The downloaded executable has an invalid PE header.")
        update_file.seek(pe_offset)
        if update_file.read(4) != b"PE\0\0":
            raise ValueError("The downloaded executable has an invalid PE header.")


def download_update(asset, executable_path):
    url, expected_size, digest = _validate_asset(asset)
    directory = os.path.dirname(os.path.abspath(executable_path))
    request = urllib.request.Request(
        url, headers={"User-Agent": UPDATE_USER_AGENT})
    update_path = None
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            with tempfile.NamedTemporaryFile(
                    prefix=".Zxoos-update-", suffix=".exe", dir=directory,
                    delete=False) as update_file:
                update_path = update_file.name
                hasher = hashlib.sha256()
                size = 0
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_UPDATE_SIZE or size > expected_size:
                        raise ValueError("The downloaded update is larger than expected.")
                    hasher.update(chunk)
                    update_file.write(chunk)

        if size != expected_size:
            raise ValueError("The downloaded update is incomplete.")
        if digest is not None and hasher.hexdigest().casefold() != digest[7:].casefold():
            raise ValueError("The downloaded update failed its SHA-256 check.")
        _validate_executable(update_path, size)
        return update_path
    except (OSError, urllib.error.URLError, TimeoutError, ValueError):
        if update_path is not None:
            try:
                os.remove(update_path)
            except FileNotFoundError:
                pass
        raise


def install_update(
        update_path, executable_path, version=None, create_desktop_shortcut=False):
    old_path = os.path.abspath(executable_path)
    update_path = os.path.abspath(update_path)
    if os.path.dirname(update_path).casefold() != os.path.dirname(old_path).casefold():
        raise ValueError("The downloaded update must be next to the application.")

    if version is not None:
        if re.fullmatch(r"v?\d+(?:\.\d+){0,3}", version, re.IGNORECASE) is None:
            raise ValueError("The update version is invalid.")
        target_path = os.path.join(
            os.path.dirname(old_path), f"Zxoos ({version}).exe")
    else:
        target_path = old_path

    script = f"""$ErrorActionPreference = 'Stop'
$processId = {os.getpid()}
$updatePath = '{update_path.replace("'", "''")}'
$oldPath = '{old_path.replace("'", "''")}'
$targetPath = '{target_path.replace("'", "''")}'
$workingDirectory = '{os.path.dirname(target_path).replace("'", "''")}'
$version = '{version or ""}'
$createDesktopShortcut = ${str(create_desktop_shortcut).lower()}
try {{
    $deadline = (Get-Date).AddSeconds(90)
    while (Get-Process -Id $processId -ErrorAction SilentlyContinue) {{
        if ((Get-Date) -ge $deadline) {{
            throw 'Zxoos did not close in time to finish the update.'
        }}
        Start-Sleep -Milliseconds 500
    }}
    Move-Item -LiteralPath $updatePath -Destination $targetPath -Force
    if (-not (Test-Path -LiteralPath $targetPath -PathType Leaf)) {{
        throw 'The updated Zxoos executable was not found after installation.'
    }}
    $shortcutError = $null
    if ($createDesktopShortcut) {{
        try {{
{_shortcut_setup_script()}
        }} catch {{
            $shortcutError = $_.Exception.Message
        }}
    }}
    $newProcess = Start-Process -FilePath $targetPath `
        -WorkingDirectory $workingDirectory -PassThru
    Start-Sleep -Seconds 8
    if ($newProcess.HasExited) {{
        throw 'Zxoos closed during startup. Open the updated executable manually.'
    }}
    if ($shortcutError) {{
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "Zxoos was updated and started, but the desktop shortcut could not be created:`n`n$shortcutError",
            'Zxoos desktop shortcut failed', 'OK', 'Warning') | Out-Null
    }}
    if ($oldPath -ne $targetPath) {{
        Remove-Item -LiteralPath $oldPath -Force
    }}
}} catch {{
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        $_.Exception.Message, 'Zxoos update failed', 'OK', 'Error') | Out-Null
}} finally {{
    Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
}}
"""
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-16", suffix=".ps1",
            prefix="zxoos-update-", delete=False) as script_file:
        script_file.write(script)
        script_path = script_file.name

    try:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-WindowStyle", "Hidden", "-File", script_path],
            creationflags=(subprocess.DETACHED_PROCESS
                           | subprocess.CREATE_NEW_PROCESS_GROUP),
            close_fds=True)
    except OSError:
        os.remove(script_path)
        raise
