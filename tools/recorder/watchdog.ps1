# Crypto L2 recorder watchdog (owner 2026-11-17). Run every 10 minutes by the scheduled task "QF crypto L2 watchdog".
# Restarts the recorder task "QF crypto L2" when its process is gone, or when no output file under the data folder has
# been written for $StaleMinutes (a hung websocket). Each restart and each failed check is logged to watchdog.log.
# The recorder writes one gzip file per symbol per UTC hour and appends continuously, so a healthy recorder keeps
# LastWriteTime within a few seconds; 10 minutes is far above that and far below the hour.
param(
    [string]$DataDir = "C:\Work\Claude\qf-crypto-data\kraken",
    [string]$Log = "C:\Work\Claude\qf-crypto-data\watchdog.log",
    [string]$Task = "QF crypto L2",
    [int]$StaleMinutes = 10,
    [int]$WarnFreeGB = 10,
    [int]$StopRawFreeGB = 3
)
$ErrorActionPreference = "Stop"
function Write-Log([string]$msg) {
    "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) $msg" | Out-File -FilePath $Log -Append -Encoding utf8
}
try {
    $procs = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -like '*crypto_l2.py*' })
    $latest = Get-ChildItem -Path $DataDir -Recurse -File -Filter *.jsonl.gz -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    $ageMin = if ($latest) { ((Get-Date) - $latest.LastWriteTime).TotalMinutes } else { [double]::PositiveInfinity }

    # Disk guard: raw book messages cost about 0.5 GB a day. Below $StopRawFreeGB free, create NO_RAW so the
    # recorder (on its next start) keeps snapshots and trades but stops raw messages; restart it to apply.
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
    elseif ($ageMin -gt $StaleMinutes) { $reason = ("no write for {0:N1} min (latest {1})" -f $ageMin, $latest.Name) }

    if ($reason) {
        foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Seconds 2
        schtasks /run /tn "$Task" | Out-Null
        Write-Log "restart: $reason"
    }
}
catch {
    Write-Log "check failed: $($_.Exception.Message)"
}
