<#
.SYNOPSIS
    Emare Security OS RMM Agent — Windows Service Kurulum Scripti
.DESCRIPTION
    Agent'ı Windows Service olarak kurar, yapılandırır ve başlatır.
    Yönetici (Administrator) olarak çalıştırılmalıdır.
.NOTES
    Emre — Emare Cloud | Emare Security OS RMM
#>

#Requires -RunAsAdministrator
#Requires -Version 5.1

param(
    [Parameter(Mandatory=$true)]
    [string]$ServerUrl,

    [ValidateSet("Install","Uninstall","Status","Start","Stop","Restart")]
    [string]$Action = "Install"
)

$ServiceName = "EmareRMMAgent"
$DisplayName = "Emare RMM Agent"
$Description = "Emare Security OS Uzaktan İzleme ve Yönetim Agent'ı"
$InstallDir  = "$env:ProgramData\EmareAgent"
$ScriptPath  = "$InstallDir\EmareAgent.ps1"
$WrapperPath = "$InstallDir\AgentService.ps1"
$TaskName    = "EmareRMMAgentTask"

function Install-Agent {
    Write-Host ""
    Write-Host "╔══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║   Emare Security OS RMM Agent Kurulumu           ║" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""

    # 1. Dizin oluştur
    Write-Host "[1/5] Kurulum dizini olusturuluyor..." -ForegroundColor Yellow
    if (-not (Test-Path $InstallDir)) {
        New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    }

    # 2. Agent scriptini kopyala
    Write-Host "[2/5] Agent dosyalari kopyalaniyor..." -ForegroundColor Yellow
    $agentSource = Join-Path (Split-Path $MyInvocation.ScriptName -Parent) "EmareAgent.ps1"
    if (-not (Test-Path $agentSource)) {
        $agentSource = Join-Path $PSScriptRoot "EmareAgent.ps1"
    }
    if (-not (Test-Path $agentSource)) {
        Write-Host "HATA: EmareAgent.ps1 bulunamadi! Ayni klasorde olmali." -ForegroundColor Red
        exit 1
    }
    Copy-Item $agentSource $ScriptPath -Force

    # 3. Yapılandırma dosyası
    Write-Host "[3/5] Yapilandirma olusturuluyor..." -ForegroundColor Yellow
    $config = @{
        ServerUrl      = $ServerUrl
        HeartbeatSec   = 60
        TaskPollSec    = 30
        DeepCollectSec = 300
        TrustAllCerts  = $false
        Version        = "1.0.0"
    }
    $config | ConvertTo-Json | Set-Content "$InstallDir\config.json" -Encoding UTF8

    # 4. Scheduled Task olarak kur (Windows Service alternatifi — daha basit ve güvenilir)
    Write-Host "[4/5] Windows Zamanlanmis Gorev olusturuluyor..." -ForegroundColor Yellow

    # Mevcut görevi sil
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -Server `"$ServerUrl`""

    $taskTrigger = New-ScheduledTaskTrigger -AtStartup
    $taskSettings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Days 365)

    $taskPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $taskAction `
        -Trigger $taskTrigger `
        -Settings $taskSettings `
        -Principal $taskPrincipal `
        -Description $Description `
        -Force | Out-Null

    # 5. Hemen başlat
    Write-Host "[5/5] Agent baslatiliyor..." -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName

    Write-Host ""
    Write-Host "════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host " Kurulum tamamlandi!" -ForegroundColor Green
    Write-Host " Sunucu:  $ServerUrl" -ForegroundColor Green
    Write-Host " Dizin:   $InstallDir" -ForegroundColor Green
    Write-Host " Gorev:   $TaskName" -ForegroundColor Green
    Write-Host " Log:     $InstallDir\agent.log" -ForegroundColor Green
    Write-Host "════════════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Write-Host "Durumu kontrol etmek icin:" -ForegroundColor Cyan
    Write-Host "  .\Install-EmareAgent.ps1 -ServerUrl $ServerUrl -Action Status" -ForegroundColor White
    Write-Host ""
}

function Uninstall-Agent {
    Write-Host "Agent kaldiriliyor..." -ForegroundColor Yellow

    # Zamanlanmış görevi durdur ve sil
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    # Çalışan PowerShell sürecini durdur
    Get-Process powershell -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*EmareAgent*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue

    Write-Host "Agent kaldirildi." -ForegroundColor Green
    Write-Host "Not: $InstallDir klasoru korundu (log ve key dosyalari)." -ForegroundColor Yellow
    Write-Host "Tamamen silmek icin: Remove-Item -Recurse -Force '$InstallDir'" -ForegroundColor Gray
}

function Get-AgentStatus {
    Write-Host ""
    Write-Host "Emare Security OS RMM Agent Durumu" -ForegroundColor Cyan
    Write-Host "────────────────────────────────────" -ForegroundColor Gray

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($task) {
        $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
        Write-Host "Gorev:        $($task.State)" -ForegroundColor $(if ($task.State -eq "Running") { "Green" } else { "Red" })
        Write-Host "Son calisma:  $($taskInfo.LastRunTime)"
        Write-Host "Sonuc kodu:   $($taskInfo.LastTaskResult)"
    } else {
        Write-Host "Gorev:        Kurulu degil" -ForegroundColor Red
    }

    if (Test-Path "$InstallDir\config.json") {
        $cfg = Get-Content "$InstallDir\config.json" -Raw | ConvertFrom-Json
        Write-Host "Sunucu:       $($cfg.ServerUrl)" -ForegroundColor White
    }

    if (Test-Path "$InstallDir\agent.key") {
        $key = Get-Content "$InstallDir\agent.key" -Raw | ConvertFrom-Json
        Write-Host "Device ID:    $($key.device_id)" -ForegroundColor White
        Write-Host "Kayit tarihi: $($key.registered_at)" -ForegroundColor White
    } else {
        Write-Host "Kayit:        Kayitli degil" -ForegroundColor Yellow
    }

    if (Test-Path "$InstallDir\agent.log") {
        Write-Host ""
        Write-Host "Son 10 log satiri:" -ForegroundColor Gray
        Get-Content "$InstallDir\agent.log" -Tail 10
    }
    Write-Host ""
}

function Start-Agent {
    Start-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    Write-Host "Agent baslatildi." -ForegroundColor Green
}

function Stop-Agent {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Get-Process powershell -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*EmareAgent*" } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "Agent durduruldu." -ForegroundColor Yellow
}

# Ana çalıştırma
switch ($Action) {
    "Install"   { Install-Agent }
    "Uninstall" { Uninstall-Agent }
    "Status"    { Get-AgentStatus }
    "Start"     { Start-Agent }
    "Stop"      { Stop-Agent }
    "Restart"   { Stop-Agent; Start-Sleep -Seconds 2; Start-Agent }
}
