
$ErrorActionPreference = "Stop"

Write-Host "Starting ResolveAIV2 Backend and Frontend..." -ForegroundColor Cyan

# Start Backend
Write-Host "Starting Backend (FastAPI on port 8000)..." -ForegroundColor Green
$backend = Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -Command `"cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`"" -NoNewWindow -PassThru

# Start Frontend
Write-Host "Starting Frontend (Vite on port 5173)..." -ForegroundColor Green
$frontend = Start-Process powershell -ArgumentList "-NoProfile -Command `"cd frontend; npm run dev`"" -NoNewWindow -PassThru

Write-Host "Both servers are running in this terminal. Press Ctrl+C to exit and kill both." -ForegroundColor Yellow

try {
    # Wait indefinitely for both processes
    Wait-Process -Id $backend.Id, $frontend.Id
}
finally {
    Write-Host "`nStopping servers..." -ForegroundColor Cyan
    if ($backend -and !$backend.HasExited) { 
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontend -and !$frontend.HasExited) { 
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Servers stopped." -ForegroundColor Cyan
}
