$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$venv = Join-Path $root "backend\.venv"
$exe = Join-Path $venv "Scripts\python.exe"

function Test-Interpreter([string]$command, [string[]]$options = @()) {
    $ErrorActionPreference = "Continue"
    if (!$command -or !(Test-Path -LiteralPath $command -PathType Leaf)) { return }
    $probe = "import sys,struct,venv,ensurepip; print(sys.executable); print(sys.version.split()[0]); sys.exit(0 if (sys.implementation.name == 'cpython' and (3,10) <= sys.version_info[:2] < (4,0) and struct.calcsize('P') == 8) else 1)"
    $lines = @(& $command @options -c $probe 2>$null)
    if ($LASTEXITCODE -eq 0 -and $lines.Count -ge 2) {
        Write-Host "Using Python $($lines[-1]) at $($lines[-2])"
        return $lines[-2]
    }
    if ($lines.Count -ge 2) { Write-Host "Found Python $($lines[-1]) at $($lines[-2]); this app needs 64-bit CPython 3.10 or newer." }
}

function Find-Python {
    $path = Test-Interpreter $exe
    if ($path) { return $path }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($tag in @('-3', '-3.12', '-3.13', '-3.11', '-3.14', '-3.10')) {
            $path = Test-Interpreter $py.Source @($tag)
            if ($path) { return $path }
        }
    }
    $candidates = @()
    foreach ($name in @('python.exe','python3.exe')) {
        $candidates += @(Get-Command $name -All -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    }
    foreach ($hive in @('HKCU:\Software\Python','HKLM:\Software\Python')) {
        foreach ($item in @(Get-ChildItem "$hive\*\*\InstallPath" -ErrorAction SilentlyContinue)) {
            $candidates += $item.GetValue('ExecutablePath')
            $installDir = $item.GetValue('')
            if ($installDir) { $candidates += Join-Path $installDir 'python.exe' }
        }
    }
    foreach ($pattern in @("$env:LOCALAPPDATA\Programs\Python\Python*\python.exe",
                            "$env:LOCALAPPDATA\Python\pythoncore-*\python.exe",
                            "$env:ProgramFiles\Python*\python.exe",
                            "$env:USERPROFILE\miniconda3\python.exe",
                            "$env:USERPROFILE\anaconda3\python.exe")) {
        $candidates += @(Get-Item -Path $pattern -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
    }
    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        $path = Test-Interpreter $candidate
        if ($path) { return $path }
    }
}

try {
    $python = Find-Python
    if (!$python) {
        Write-Host "Could not find a usable 64-bit Python 3.10+ with venv and pip."
        $manual = Read-Host 'Paste the full path to your python.exe, or press Enter to install Python'
        if ($manual.Trim()) {
            $python = Test-Interpreter ($manual.Trim().Trim('"'))
            if (!$python) { throw "That executable could not run the Python check. See RUN.md for the path lookup command." }
        } else {
            if (!(Get-Command winget.exe -ErrorAction SilentlyContinue)) {
                throw "Install 64-bit Python from https://www.python.org/downloads/windows/ with pip enabled, then reopen run.cmd. No App Installer is required for this route."
            }
            & winget.exe install --id Python.Python.3.12 --exact --source winget --accept-source-agreements --accept-package-agreements
            if ($LASTEXITCODE -ne 0) { throw "Python installation did not complete. See RUN.md for manual setup." }
            $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") + ";" + $env:Path
            $python = Find-Python
            if (!$python) { throw "Reopen run.cmd to pick up the newly installed Python." }
        }
    }
    if ($python -ne $exe) {
        if (Test-Path -LiteralPath $venv) {
            $backup = "$venv-backup-$([Guid]::NewGuid().ToString('N'))"
            Move-Item -LiteralPath $venv -Destination $backup
            Write-Host "Saved the unusable project environment at $backup."
        }
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create the project's Python environment." }
    }
    & $exe -m pip install --disable-pip-version-check -r backend/requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Python package installation failed. Check pip's message above." }
    & $exe scripts/launch.py
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
