$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$pythonExe = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Prvo napravite .venv i instalirajte requirements-build.txt; pogledajte README.md.'
}
Push-Location -LiteralPath $projectDir
try {
    & $pythonExe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Testovi nisu prošli.' }
    & $pythonExe -m PyInstaller --noconfirm --clean --onefile --windowed --name 'ePoint CSV Studio' --collect-data jsonschema_specifications --hidden-import epoint_csv.ui --hidden-import epoint_csv.core --hidden-import epoint_csv.research --hidden-import epoint_csv.secrets main.py
    if ($LASTEXITCODE -ne 0) { throw 'Izrada EXE nije uspjela.' }
    Copy-Item -LiteralPath (Join-Path $projectDir 'README.md') -Destination (Join-Path $projectDir 'dist\UPUTE.md')
    Copy-Item -LiteralPath (Join-Path $projectDir 'PROVJERE.md') -Destination (Join-Path $projectDir 'dist\PROVJERE.md')
    $browserSource = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'ms-playwright'
    if (-not (Test-Path -LiteralPath $browserSource)) { throw 'Playwright Chromium nije instaliran. Pokrenite: .\.venv\Scripts\python.exe -m playwright install chromium' }
    if (Test-Path -LiteralPath (Join-Path $projectDir 'dist\ms-playwright')) { Remove-Item -LiteralPath (Join-Path $projectDir 'dist\ms-playwright') -Recurse -Force }
    Copy-Item -LiteralPath $browserSource -Destination (Join-Path $projectDir 'dist\ms-playwright') -Recurse
    Get-FileHash -LiteralPath (Join-Path $projectDir 'dist\ePoint CSV Studio.exe') -Algorithm SHA256
} finally {
    Pop-Location
}


