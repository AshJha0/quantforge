# Crypto L2 recorder watchdog (owner 2026-11-17; liveness reworked 2026-11-18). Run every 10 minutes by the scheduled
# task "QF crypto L2 watchdog". Restarts the recorder task "QF crypto L2" when its process is gone, or when its
# heartbeat file is stale. The recorder writes <DataDir>\..\heartbeat.json every 10 s with the age of its last
# websocket message. Gzip LastWriteTime is NOT a liveness signal: with 100-level books the compressor holds data for
# minutes, and judging by it killed a healthy recorder every 10-20 minutes on 2026-11-17/18.
# Restart is graceful first: create <DataDir>\STOP, wait up to $GraceSeconds for the recorder to close its files and
# exit, and only then force-kill. Each restart and each failed check is logged to watchdog.log.
param(
    [string]$DataDir = "C:\Work\Claude\qf-crypto-data\kraken",
    [string]$Heartbeat = "C:\Work\Claude\qf-crypto-data\heartbeat.json",
    [string]$Log = "C:\Work\Claude\qf-crypto-data\watchdog.log",
    [string]$Task = "QF crypto L2",
    [int]$StaleSeconds = 120,
    [int]$NoMessageSeconds = 300,
    [int]$GraceSeconds = 45,
    [int]$WarnFreeGB = 10,
    [int]$StopRawFreeGB = 3
)
$ErrorActionPreference = "Stop"
function Write-Log([string]$msg) {
    "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) $msg" | Out-File -FilePath $Log -Append -Encoding utf8
}
function Get-Recorder {
    @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -like '*crypto_l2.py*' })
}
try {
    $procs = Get-Recorder
    $hbAge = [double]::PositiveInfinity; $msgAge = $null
    if (Test-Path $Heartbeat) {
        try {
            $hb = Get-Content $Heartbeat -Raw | ConvertFrom-Json
            $hbAge = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds() / 1000.0 - [double]$hb.epoch
            $msgAge = $hb.last_msg_age_s
        } catch { $hbAge = ((Get-Date) - (Get-Item $Heartbeat).LastWriteTime).TotalSeconds }
    }

    # Disk guard: below $StopRawFreeGB free, create NO_RAW so the recorder (on its next start) keeps snapshots and
    # trades but stops raw messages; restart it to apply.
    $drive = (Get-Item $DataDir).PSDrive.Name
    $freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
    $noRaw = Join-Path $DataDir "NO_RAW"
    $reason = $null
    if ($freeGB -lt $StopRawFreeGB -and -not (Test-Path $noRaw)) {
        New-Item -ItemType File -Path $noRaw | Out-Null
        $reason = "disk ${freeGB} GB free: raw messages stopped (NO_RAW)"
    }
    elseif ($freeGB -lt $WarnFreeGB) { Write-Log "warning: disk ${freeGB} GB free" }
    if ($reason) { }
    elseif ($procs.Count -eq 0) { $reason = "no recorder process" }
    elseif ($hbAge -gt $StaleSeconds) { $reason = ("heartbeat stale {0:N0} s" -f $hbAge) }
    elseif ($null -ne $msgAge -and [double]$msgAge -gt $NoMessageSeconds) { $reason = ("no websocket message for {0:N0} s" -f [double]$msgAge) }

    if ($reason) {
        $how = "none running"
        if ($procs.Count -gt 0) {
            New-Item -ItemType File -Path (Join-Path $DataDir "STOP") -Force | Out-Null
            $deadline = (Get-Date).AddSeconds($GraceSeconds)
            while ((Get-Date) -lt $deadline -and (Get-Recorder).Count -gt 0) { Start-Sleep -Seconds 2 }
            $left = Get-Recorder
            if ($left.Count -gt 0) {
                foreach ($p in $left) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
                $how = "FORCE-KILLED after ${GraceSeconds} s grace"
            } else { $how = "stopped gracefully" }
            Remove-Item (Join-Path $DataDir "STOP") -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        schtasks /run /tn "$Task" | Out-Null
        Write-Log "restart: $reason ($how)"
    }
}
catch {
    Write-Log "check failed: $($_.Exception.Message)"
}
