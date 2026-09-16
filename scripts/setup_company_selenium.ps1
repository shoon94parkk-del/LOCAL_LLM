param(
    [Parameter(Mandatory = $true)]
    [string]$GlmUrl
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envPath = Join-Path $root ".env"
$templatePath = Join-Path $root ".env.example"

if (-not (Test-Path $envPath)) {
    Copy-Item $templatePath $envPath
}

function Set-EnvValue {
    param([string]$Key, [string]$Value)
    $content = Get-Content $envPath -Raw
    $pattern = "(?m)^" + [regex]::Escape($Key) + "=.*$"
    $line = "$Key=$Value"
    if ([regex]::IsMatch($content, $pattern)) {
        $content = [regex]::Replace($content, $pattern, $line)
    } else {
        $content = $content.TrimEnd() + "`r`n" + $line + "`r`n"
    }
    Set-Content -Path $envPath -Value $content -Encoding UTF8
}

Set-EnvValue "LOCAL_LLM_GLM_MODE" "selenium"
Set-EnvValue "LOCAL_LLM_GLM_URL" $GlmUrl
Set-EnvValue "LOCAL_LLM_GLM_TIMEOUT_MS" "1800000"
Set-EnvValue "LOCAL_LLM_EMBEDDING_MODE" "disabled"

$memoryFolder = Join-Path $root "data\workspace\memory"
New-Item -ItemType Directory -Path $memoryFolder -Force | Out-Null

Write-Host "Company Selenium mode configured." -ForegroundColor Green
Write-Host "  .env: $envPath"
Write-Host "  GLM URL: $GlmUrl"
Write-Host "  Memory files: $memoryFolder"
Write-Host "Run: uvicorn app.main:app --host 127.0.0.1 --port 8000"
