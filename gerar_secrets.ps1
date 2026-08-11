# gerar_secrets.ps1 - monta .streamlit\secrets.toml a partir do token ADC do gcloud
# sem imprimir o token na tela. Rode UMA vez por app (ou quando o token mudar).
#   .\gerar_secrets.ps1
# Se o Windows bloquear:
#   powershell -ExecutionPolicy Bypass -File .\gerar_secrets.ps1

$ErrorActionPreference = "Stop"

$adc = Join-Path $env:APPDATA "gcloud\application_default_credentials.json"
if (-not (Test-Path $adc)) {
    Write-Error "ADC nao encontrado. Rode primeiro: gcloud auth application-default login"
    exit 1
}

$c = Get-Content $adc -Raw | ConvertFrom-Json

$project = "dm-mottu-aluguel"   # ajuste se o app usar outro projeto

# Preserva credenciais SSO ja existentes (username/password) se houver secrets.toml
$ssoUser = ""
$ssoPass = ""
$secretsPath = ".streamlit\secrets.toml"
if (Test-Path $secretsPath) {
    foreach ($line in Get-Content $secretsPath) {
        if ($line -match '^\s*username\s*=\s*"(.*)"\s*$') { $ssoUser = $Matches[1] }
        if ($line -match '^\s*password\s*=\s*"(.*)"\s*$') { $ssoPass = $Matches[1] }
    }
}

New-Item -ItemType Directory -Force -Path ".streamlit" | Out-Null

$sb = New-Object System.Text.StringBuilder
[void]$sb.AppendLine("# Credenciais Mottu SSO (API tempo real, password grant)")
[void]$sb.AppendLine("username = `"$ssoUser`"")
[void]$sb.AppendLine("password = `"$ssoPass`"")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("gcp_project_id = `"$project`"")
[void]$sb.AppendLine("")
[void]$sb.AppendLine("[gcp_service_account]")
[void]$sb.AppendLine("type = `"authorized_user`"")
[void]$sb.AppendLine("client_id = `"$($c.client_id)`"")
[void]$sb.AppendLine("client_secret = `"$($c.client_secret)`"")
[void]$sb.AppendLine("refresh_token = `"$($c.refresh_token)`"")

[System.IO.File]::WriteAllText((Resolve-Path ".streamlit").Path + "\secrets.toml", $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

Write-Host "OK: .streamlit\secrets.toml gerado (token NAO impresso)."
if ($ssoUser -eq "" -or $ssoPass -eq "") {
    Write-Host "ATENCAO: username/password SSO vazios - preencha manualmente para as colunas de API em tempo real."
}
