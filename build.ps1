$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Ambiente .venv ausente. Consulte README.md.'
}
$basePython = & $python -c 'import sys; print(sys.base_prefix)'
& $python -m PyInstaller --noconfirm --clean --onedir --windowed `
    --name LeitorProfitV3 `
    --paths (Join-Path $basePython 'Lib') `
    --paths (Join-Path $basePython 'DLLs') `
    --hidden-import tkinter `
    --hidden-import _tkinter `
    --collect-all tkinter `
    --add-binary "$(Join-Path $basePython 'DLLs\_tkinter.pyd');." `
    --add-binary "$(Join-Path $basePython 'DLLs\tcl86t.dll');." `
    --add-binary "$(Join-Path $basePython 'DLLs\tk86t.dll');." `
    --add-data "$(Join-Path $basePython 'tcl');tcl" `
    --collect-all rapidocr `
    --collect-all windows_capture `
    --collect-binaries onnxruntime `
    --hidden-import pystray._win32 `
    (Join-Path $projectDir 'run_app.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar executável.' }
Write-Host "Executável: $(Join-Path $projectDir 'dist\LeitorProfitV3\LeitorProfitV3.exe')"
