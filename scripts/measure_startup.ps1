param(
    [Parameter(Mandatory = $true)] [string] $OldExe,
    [Parameter(Mandatory = $true)] [string] $NewExe,
    [ValidateRange(1, 20)] [int] $Runs = 5,
    [ValidateRange(1, 120)] [int] $TimeoutSeconds = 60
)

$oldPath = (Resolve-Path -LiteralPath $OldExe).Path
$newPath = (Resolve-Path -LiteralPath $NewExe).Path
if (Get-Process | Where-Object { $_.MainWindowTitle -like 'PicView*' }) {
    throw 'Close all PicView windows before measuring startup.'
}

function Measure-Launch([string] $label, [string] $path, [int] $iteration) {
    $startedAt = Get-Date
    $timer = [System.Diagnostics.Stopwatch]::StartNew()
    $process = Start-Process -FilePath $path -WorkingDirectory (Split-Path -Parent $path) -PassThru
    $visible = $null
    try {
        while ($timer.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
            $visible = Get-Process | Where-Object {
                $_.StartTime -ge $startedAt.AddSeconds(-1) -and $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like 'PicView*'
            } | Select-Object -First 1
            if ($visible) { break }
            Start-Sleep -Milliseconds 50
        }
        if (-not $visible) { throw "PicView window did not appear within $TimeoutSeconds seconds: $path" }
        [pscustomobject]@{ Variant = $label; Run = $iteration; WindowVisibleSeconds = [math]::Round($timer.Elapsed.TotalSeconds, 3) }
    }
    finally {
        if ($visible) { $null = $visible.CloseMainWindow() }
        Start-Sleep -Milliseconds 500
        Get-Process | Where-Object {
            $_.ProcessName -like 'PicView*' -and $_.StartTime -ge $startedAt.AddSeconds(-1)
        } | Stop-Process -Force -ErrorAction SilentlyContinue
        $process.Dispose()
    }
}

for ($iteration = 1; $iteration -le $Runs; $iteration++) {
    $pair = if ($iteration % 2) { @(@('onefile', $oldPath), @('onedir', $newPath)) } else { @(@('onedir', $newPath), @('onefile', $oldPath)) }
    foreach ($variant in $pair) {
        Measure-Launch $variant[0] $variant[1] $iteration
    }
}
