param(
    [string]$PythonExecutable = "python",
    [int]$Port = 8766
)

$ErrorActionPreference = "Stop"
$sender = Read-Host "Gmail sender address (Enter for Lucasecarpenter@gmail.com)"
if ([string]::IsNullOrWhiteSpace($sender)) {
    $sender = "Lucasecarpenter@gmail.com"
}
$secret = Read-Host "Gmail app password (hidden; not your ordinary password)" -AsSecureString
$names = @(
    "BEACON_SMTP_HOST", "BEACON_SMTP_PORT", "BEACON_SMTP_SECURITY",
    "BEACON_SMTP_FROM", "BEACON_SMTP_USER", "BEACON_SMTP_PASSWORD",
    "BEACON_SMTP_ALLOWED_RECIPIENTS"
)
$prior = @{}
foreach ($name in $names) {
    $prior[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
try {
    $env:BEACON_SMTP_HOST = "smtp.gmail.com"
    $env:BEACON_SMTP_PORT = "587"
    $env:BEACON_SMTP_SECURITY = "starttls"
    $env:BEACON_SMTP_FROM = $sender.Trim()
    $env:BEACON_SMTP_USER = $sender.Trim()
    $env:BEACON_SMTP_PASSWORD = (New-Object System.Net.NetworkCredential("", $secret)).Password
    $env:BEACON_SMTP_ALLOWED_RECIPIENTS = "Lucasecarpenter@gmail.com"
    & $PythonExecutable -B (Join-Path $PSScriptRoot "server.py") --port $Port
    if ($LASTEXITCODE -ne 0) {
        throw "The email-enabled console exited with code $LASTEXITCODE."
    }
} finally {
    foreach ($name in $names) {
        [Environment]::SetEnvironmentVariable($name, $prior[$name], "Process")
    }
    $secret.Dispose()
}
