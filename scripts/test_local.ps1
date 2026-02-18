# On-Call Copilot – PowerShell local test script
# Usage: .\scripts\test_local.ps1 [-Demo 1|2|3]
param(
    [ValidateSet("1","2","3")]
    [string]$Demo = "1"
)

$base = "http://localhost:8088"

$files = @{
    "1" = "scripts/demos/demo_1_simple_alert.json"
    "2" = "scripts/demos/demo_2_multi_signal.json"
    "3" = "scripts/demos/demo_3_post_incident.json"
}

$file = $files[$Demo]
Write-Host "==> Sending $file to $base/responses ..."

$body = Get-Content -Raw -Path $file
$response = Invoke-RestMethod -Uri "$base/responses" -Method Post -ContentType "application/json" -Body $body
$response | ConvertTo-Json -Depth 10

Write-Host "`n==> Health check:"
Invoke-RestMethod -Uri "$base/health" | ConvertTo-Json
