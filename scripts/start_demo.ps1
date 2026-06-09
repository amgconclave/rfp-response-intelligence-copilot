param(
    [string]$Python = "python",
    [int]$ApiPort = 8000,
    [int]$DashboardPort = 8501
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Test-LocalPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $result = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $connected = $result.AsyncWaitHandle.WaitOne(250, $false)
        if ($connected) {
            $client.EndConnect($result)
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
    finally {
        $client.Close()
    }
}

Write-Host "Runtime Demo starter"
Write-Host "Repo: $Root"
Write-Host "This script will not stop or kill existing processes."
Write-Host ""

& $Python scripts\runtime_check.py
if ($LASTEXITCODE -ne 0) {
    throw "Runtime preflight failed. Install dependencies before starting the demo servers."
}

$started = @()

if (Test-LocalPort -Port $ApiPort) {
    Write-Host "FastAPI port $ApiPort is already listening; skipping API start."
}
else {
    $apiArgs = "-m uvicorn app.main:app --reload --host 127.0.0.1 --port $ApiPort"
    $api = Start-Process -FilePath $Python -ArgumentList $apiArgs -PassThru -WindowStyle Hidden
    $started += @{ Service = "FastAPI"; Id = $api.Id; Url = "http://127.0.0.1:$ApiPort" }
    Write-Host "Started FastAPI PID $($api.Id) at http://127.0.0.1:$ApiPort"
}

if (Test-LocalPort -Port $DashboardPort) {
    Write-Host "Streamlit port $DashboardPort is already listening; skipping dashboard start."
}
else {
    $dashboardArgs = "-m streamlit run dashboard/app.py --server.port $DashboardPort"
    $dashboard = Start-Process -FilePath $Python -ArgumentList $dashboardArgs -PassThru -WindowStyle Hidden
    $started += @{ Service = "Streamlit"; Id = $dashboard.Id; Url = "http://127.0.0.1:$DashboardPort" }
    Write-Host "Started Streamlit PID $($dashboard.Id) at http://127.0.0.1:$DashboardPort"
}

Write-Host ""
Write-Host "Health checks:"
Write-Host "  API: http://127.0.0.1:$ApiPort/health"
Write-Host "  Docs: http://127.0.0.1:$ApiPort/docs"
Write-Host "  Dashboard: http://127.0.0.1:$DashboardPort"
Write-Host ""
Write-Host "Manual stop commands for processes started by this script:"
foreach ($item in $started) {
    Write-Host "  Stop-Process -Id $($item.Id)  # $($item.Service)"
}
if ($started.Count -eq 0) {
    Write-Host "  No new processes were started."
}
