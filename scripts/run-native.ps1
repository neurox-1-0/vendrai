# Native (non-Docker) NeuroX runtime for Windows.
# Mirrors scripts/stack.sh's product-up / product-down / status, but for
# binaries and Python/Node processes running directly on this machine
# instead of containers.
#
# Usage: pwsh scripts/run-native.ps1 <start|stop|status>

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("start", "stop", "status")]
    [string]$Command
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$native = Join-Path $root "native"
$logs = Join-Path $native "logs"
$pidFile = Join-Path $native ".pids.json"
$venvPy = Join-Path $root "services\api\.venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Get-EnvValue($key) {
    $line = Get-Content (Join-Path $root ".env") | Where-Object { $_ -match "^$key=" } | Select-Object -First 1
    if (-not $line) { return "" }
    return ($line -split "=", 2)[1]
}

function Save-Pids($table) {
    $table | ConvertTo-Json | Set-Content -Path $pidFile
}

function Load-Pids() {
    if (Test-Path $pidFile) {
        return Get-Content $pidFile | ConvertFrom-Json -AsHashtable
    }
    return @{}
}

function Start-Native($name, $exe, $arguments, $workDir, $envOverrides) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = $arguments
    if ($workDir) { $psi.WorkingDirectory = $workDir }
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    foreach ($k in $envOverrides.Keys) { $psi.EnvironmentVariables[$k] = $envOverrides[$k] }
    $proc = [System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Milliseconds 300
    $logFile = Join-Path $logs "$name.log"
    Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived -Action {
        Add-Content -Path $Event.MessageData -Value $EventArgs.Data
    } -MessageData $logFile | Out-Null
    Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived -Action {
        Add-Content -Path $Event.MessageData -Value $EventArgs.Data
    } -MessageData $logFile | Out-Null
    $proc.BeginOutputReadLine()
    $proc.BeginErrorReadLine()
    Write-Output "Started $name (PID $($proc.Id))"
    return $proc.Id
}

function Wait-Port($port, $seconds = 60) {
    for ($i = 0; $i -lt $seconds; $i++) {
        $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($conn) { return $true }
        Start-Sleep -Seconds 1
    }
    return $false
}

if ($Command -eq "status") {
    $ports = @{
        "postgres (5432)" = 5432; "redis (6379)" = 6379; "rabbitmq (5672)" = 5672
        "qdrant (6333)" = 6333; "minio (9000)" = 9000; "clamav (3310)" = 3310
        "opa (8181)" = 8181; "keycloak (8080)" = 8080; "mailpit (8025)" = 8025
        "mock-erp (8090)" = 8090; "api (8000)" = 8000; "web (3000)" = 3000
    }
    foreach ($k in $ports.Keys) {
        $up = Get-NetTCPConnection -LocalPort $ports[$k] -State Listen -ErrorAction SilentlyContinue
        $status = if ($up) { "UP" } else { "down" }
        Write-Output ("{0,-20} {1}" -f $k, $status)
    }
    exit 0
}

if ($Command -eq "stop") {
    $pids = Load-Pids
    foreach ($name in $pids.Keys) {
        $procId = $pids[$name]
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Output "Stopped $name (PID $procId)"
    }
    Remove-Item -Path $pidFile -ErrorAction SilentlyContinue
    Write-Output "Note: Postgres and Redis run as persistent Windows services and were left running."
    exit 0
}

# --- start ---
$pids = @{}

# Binaries not already running as Windows services.
$pids["qdrant"] = Start-Native "qdrant" "$native\qdrant\qdrant.exe" "" "$native\qdrant" @{}
$pids["opa"] = Start-Native "opa" "$native\opa\opa.exe" "run --server --addr=0.0.0.0:8181 `"$root\policies`"" "$native\opa" @{}
$pids["mailpit"] = Start-Native "mailpit" "$native\mailpit\mailpit.exe" "" "$native\mailpit" @{}

$pids["minio"] = Start-Native "minio" "$native\minio\minio.exe" "server `"$native\minio\data`" --console-address :9001" "$native\minio" @{
    MINIO_ROOT_USER     = Get-EnvValue "MINIO_ROOT_USER"
    MINIO_ROOT_PASSWORD = Get-EnvValue "MINIO_ROOT_PASSWORD"
}
Wait-Port 9000 30 | Out-Null

$pids["clamd"] = Start-Native "clamd" "C:\Program Files\ClamAV\clamd.exe" "--config-file=`"$native\clamav\clamd.conf`"" $null @{}
Wait-Port 3310 60 | Out-Null

$pids["keycloak"] = Start-Native "keycloak" "$native\keycloak-26.2.5\bin\kc.bat" "start-dev --import-realm --http-port=8080" "$native\keycloak-26.2.5" @{
    KC_BOOTSTRAP_ADMIN_USERNAME = Get-EnvValue "KEYCLOAK_ADMIN"
    KC_BOOTSTRAP_ADMIN_PASSWORD = Get-EnvValue "KEYCLOAK_ADMIN_PASSWORD"
}

# RabbitMQ: known to hang indefinitely on this machine past the version
# banner (see native/logs/rabbitmq.log). Started best-effort; do not block
# the rest of the stack on it.
$pids["rabbitmq"] = Start-Native "rabbitmq" "C:\Program Files\RabbitMQ Server\rabbitmq_server-3.13.7\sbin\rabbitmq-server.bat" "" $null @{
    ERLANG_HOME = "C:\erl27"
}

Wait-Port 8080 60 | Out-Null
Save-Pids $pids

Write-Output "Waiting for MinIO/Keycloak before starting Python services..."
Start-Sleep -Seconds 5

# Python services: api + workers, all from the shared venv.
$apiDir = "$root\services\api"
$pyProcs = @{
    "api"                  = "uvicorn app.main:app --host 0.0.0.0 --port 8000"
    "outbox-relay"         = "-m app.workers.outbox"
    "document-worker"      = "-m app.workers.document"
    "agent-worker"         = "-m app.workers.agent"
    "invoice-worker"       = "-m app.workers.invoice_agent"
    "retrieval-api"        = "-m uvicorn app.retrieval_service:app --host 0.0.0.0 --port 8100"
    "retrieval-worker"     = "-m app.workers.retrieval"
    "notification-worker"  = "-m app.workers.notification"
    "alert-worker"         = "-m app.workers.alerts"
    "sanctions-worker"     = "-m app.workers.sanctions"
    "erp-worker"           = "-m app.workers.erp"
}
foreach ($name in $pyProcs.Keys) {
    $pids[$name] = Start-Native $name $venvPy $pyProcs[$name] $apiDir @{}
}

# mock-erp (shares the same venv; strict subset of dependencies).
$pids["mock-erp"] = Start-Native "mock-erp" $venvPy "-m uvicorn app:app --host 0.0.0.0 --port 8090" "$root\services\mock_erp" @{
    ERP_DB_PATH = "$native\mock-erp\erp.sqlite3"
}

Save-Pids $pids

Write-Output ""
Write-Output "Started. Run 'pwsh scripts/run-native.ps1 status' to check ports."
Write-Output "Web app is not started here - run 'npm run dev' from apps/web separately."
Write-Output "RabbitMQ is known to hang on this machine; see native/logs/rabbitmq.log."
