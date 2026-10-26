# Starts Streamlit (8599), FastAPI (8099) and Vite dev (5199 -> /api on 8099),
# waits for all three, runs take_screenshots.py (Playwright, headless) into
# docs/screenshots/, then stops only the processes it started. Avoids
# 8501/8000/5173/8010/5190, so a demo already running is never disturbed.
#
#   powershell -ExecutionPolicy Bypass -File scripts\screenshots\take_screenshots.ps1 [-Theme dark|light]
#
# Needs Playwright once:
#   .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
#   .venv\Scripts\python.exe -m playwright install chromium
param([string]$Theme = "dark", [string]$Python = "")

$Here = $PSScriptRoot
$Repo = (Resolve-Path "$Here\..\..").Path
# -Python for a git worktree, which has no .venv of its own.
$Py   = if ($Python) { $Python } else { "$Repo\.venv\Scripts\python.exe" }
$Out  = "$Repo\docs\screenshots"
$Logs = "$env:TEMP\flood-policy-kit-screenshots"
New-Item -ItemType Directory -Force $Logs | Out-Null

$started = @()
try {
    $started += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $Repo $Py `
        -ArgumentList "-m streamlit run app/streamlit_app.py --server.port 8599 --server.headless true --browser.gatherUsageStats false" `
        -RedirectStandardOutput "$Logs\streamlit.log" -RedirectStandardError "$Logs\streamlit.err.log"
    $started += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $Repo $Py `
        -ArgumentList "-m uvicorn api.main:app --host 127.0.0.1 --port 8099" `
        -RedirectStandardOutput "$Logs\api.log" -RedirectStandardError "$Logs\api.err.log"
    # web/vite.config.js reads these two, so the dev server gets its own port.
    $env:VITE_PORT = "5199"; $env:VITE_API = "http://127.0.0.1:8099"
    $started += Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory "$Repo\web" "node" `
        -ArgumentList "node_modules/vite/bin/vite.js" `
        -RedirectStandardOutput "$Logs\vite.log" -RedirectStandardError "$Logs\vite.err.log"

    $urls = "http://localhost:8599/_stcore/health", "http://127.0.0.1:8099/api/meta", "http://localhost:5199/api/meta"
    $deadline = (Get-Date).AddSeconds(300)  # the API indexes the PDF corpus at startup
    foreach ($u in $urls) {
        while ($true) {
            # curl.exe, not Invoke-WebRequest: PowerShell 5.1 routes localhost
            # through the system proxy and never reached the API.
            $code = curl.exe -s -o NUL -w "%{http_code}" --noproxy "*" --max-time 10 $u
            if ($code -eq "200") { break }
            if ((Get-Date) -gt $deadline) { throw "not up: $u (logs in $Logs)" }
            Start-Sleep -Milliseconds 500
        }
    }

    & $Py "$Here\take_screenshots.py" $Out "http://localhost:8599/" "http://localhost:5199/" $Theme
}
finally {
    # Kill each started process with its children (python/node spawn workers).
    foreach ($p in $started) { if ($p) { taskkill /PID $p.Id /T /F 2>$null | Out-Null } }
}
