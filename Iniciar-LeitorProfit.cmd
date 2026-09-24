@echo off
cd /d "%~dp0"
if exist "dist\LeitorProfitV3\LeitorProfitV3.exe" (
  start "" "dist\LeitorProfitV3\LeitorProfitV3.exe"
  exit /b 0
)
if exist "dist\LeitorProfitV2\LeitorProfitV2.exe" (
  start "" "dist\LeitorProfitV2\LeitorProfitV2.exe"
  exit /b 0
)
if exist "dist\LeitorProfit\LeitorProfit.exe" (
  start "" "dist\LeitorProfit\LeitorProfit.exe"
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m profit_alert
  exit /b 0
)
echo O aplicativo nao esta instalado. Consulte README.md para preparar o ambiente.
pause
exit /b 1
