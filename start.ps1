# start.ps1 — Launch ResolveDesk (FastAPI backend + React frontend)
# Run from the project root: powershell -File start.ps1

$PYTHON = "C:\Users\User\Desktop\RESLOVED AI\venv\Scripts\python.exe"
$NODE_PATH = "C:\Program Files\nodejs"

Write-Host "=== ResolveDesk Startup ===" -ForegroundColor Cyan
Write-Host ""

# Start FastAPI backend
Write-Host "Starting FastAPI backend on http://localhost:8000 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$PYTHON' -m uvicorn backend.main:app --reload --port 8000"

Start-Sleep 2

# Start React frontend
Write-Host "Starting React frontend on http://localhost:5173 ..." -ForegroundColor Green
$env:PATH = "$NODE_PATH;" + $env:PATH
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PATH = 'C:\Program Files\nodejs;' + `$env:PATH; cd frontend; & 'C:\Program Files\nodejs\npm.cmd' run dev"

Start-Sleep 3

Write-Host ""
Write-Host "=== Ready! ===" -ForegroundColor Cyan
Write-Host "  React UI  : http://localhost:5173" -ForegroundColor Yellow
Write-Host "  API Docs  : http://localhost:8000/docs" -ForegroundColor Yellow
Write-Host ""
