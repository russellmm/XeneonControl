param([string]$Python = 'python.exe')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
& $Python -m venv '.build-env'
if ($LASTEXITCODE) { throw 'Could not create build environment' }
$buildPython = Join-Path $PSScriptRoot '.build-env\Scripts\python.exe'
& $buildPython -m pip install 'pyinstaller==6.22.3'
if ($LASTEXITCODE) { throw 'Could not install build dependency' }
& $buildPython -m unittest -v test_protocol test_refresh test_tray
if ($LASTEXITCODE) { throw 'Tests failed' }
& $buildPython -m PyInstaller --noconfirm --clean --onefile --windowed --name XeneonControl --icon "$PSScriptRoot	ray.ico" --add-data "$PSScriptRoot	ray.ico;." --distpath release --workpath .build --specpath .build xeneon_control.py
if ($LASTEXITCODE) { throw 'Packaging failed' }
Write-Host 'Built release\XeneonControl.exe'
