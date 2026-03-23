<#
.SYNOPSIS
    Emare Security OS RMM Agent — Windows Deep Monitoring Agent
.DESCRIPTION
    Windows üzerinde çalışan kapsamlı izleme agent'ı.
    CPU, RAM, Disk, Network, GPU, Süreçler, Servisler, Güvenlik Olayları,
    Yüklü Yazılımlar, Açık Portlar, Kullanıcı Oturumları, Sıcaklık ve daha fazlası.
    Windows Service olarak kurulabilir.
.NOTES
    Emre — Emare Cloud | Emare Security OS RMM
    v1.0.0 | 2026-03-23
#>

#Requires -Version 5.1

# ═══════════════════════════════════════════════════════════
#  YAPILANDIRMA
# ═══════════════════════════════════════════════════════════

$Script:Config = @{
    ServerUrl       = "https://localhost:5555"
    AgentKeyFile    = "$env:ProgramData\EmareAgent\agent.key"
    ConfigFile      = "$env:ProgramData\EmareAgent\config.json"
    LogFile         = "$env:ProgramData\EmareAgent\agent.log"
    HeartbeatSec    = 60
    TaskPollSec     = 30
    DeepCollectSec  = 300      # 5 dk — derin telemetri
    MaxLogSizeMB    = 10
    TrustAllCerts   = $false   # Self-signed sertifika için $true
    Version         = "1.0.0"
}

# ═══════════════════════════════════════════════════════════
#  SSL / TLS AYARLARI
# ═══════════════════════════════════════════════════════════

[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

# ═══════════════════════════════════════════════════════════
#  LOG SİSTEMİ
# ═══════════════════════════════════════════════════════════

function Write-AgentLog {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"

    # Log dosyası rotasyonu
    $logDir = Split-Path $Script:Config.LogFile -Parent
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

    if (Test-Path $Script:Config.LogFile) {
        $size = (Get-Item $Script:Config.LogFile).Length / 1MB
        if ($size -gt $Script:Config.MaxLogSizeMB) {
            $archivePath = $Script:Config.LogFile -replace '\.log$', "_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
            Move-Item $Script:Config.LogFile $archivePath -Force
        }
    }
    Add-Content -Path $Script:Config.LogFile -Value $line -Encoding UTF8
    if ($Level -eq "ERROR") { Write-Host $line -ForegroundColor Red }
    elseif ($Level -eq "WARN") { Write-Host $line -ForegroundColor Yellow }
    else { Write-Host $line }
}

# ═══════════════════════════════════════════════════════════
#  HTTP İSTEK YARDIMCILARI
# ═══════════════════════════════════════════════════════════

function Invoke-AgentRequest {
    param(
        [string]$Endpoint,
        [string]$Method = "GET",
        [hashtable]$Body = $null
    )
    $url = "$($Script:Config.ServerUrl)/api/rmm/$Endpoint"
    $headers = @{ "Content-Type" = "application/json"; "X-Requested-With" = "XMLHttpRequest" }

    if ($Script:AgentKey) {
        $headers["X-Agent-Key"] = $Script:AgentKey
    }

    $params = @{
        Uri             = $url
        Method          = $Method
        Headers         = $headers
        ContentType     = "application/json"
        UseBasicParsing = $true
        TimeoutSec      = 30
        ErrorAction     = "Stop"
    }
    if ($Body) {
        $params["Body"] = ($Body | ConvertTo-Json -Depth 10 -Compress)
    }

    try {
        $resp = Invoke-RestMethod @params
        return $resp
    }
    catch {
        Write-AgentLog "HTTP hata [$Method $Endpoint]: $($_.Exception.Message)" "ERROR"
        return $null
    }
}

# ═══════════════════════════════════════════════════════════
#  KAYIT (REGISTRATION)
# ═══════════════════════════════════════════════════════════

function Register-Agent {
    Write-AgentLog "Sunucuya kayit baslatiliyor..."

    $osInfo = Get-CimInstance Win32_OperatingSystem
    $netAdapter = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -ne "127.0.0.1" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -First 1

    $body = @{
        hostname      = $env:COMPUTERNAME
        os_type       = "windows"
        os_version    = "$($osInfo.Caption) $($osInfo.Version)"
        ip_address    = if ($netAdapter) { $netAdapter.IPAddress } else { "0.0.0.0" }
        agent_version = $Script:Config.Version
        tags          = @("windows", "auto-registered")
    }

    $result = Invoke-AgentRequest -Endpoint "agent/register" -Method "POST" -Body $body

    if ($result -and $result.success) {
        $Script:AgentKey = $result.agent_key
        $Script:DeviceId = $result.id

        # Agent key'i kaydet
        $keyDir = Split-Path $Script:Config.AgentKeyFile -Parent
        if (-not (Test-Path $keyDir)) { New-Item -ItemType Directory -Path $keyDir -Force | Out-Null }
        @{ agent_key = $Script:AgentKey; device_id = $Script:DeviceId; registered_at = (Get-Date -Format "o") } |
            ConvertTo-Json | Set-Content -Path $Script:Config.AgentKeyFile -Encoding UTF8

        Write-AgentLog "Kayit basarili! DeviceID=$($Script:DeviceId)"
        return $true
    }
    Write-AgentLog "Kayit basarisiz!" "ERROR"
    return $false
}

function Load-AgentKey {
    if (Test-Path $Script:Config.AgentKeyFile) {
        try {
            $data = Get-Content $Script:Config.AgentKeyFile -Raw | ConvertFrom-Json
            $Script:AgentKey = $data.agent_key
            $Script:DeviceId = $data.device_id
            Write-AgentLog "Agent key yuklendi: DeviceID=$($Script:DeviceId)"
            return $true
        }
        catch {
            Write-AgentLog "Key dosyasi bozuk, yeniden kayit gerekiyor" "WARN"
        }
    }
    return $false
}

# ═══════════════════════════════════════════════════════════
#  DERİN METRİK TOPLAYICILAR
# ═══════════════════════════════════════════════════════════

function Get-CpuMetrics {
    try {
        $cpu = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
        $cpuInfo = Get-CimInstance Win32_Processor | Select-Object -First 1
        return @{
            usage_percent = [math]::Round($cpu.Average, 1)
            name          = $cpuInfo.Name.Trim()
            cores         = $cpuInfo.NumberOfCores
            threads       = $cpuInfo.NumberOfLogicalProcessors
            max_clock_mhz = $cpuInfo.MaxClockSpeed
            architecture  = switch ($cpuInfo.Architecture) {
                0 { "x86" }; 9 { "x64" }; 12 { "ARM64" }; default { "unknown" }
            }
        }
    }
    catch {
        return @{ usage_percent = 0; error = $_.Exception.Message }
    }
}

function Get-MemoryMetrics {
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $totalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
        $freeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
        $usedGB = [math]::Round($totalGB - $freeGB, 2)
        $percent = [math]::Round(($usedGB / $totalGB) * 100, 1)

        $pageFile = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue |
            Select-Object -First 1

        return @{
            usage_percent   = $percent
            total_gb        = $totalGB
            used_gb         = $usedGB
            free_gb         = $freeGB
            page_file_gb    = if ($pageFile) { [math]::Round($pageFile.AllocatedBaseSize / 1024, 2) } else { 0 }
            page_file_usage = if ($pageFile) { [math]::Round($pageFile.CurrentUsage / $pageFile.AllocatedBaseSize * 100, 1) } else { 0 }
        }
    }
    catch {
        return @{ usage_percent = 0; error = $_.Exception.Message }
    }
}

function Get-DiskMetrics {
    try {
        $disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
            ForEach-Object {
                $total = [math]::Round($_.Size / 1GB, 2)
                $free = [math]::Round($_.FreeSpace / 1GB, 2)
                $used = [math]::Round($total - $free, 2)
                @{
                    drive   = $_.DeviceID
                    label   = $_.VolumeName
                    total_gb = $total
                    used_gb  = $used
                    free_gb  = $free
                    percent  = if ($total -gt 0) { [math]::Round(($used / $total) * 100, 1) } else { 0 }
                    fs_type  = $_.FileSystem
                }
            }

        $primary = $disks | Where-Object { $_.drive -eq "C:" } | Select-Object -First 1
        $overallPercent = if ($primary) { $primary.percent } else {
            ($disks | Measure-Object -Property percent -Average).Average
        }

        # Disk I/O
        $diskIO = @{}
        try {
            $perfCounters = Get-CimInstance Win32_PerfFormattedData_PerfDisk_PhysicalDisk |
                Where-Object { $_.Name -ne "_Total" } | Select-Object -First 2
            foreach ($d in $perfCounters) {
                $diskIO[$d.Name] = @{
                    read_bytes_sec  = $d.DiskReadBytesPerSec
                    write_bytes_sec = $d.DiskWriteBytesPerSec
                    avg_queue       = $d.AvgDiskQueueLength
                    iops_read       = $d.DiskReadsPerSec
                    iops_write      = $d.DiskWritesPerSec
                }
            }
        } catch {}

        return @{
            usage_percent = [math]::Round($overallPercent, 1)
            volumes       = $disks
            io            = $diskIO
        }
    }
    catch {
        return @{ usage_percent = 0; error = $_.Exception.Message }
    }
}

function Get-NetworkMetrics {
    try {
        $adapters = Get-NetAdapter -Physical -ErrorAction SilentlyContinue |
            Where-Object { $_.Status -eq "Up" }

        $totalIn = 0; $totalOut = 0
        $interfaces = @()

        foreach ($adapter in $adapters) {
            $stats = Get-NetAdapterStatistics -Name $adapter.Name -ErrorAction SilentlyContinue
            if ($stats) {
                $totalIn += $stats.ReceivedBytes
                $totalOut += $stats.SentBytes
                $ipAddr = (Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
                    Select-Object -First 1).IPAddress

                $interfaces += @{
                    name       = $adapter.Name
                    mac        = $adapter.MacAddress
                    speed_mbps = [math]::Round($adapter.LinkSpeed.Replace(" Gbps","000").Replace(" Mbps","").Replace(" Kbps","") / 1, 0)
                    ip_address = $ipAddr
                    rx_bytes   = $stats.ReceivedBytes
                    tx_bytes   = $stats.SentBytes
                    rx_errors  = $stats.ReceivedPacketErrors
                    tx_errors  = $stats.OutboundPacketErrors
                    status     = $adapter.Status
                }
            }
        }

        # DNS sunucuları
        $dns = Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.ServerAddresses } |
            Select-Object -ExpandProperty ServerAddresses -Unique | Select-Object -First 4

        # Aktif bağlantılar
        $connStats = @{ total = 0; established = 0; listen = 0; time_wait = 0; close_wait = 0 }
        try {
            $conns = Get-NetTCPConnection -ErrorAction SilentlyContinue
            $connStats.total = $conns.Count
            $connStats.established = ($conns | Where-Object State -eq "Established").Count
            $connStats.listen = ($conns | Where-Object State -eq "Listen").Count
            $connStats.time_wait = ($conns | Where-Object State -eq "TimeWait").Count
            $connStats.close_wait = ($conns | Where-Object State -eq "CloseWait").Count
        } catch {}

        return @{
            total_rx_bytes  = $totalIn
            total_tx_bytes  = $totalOut
            interfaces      = $interfaces
            dns_servers     = @($dns)
            connections     = $connStats
        }
    }
    catch {
        return @{ total_rx_bytes = 0; total_tx_bytes = 0; error = $_.Exception.Message }
    }
}

function Get-GpuMetrics {
    try {
        $gpus = @()
        # NVIDIA GPU
        $nvsmi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
        if ($nvsmi) {
            $nvOutput = & nvidia-smi --query-gpu=name,temperature.gpu,utilization.gpu,utilization.memory,memory.total,memory.used,memory.free,fan.speed,power.draw --format=csv,noheader,nounits 2>$null
            if ($nvOutput) {
                foreach ($line in $nvOutput) {
                    $parts = $line -split ",\s*"
                    if ($parts.Count -ge 9) {
                        $gpus += @{
                            name          = $parts[0].Trim()
                            vendor        = "NVIDIA"
                            temp_c        = [int]$parts[1]
                            gpu_usage     = [int]$parts[2]
                            mem_usage     = [int]$parts[3]
                            mem_total_mb  = [int]$parts[4]
                            mem_used_mb   = [int]$parts[5]
                            mem_free_mb   = [int]$parts[6]
                            fan_percent   = [int]$parts[7]
                            power_watts   = [double]$parts[8]
                        }
                    }
                }
            }
        }

        # WMI fallback (Intel/AMD/generic)
        if (-not $gpus) {
            $wmiGpus = Get-CimInstance Win32_VideoController
            foreach ($g in $wmiGpus) {
                $gpus += @{
                    name         = $g.Name
                    vendor       = $g.AdapterCompatibility
                    driver       = $g.DriverVersion
                    ram_mb       = [math]::Round($g.AdapterRAM / 1MB, 0)
                    resolution   = "$($g.CurrentHorizontalResolution)x$($g.CurrentVerticalResolution)"
                    refresh_hz   = $g.CurrentRefreshRate
                }
            }
        }

        return @{ gpus = $gpus }
    }
    catch {
        return @{ gpus = @(); error = $_.Exception.Message }
    }
}

function Get-SystemInfo {
    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $cs = Get-CimInstance Win32_ComputerSystem
        $bios = Get-CimInstance Win32_BIOS

        $uptime = (Get-Date) - $os.LastBootUpTime

        return @{
            hostname      = $env:COMPUTERNAME
            domain        = $cs.Domain
            os_name       = $os.Caption
            os_version    = $os.Version
            os_build      = $os.BuildNumber
            os_arch       = $os.OSArchitecture
            manufacturer  = $cs.Manufacturer
            model         = $cs.Model
            serial        = $bios.SerialNumber
            bios_version  = $bios.SMBIOSBIOSVersion
            uptime_hours  = [math]::Round($uptime.TotalHours, 1)
            uptime_text   = "$($uptime.Days)g $($uptime.Hours)s $($uptime.Minutes)dk"
            install_date  = $os.InstallDate.ToString("yyyy-MM-dd")
            timezone      = (Get-TimeZone).Id
            locale        = (Get-Culture).Name
            last_boot     = $os.LastBootUpTime.ToString("yyyy-MM-dd HH:mm:ss")
            user_count    = (Get-CimInstance Win32_UserAccount -Filter "LocalAccount=True" -ErrorAction SilentlyContinue).Count
        }
    }
    catch {
        return @{ hostname = $env:COMPUTERNAME; error = $_.Exception.Message }
    }
}

function Get-ProcessList {
    try {
        $procs = Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 25 |
            ForEach-Object {
                @{
                    name       = $_.ProcessName
                    pid        = $_.Id
                    cpu_sec    = [math]::Round($_.CPU, 2)
                    ram_mb     = [math]::Round($_.WorkingSet64 / 1MB, 1)
                    threads    = $_.Threads.Count
                    handles    = $_.HandleCount
                    start_time = if ($_.StartTime) { $_.StartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "" }
                    path       = try { $_.Path } catch { "" }
                }
            }
        return @{ processes = $procs; total_count = (Get-Process).Count }
    }
    catch {
        return @{ processes = @(); error = $_.Exception.Message }
    }
}

function Get-ServiceStatus {
    try {
        $services = Get-Service | ForEach-Object {
            @{
                name         = $_.Name
                display_name = $_.DisplayName
                status       = $_.Status.ToString()
                start_type   = $_.StartType.ToString()
            }
        }

        $running = ($services | Where-Object { $_.status -eq "Running" }).Count
        $stopped = ($services | Where-Object { $_.status -eq "Stopped" }).Count
        $critical = @("wuauserv","EventLog","Winmgmt","RpcSs","Dhcp","Dnscache","LanmanServer","Spooler","W32Time","WinDefend")
        $critStatus = $services | Where-Object { $critical -contains $_.name }

        return @{
            total         = $services.Count
            running       = $running
            stopped       = $stopped
            critical      = $critStatus
            all_services  = $services
        }
    }
    catch {
        return @{ total = 0; error = $_.Exception.Message }
    }
}

function Get-InstalledSoftware {
    try {
        $paths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
        )

        $apps = $paths | ForEach-Object { Get-ItemProperty $_ -ErrorAction SilentlyContinue } |
            Where-Object { $_.DisplayName } |
            Sort-Object DisplayName -Unique |
            ForEach-Object {
                @{
                    name        = $_.DisplayName
                    version     = $_.DisplayVersion
                    publisher   = $_.Publisher
                    install_date = $_.InstallDate
                    size_mb     = if ($_.EstimatedSize) { [math]::Round($_.EstimatedSize / 1024, 1) } else { 0 }
                }
            }

        return @{ count = $apps.Count; software = $apps }
    }
    catch {
        return @{ count = 0; error = $_.Exception.Message }
    }
}

function Get-SecurityStatus {
    try {
        $result = @{
            firewall     = @{}
            antivirus    = @{}
            updates      = @{}
            users        = @()
            shares       = @()
            auto_login   = $false
            rdp_enabled  = $false
            uac_enabled  = $true
        }

        # Windows Firewall
        try {
            $fwProfiles = Get-NetFirewallProfile -ErrorAction SilentlyContinue
            $result.firewall = @{
                domain  = ($fwProfiles | Where-Object Name -eq "Domain").Enabled
                private = ($fwProfiles | Where-Object Name -eq "Private").Enabled
                public  = ($fwProfiles | Where-Object Name -eq "Public").Enabled
            }
        } catch {}

        # Antivirus (Windows Security Center)
        try {
            $av = Get-CimInstance -Namespace "root/SecurityCenter2" -ClassName AntiVirusProduct -ErrorAction SilentlyContinue
            if ($av) {
                $result.antivirus = @{
                    products = @($av | ForEach-Object {
                        @{
                            name   = $_.displayName
                            state  = $_.productState
                            active = ($_.productState -band 0x1000) -ne 0
                        }
                    })
                }
            }
        } catch {}

        # Windows Update
        try {
            $hotfixes = Get-HotFix -ErrorAction SilentlyContinue | Sort-Object InstalledOn -Descending | Select-Object -First 10
            $result.updates = @{
                last_updates = @($hotfixes | ForEach-Object {
                    @{
                        id           = $_.HotFixID
                        description  = $_.Description
                        installed_on = if ($_.InstalledOn) { $_.InstalledOn.ToString("yyyy-MM-dd") } else { "" }
                    }
                })
                total_count = (Get-HotFix -ErrorAction SilentlyContinue).Count
            }
        } catch {}

        # Yerel kullanıcılar
        try {
            $result.users = @(Get-LocalUser -ErrorAction SilentlyContinue | ForEach-Object {
                @{
                    name         = $_.Name
                    enabled      = $_.Enabled
                    last_logon   = if ($_.LastLogon) { $_.LastLogon.ToString("yyyy-MM-dd HH:mm:ss") } else { "" }
                    password_set = if ($_.PasswordLastSet) { $_.PasswordLastSet.ToString("yyyy-MM-dd") } else { "Hiç" }
                    admin        = (Get-LocalGroupMember -Group "Administrators" -ErrorAction SilentlyContinue |
                                   Where-Object Name -like "*\$($_.Name)").Count -gt 0
                }
            })
        } catch {}

        # Paylaşımlar
        try {
            $result.shares = @(Get-SmbShare -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notlike "*$" } |
                ForEach-Object { @{ name = $_.Name; path = $_.Path; description = $_.Description } })
        } catch {}

        # RDP kontrolü
        try {
            $rdpReg = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server" -Name "fDenyTSConnections" -ErrorAction SilentlyContinue
            $result.rdp_enabled = $rdpReg.fDenyTSConnections -eq 0
        } catch {}

        # Auto-login kontrolü
        try {
            $autoLogin = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" -Name "AutoAdminLogon" -ErrorAction SilentlyContinue
            $result.auto_login = $autoLogin.AutoAdminLogon -eq "1"
        } catch {}

        # UAC kontrolü
        try {
            $uac = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" -Name "EnableLUA" -ErrorAction SilentlyContinue
            $result.uac_enabled = $uac.EnableLUA -eq 1
        } catch {}

        return $result
    }
    catch {
        return @{ error = $_.Exception.Message }
    }
}

function Get-EventLogSummary {
    try {
        $last24h = (Get-Date).AddHours(-24)

        $security = @{ errors = 0; warnings = 0; critical = 0; recent = @() }
        $system = @{ errors = 0; warnings = 0; critical = 0; recent = @() }
        $application = @{ errors = 0; warnings = 0; critical = 0; recent = @() }

        # System log
        try {
            $sysEvents = Get-WinEvent -FilterHashtable @{LogName="System"; StartTime=$last24h; Level=@(1,2,3)} -MaxEvents 50 -ErrorAction SilentlyContinue
            if ($sysEvents) {
                $system.critical = ($sysEvents | Where-Object Level -eq 1).Count
                $system.errors = ($sysEvents | Where-Object Level -eq 2).Count
                $system.warnings = ($sysEvents | Where-Object Level -eq 3).Count
                $system.recent = @($sysEvents | Select-Object -First 10 | ForEach-Object {
                    @{
                        id      = $_.Id
                        level   = $_.LevelDisplayName
                        source  = $_.ProviderName
                        message = ($_.Message -split "`n")[0]
                        time    = $_.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                    }
                })
            }
        } catch {}

        # Security log (oturum olayları)
        try {
            $secEvents = Get-WinEvent -FilterHashtable @{LogName="Security"; StartTime=$last24h; Id=@(4624,4625,4634,4648,4672)} -MaxEvents 30 -ErrorAction SilentlyContinue
            if ($secEvents) {
                $security.errors = ($secEvents | Where-Object Id -eq 4625).Count  # başarısız oturum
                $security.warnings = ($secEvents | Where-Object Id -eq 4648).Count  # explicit credential
                $security.recent = @($secEvents | Select-Object -First 10 | ForEach-Object {
                    @{
                        id      = $_.Id
                        type    = switch($_.Id) { 4624 {"Oturum Acildi"} 4625 {"Basarisiz Oturum"} 4634 {"Oturum Kapandi"} 4648 {"Explicit Credential"} 4672 {"Admin Oturum"} default {"Diger"} }
                        time    = $_.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                        message = ($_.Message -split "`n")[0]
                    }
                })
            }
        } catch {}

        # Application log
        try {
            $appEvents = Get-WinEvent -FilterHashtable @{LogName="Application"; StartTime=$last24h; Level=@(1,2,3)} -MaxEvents 30 -ErrorAction SilentlyContinue
            if ($appEvents) {
                $application.critical = ($appEvents | Where-Object Level -eq 1).Count
                $application.errors = ($appEvents | Where-Object Level -eq 2).Count
                $application.warnings = ($appEvents | Where-Object Level -eq 3).Count
                $application.recent = @($appEvents | Select-Object -First 10 | ForEach-Object {
                    @{
                        id      = $_.Id
                        level   = $_.LevelDisplayName
                        source  = $_.ProviderName
                        message = ($_.Message -split "`n")[0]
                        time    = $_.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                    }
                })
            }
        } catch {}

        return @{
            system      = $system
            security    = $security
            application = $application
        }
    }
    catch {
        return @{ error = $_.Exception.Message }
    }
}

function Get-OpenPorts {
    try {
        $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Sort-Object LocalPort |
            ForEach-Object {
                $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                @{
                    port           = $_.LocalPort
                    address        = $_.LocalAddress
                    protocol       = "TCP"
                    pid            = $_.OwningProcess
                    process_name   = if ($proc) { $proc.ProcessName } else { "?" }
                }
            }

        $udpListeners = Get-NetUDPEndpoint -ErrorAction SilentlyContinue |
            ForEach-Object {
                $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
                @{
                    port         = $_.LocalPort
                    address      = $_.LocalAddress
                    protocol     = "UDP"
                    pid          = $_.OwningProcess
                    process_name = if ($proc) { $proc.ProcessName } else { "?" }
                }
            }

        $all = @($listeners) + @($udpListeners) | Sort-Object { $_.port }

        # Bilinen riskli portlar
        $risky = @(21,23,25,135,137,138,139,445,1433,1434,3306,3389,5900,5985,8080)
        $riskyOpen = $all | Where-Object { $risky -contains $_.port }

        return @{
            total      = $all.Count
            tcp_count  = $listeners.Count
            udp_count  = $udpListeners.Count
            ports      = $all
            risky_open = $riskyOpen
        }
    }
    catch {
        return @{ total = 0; error = $_.Exception.Message }
    }
}

function Get-UserSessions {
    try {
        $sessions = @()
        try {
            $queryOutput = query user 2>$null
            if ($queryOutput) {
                foreach ($line in ($queryOutput | Select-Object -Skip 1)) {
                    if ($line -match '^\s*>?(\S+)\s+(\S+)\s+(\d+)\s+(\S+)\s+(.+)$') {
                        $sessions += @{
                            username   = $Matches[1]
                            session    = $Matches[2]
                            id         = [int]$Matches[3]
                            state      = $Matches[4]
                            idle_time  = $Matches[5].Trim()
                        }
                    }
                }
            }
        } catch {}

        return @{
            count    = $sessions.Count
            sessions = $sessions
        }
    }
    catch {
        return @{ count = 0; error = $_.Exception.Message }
    }
}

function Get-StartupPrograms {
    try {
        $startups = @()

        # Registry Run keys
        $runPaths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\RunOnce"
        )
        foreach ($rp in $runPaths) {
            try {
                $props = Get-ItemProperty $rp -ErrorAction SilentlyContinue
                if ($props) {
                    $props.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object {
                        $startups += @{ name = $_.Name; command = $_.Value; source = $rp }
                    }
                }
            } catch {}
        }

        # Scheduled tasks
        try {
            $tasks = Get-ScheduledTask -ErrorAction SilentlyContinue |
                Where-Object { $_.State -eq "Ready" -and $_.TaskPath -notlike "\Microsoft\*" } |
                Select-Object -First 20 |
                ForEach-Object {
                    @{
                        name   = $_.TaskName
                        path   = $_.TaskPath
                        state  = $_.State.ToString()
                        source = "ScheduledTask"
                    }
                }
            $startups += @($tasks)
        } catch {}

        return @{ count = $startups.Count; items = $startups }
    }
    catch {
        return @{ count = 0; error = $_.Exception.Message }
    }
}

function Get-TemperatureInfo {
    try {
        $temps = @()

        # WMI Thermal Zone
        try {
            $thermal = Get-CimInstance MSAcpi_ThermalZoneTemperature -Namespace "root/WMI" -ErrorAction SilentlyContinue
            if ($thermal) {
                foreach ($t in $thermal) {
                    $celsius = [math]::Round(($t.CurrentTemperature - 2732) / 10, 1)
                    $temps += @{
                        zone   = $t.InstanceName
                        temp_c = $celsius
                        source = "WMI_ThermalZone"
                    }
                }
            }
        } catch {}

        # NVIDIA GPU sıcaklık
        try {
            $nvsmi = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
            if ($nvsmi) {
                $nvTemp = & nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>$null
                if ($nvTemp) {
                    $temps += @{ zone = "NVIDIA_GPU"; temp_c = [int]$nvTemp; source = "nvidia-smi" }
                }
            }
        } catch {}

        return @{ sensors = $temps }
    }
    catch {
        return @{ sensors = @(); error = $_.Exception.Message }
    }
}

function Get-BatteryInfo {
    try {
        $battery = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $battery) { return @{ has_battery = $false } }
        return @{
            has_battery     = $true
            charge_percent  = $battery.EstimatedChargeRemaining
            status          = switch ($battery.BatteryStatus) {
                1 {"Deşarj"} 2 {"AC"} 3 {"Tam"} 4 {"Düşük"} 5 {"Kritik"} 6 {"Şarj"} 7 {"Şarj (Yüksek)"} 8 {"Şarj (Düşük)"} 9 {"Şarj (Kritik)"} default {"Bilinmiyor"}
            }
            runtime_min     = $battery.EstimatedRunTime
            design_voltage  = $battery.DesignVoltage
        }
    }
    catch {
        return @{ has_battery = $false; error = $_.Exception.Message }
    }
}

# ═══════════════════════════════════════════════════════════
#  SYSMON — TÜM VERİLER (29 EVENT ID)
# ═══════════════════════════════════════════════════════════

$Script:SysmonEventMap = @{
    1  = "ProcessCreate"
    2  = "FileCreateTime"
    3  = "NetworkConnect"
    4  = "SysmonServiceState"
    5  = "ProcessTerminate"
    6  = "DriverLoad"
    7  = "ImageLoad"
    8  = "CreateRemoteThread"
    9  = "RawAccessRead"
    10 = "ProcessAccess"
    11 = "FileCreate"
    12 = "RegistryAddDelete"
    13 = "RegistryValueSet"
    14 = "RegistryRename"
    15 = "FileCreateStreamHash"
    16 = "SysmonConfigChange"
    17 = "PipeCreated"
    18 = "PipeConnected"
    19 = "WmiFilterActivity"
    20 = "WmiConsumerActivity"
    21 = "WmiBindingActivity"
    22 = "DnsQuery"
    23 = "FileDelete"
    24 = "ClipboardChange"
    25 = "ProcessTampering"
    26 = "FileDeleteDetected"
    27 = "FileBlockExecutable"
    28 = "FileBlockShredding"
    29 = "FileExecutableDetected"
}

function Get-SysmonStatus {
    <# Sysmon kurulu mu, versiyon ve config bilgisi #>
    try {
        $svc = Get-Service -Name "Sysmon*" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $svc) {
            return @{ installed = $false; reason = "Sysmon servisi bulunamadi" }
        }
        $driver = Get-CimInstance Win32_SystemDriver -Filter "Name='SysmonDrv'" -ErrorAction SilentlyContinue
        $exe = (Get-Command sysmon -ErrorAction SilentlyContinue).Source
        $verInfo = $null
        if ($exe) {
            $verInfo = (Get-Item $exe -ErrorAction SilentlyContinue).VersionInfo.ProductVersion
        }
        return @{
            installed    = $true
            service_name = $svc.Name
            status       = $svc.Status.ToString()
            start_type   = $svc.StartType.ToString()
            version      = $verInfo
            driver       = if ($driver) { $driver.State } else { "unknown" }
            exe_path     = $exe
        }
    }
    catch {
        return @{ installed = $false; error = $_.Exception.Message }
    }
}

function Get-SysmonData {
    param(
        [int]$Hours = 1,
        [int]$MaxPerCategory = 25,
        [int[]]$EventIds = $null   # null = hepsi
    )
    try {
        $status = Get-SysmonStatus
        if (-not $status.installed) {
            return @{ available = $false; status = $status }
        }

        $logName = "Microsoft-Windows-Sysmon/Operational"
        $since = (Get-Date).AddHours(-$Hours)
        $targetIds = if ($EventIds) { $EventIds } else { $Script:SysmonEventMap.Keys | Sort-Object }

        # İstatistik özeti
        $summary = @{}
        $details = @{}

        foreach ($eid in $targetIds) {
            $catName = if ($Script:SysmonEventMap.ContainsKey($eid)) { $Script:SysmonEventMap[$eid] } else { "Unknown_$eid" }
            try {
                $events = Get-WinEvent -FilterHashtable @{
                    LogName   = $logName
                    Id        = $eid
                    StartTime = $since
                } -MaxEvents $MaxPerCategory -ErrorAction SilentlyContinue

                $count = 0
                if ($events) { $count = $events.Count }
                $summary[$catName] = $count

                if ($events -and $count -gt 0) {
                    $details[$catName] = @($events | ForEach-Object {
                        $parsed = Parse-SysmonEvent -Event $_ -EventId $eid
                        $parsed
                    })
                }
            }
            catch {
                $summary[$catName] = 0
            }
        }

        # Yüksek riskli olaylari isaretle
        $threats = @()
        $threatIds = @(8, 10, 25)  # CreateRemoteThread, ProcessAccess, ProcessTampering
        foreach ($tid in $threatIds) {
            $tName = $Script:SysmonEventMap[$tid]
            if ($details.ContainsKey($tName) -and $details[$tName].Count -gt 0) {
                $threats += @{
                    event_id = $tid
                    category = $tName
                    count    = $details[$tName].Count
                    severity = "HIGH"
                }
            }
        }

        $suspiciousNetIds = @(3, 22)  # NetworkConnect, DnsQuery
        foreach ($snid in $suspiciousNetIds) {
            $snName = $Script:SysmonEventMap[$snid]
            if ($summary.ContainsKey($snName) -and $summary[$snName] -gt 100) {
                $threats += @{
                    event_id = $snid
                    category = $snName
                    count    = $summary[$snName]
                    severity = "MEDIUM"
                    note     = "Son $Hours saatte yuksek hacim"
                }
            }
        }

        return @{
            available       = $true
            status          = $status
            period_hours    = $Hours
            collected_at    = (Get-Date -Format "o")
            event_summary   = $summary
            total_events    = ($summary.Values | Measure-Object -Sum).Sum
            threat_alerts   = $threats
            details         = $details
        }
    }
    catch {
        return @{ available = $false; error = $_.Exception.Message }
    }
}

function Parse-SysmonEvent {
    param($Event, [int]$EventId)
    $base = @{
        time = $Event.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
        id   = $EventId
    }
    $xml = [xml]$Event.ToXml()
    $data = @{}
    $xml.Event.EventData.Data | ForEach-Object {
        if ($_.Name) { $data[$_.Name] = $_.'#text' }
    }
    switch ($EventId) {
        1  { # ProcessCreate
            $base.image       = $data['Image']
            $base.commandline = $data['CommandLine']
            $base.user        = $data['User']
            $base.parent      = $data['ParentImage']
            $base.parent_cmd  = $data['ParentCommandLine']
            $base.pid         = $data['ProcessId']
            $base.ppid        = $data['ParentProcessId']
            $base.hashes      = $data['Hashes']
            $base.integrity   = $data['IntegrityLevel']
            $base.logon_guid  = $data['LogonGuid']
        }
        2  { # FileCreateTime
            $base.image          = $data['Image']
            $base.target_file    = $data['TargetFilename']
            $base.creation_utc   = $data['CreationUtcTime']
            $base.previous_utc   = $data['PreviousCreationUtcTime']
        }
        3  { # NetworkConnect
            $base.image      = $data['Image']
            $base.user       = $data['User']
            $base.protocol   = $data['Protocol']
            $base.src_ip     = $data['SourceIp']
            $base.src_port   = $data['SourcePort']
            $base.dst_ip     = $data['DestinationIp']
            $base.dst_port   = $data['DestinationPort']
            $base.dst_host   = $data['DestinationHostname']
            $base.initiated  = $data['Initiated']
        }
        5  { # ProcessTerminate
            $base.image = $data['Image']
            $base.pid   = $data['ProcessId']
        }
        6  { # DriverLoad
            $base.image     = $data['ImageLoaded']
            $base.hashes    = $data['Hashes']
            $base.signed    = $data['Signed']
            $base.signature = $data['Signature']
        }
        7  { # ImageLoad (DLL)
            $base.image      = $data['Image']
            $base.loaded     = $data['ImageLoaded']
            $base.hashes     = $data['Hashes']
            $base.signed     = $data['Signed']
            $base.signature  = $data['Signature']
        }
        8  { # CreateRemoteThread (THREAT)
            $base.source_image = $data['SourceImage']
            $base.target_image = $data['TargetImage']
            $base.source_pid   = $data['SourceProcessId']
            $base.target_pid   = $data['TargetProcessId']
            $base.start_addr   = $data['StartAddress']
            $base.start_module = $data['StartModule']
            $base.start_func   = $data['StartFunction']
        }
        9  { # RawAccessRead
            $base.image  = $data['Image']
            $base.device = $data['Device']
        }
        10 { # ProcessAccess (THREAT)
            $base.source_image = $data['SourceImage']
            $base.target_image = $data['TargetImage']
            $base.granted      = $data['GrantedAccess']
            $base.call_trace   = $data['CallTrace']
            $base.source_pid   = $data['SourceProcessId']
            $base.target_pid   = $data['TargetProcessId']
        }
        11 { # FileCreate
            $base.image       = $data['Image']
            $base.target_file = $data['TargetFilename']
            $base.creation    = $data['CreationUtcTime']
        }
        {$_ -in 12,13,14} { # Registry
            $base.image      = $data['Image']
            $base.event_type = $data['EventType']
            $base.target_obj = $data['TargetObject']
            if ($EventId -eq 13) { $base.reg_value = $data['Details'] }
            if ($EventId -eq 14) { $base.new_name  = $data['NewName'] }
        }
        15 { # FileCreateStreamHash
            $base.image       = $data['Image']
            $base.target_file = $data['TargetFilename']
            $base.hash        = $data['Hash']
        }
        {$_ -in 17,18} { # PipeCreated / PipeConnected
            $base.image     = $data['Image']
            $base.pipe_name = $data['PipeName']
        }
        {$_ -in 19,20,21} { # WMI
            $base.event_type = $data['EventType']
            $base.operation  = $data['Operation']
            $base.user       = $data['User']
            $base.name       = $data['Name']
            if ($EventId -eq 19) { $base.query = $data['Query'] }
            if ($EventId -eq 20) { $base.destination = $data['Destination'] }
        }
        22 { # DnsQuery
            $base.image    = $data['Image']
            $base.query    = $data['QueryName']
            $base.status   = $data['QueryStatus']
            $base.results  = $data['QueryResults']
        }
        {$_ -in 23,26} { # FileDelete / FileDeleteDetected
            $base.image       = $data['Image']
            $base.target_file = $data['TargetFilename']
            $base.hashes      = $data['Hashes']
            $base.is_exe      = $data['IsExecutable']
            if ($EventId -eq 23) { $base.archived = $data['Archived'] }
        }
        24 { # ClipboardChange
            $base.image    = $data['Image']
            $base.session  = $data['Session']
            $base.hashes   = $data['Hashes']
            $base.archived = $data['Archived']
        }
        25 { # ProcessTampering (THREAT)
            $base.image = $data['Image']
            $base.type  = $data['Type']
        }
        {$_ -in 27,28} { # FileBlock
            $base.image       = $data['Image']
            $base.target_file = $data['TargetFilename']
            $base.hashes      = $data['Hashes']
        }
        29 { # FileExecutableDetected
            $base.image       = $data['Image']
            $base.target_file = $data['TargetFilename']
            $base.hashes      = $data['Hashes']
        }
        default {
            # Bilinmeyen Event ID — ham veriyi ekle
            $base.raw_data = $data
        }
    }
    return $base
}

# ═══════════════════════════════════════════════════════════
#  DERİN TELEMETRİ — HEPSİNİ TOPLA
# ═══════════════════════════════════════════════════════════

function Collect-DeepTelemetry {
    Write-AgentLog "Derin telemetri toplaniyor..."
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    $telemetry = @{
        collected_at  = (Get-Date -Format "o")
        agent_version = $Script:Config.Version
        system        = Get-SystemInfo
        cpu           = Get-CpuMetrics
        memory        = Get-MemoryMetrics
        disks         = Get-DiskMetrics
        network       = Get-NetworkMetrics
        gpu           = Get-GpuMetrics
        security      = Get-SecurityStatus
        event_logs    = Get-EventLogSummary
        open_ports    = Get-OpenPorts
        sessions      = Get-UserSessions
        software      = Get-InstalledSoftware
        services      = Get-ServiceStatus
        processes     = Get-ProcessList
        startups      = Get-StartupPrograms
        temperature   = Get-TemperatureInfo
        battery       = Get-BatteryInfo
        sysmon        = Get-SysmonData -Hours 1 -MaxPerCategory 15
    }

    $sw.Stop()
    Write-AgentLog "Derin telemetri toplandi ($([math]::Round($sw.Elapsed.TotalSeconds, 1))s)"
    return $telemetry
}

# ═══════════════════════════════════════════════════════════
#  HEARTBEAT — TEMEL METRİKLER
# ═══════════════════════════════════════════════════════════

function Send-Heartbeat {
    $cpu = Get-CpuMetrics
    $mem = Get-MemoryMetrics
    $disk = Get-DiskMetrics
    $net = Get-NetworkMetrics

    $body = @{
        cpu     = $cpu.usage_percent
        ram     = $mem.usage_percent
        disk    = $disk.usage_percent
        net_in  = $net.total_rx_bytes
        net_out = $net.total_tx_bytes
        extra   = @{
            cpu_name     = $cpu.name
            cpu_cores    = $cpu.cores
            mem_total_gb = $mem.total_gb
            mem_free_gb  = $mem.free_gb
            disk_volumes = $disk.volumes
            net_ifaces   = $net.interfaces.Count
            connections  = $net.connections
        }
    }

    $result = Invoke-AgentRequest -Endpoint "agent/heartbeat" -Method "POST" -Body $body
    if ($result -and $result.success) {
        Write-AgentLog "Heartbeat gonderildi [CPU=$($cpu.usage_percent)% RAM=$($mem.usage_percent)% DISK=$($disk.usage_percent)%]"
    }
    else {
        Write-AgentLog "Heartbeat gonderilemedi!" "WARN"
    }
}

# ═══════════════════════════════════════════════════════════
#  GÖREV YÜRÜTÜCÜ
# ═══════════════════════════════════════════════════════════

function Execute-Task {
    param([hashtable]$Task)

    $taskId = $Task.id
    $taskType = $Task.task_type
    $payload = $Task.payload
    Write-AgentLog "Gorev calistiriliyor: [$taskType] ID=$taskId"

    $success = $true
    $result = ""

    try {
        switch ($taskType) {
            "shell_exec" {
                $cmd = $payload.cmd
                if (-not $cmd) { throw "cmd parametresi eksik" }
                $result = cmd.exe /c $cmd 2>&1 | Out-String
            }

            "powershell_exec" {
                $script = $payload.script
                if (-not $script) { throw "script parametresi eksik" }
                $result = Invoke-Expression $script 2>&1 | Out-String
            }

            "sysinfo_collect" {
                $telemetry = Collect-DeepTelemetry
                $result = $telemetry | ConvertTo-Json -Depth 10 -Compress
            }

            "registry_query" {
                $path = $payload.path
                if (-not $path) { throw "path parametresi eksik" }
                $regData = Get-ItemProperty -Path $path -ErrorAction Stop
                $result = $regData | ConvertTo-Json -Depth 5 -Compress
            }

            "event_log" {
                $logName = if ($payload.log) { $payload.log } else { "System" }
                $maxEvents = if ($payload.max_events) { [int]$payload.max_events } else { 50 }
                $level = if ($payload.level) { @([int]$payload.level) } else { @(1,2,3) }

                $events = Get-WinEvent -FilterHashtable @{LogName=$logName; Level=$level} -MaxEvents $maxEvents -ErrorAction SilentlyContinue |
                    ForEach-Object {
                        @{
                            id = $_.Id; level = $_.LevelDisplayName; source = $_.ProviderName
                            message = ($_.Message -split "`n")[0]
                            time = $_.TimeCreated.ToString("yyyy-MM-dd HH:mm:ss")
                        }
                    }
                $result = @{ events = $events; count = $events.Count } | ConvertTo-Json -Depth 5 -Compress
            }

            "sysmon_collect" {
                $hours = if ($payload.hours) { [int]$payload.hours } else { 1 }
                $maxPer = if ($payload.max_per_category) { [int]$payload.max_per_category } else { 50 }
                $filterIds = $null
                if ($payload.event_ids) {
                    $filterIds = @($payload.event_ids | ForEach-Object { [int]$_ })
                }
                $sysmonResult = Get-SysmonData -Hours $hours -MaxPerCategory $maxPer -EventIds $filterIds
                $result = $sysmonResult | ConvertTo-Json -Depth 10 -Compress
            }

            "restart_service" {
                $svcName = $payload.service
                if (-not $svcName) { throw "service parametresi eksik" }
                Restart-Service -Name $svcName -Force -ErrorAction Stop
                $svc = Get-Service -Name $svcName
                $result = "Servis yeniden baslatildi: $($svc.DisplayName) [$($svc.Status)]"
            }

            "install_software" {
                $installer = $payload.url
                $args = if ($payload.args) { $payload.args } else { "/S /quiet" }
                if (-not $installer) { throw "url parametresi eksik" }

                $tempFile = Join-Path $env:TEMP "emare_install_$(Get-Random).exe"
                Invoke-WebRequest -Uri $installer -OutFile $tempFile -UseBasicParsing
                $proc = Start-Process -FilePath $tempFile -ArgumentList $args -Wait -PassThru
                Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
                $result = "Kurulum tamamlandi. Exit code: $($proc.ExitCode)"
            }

            "uninstall_software" {
                $name = $payload.name
                if (-not $name) { throw "name parametresi eksik" }
                $uninstallString = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*" |
                    Where-Object DisplayName -like "*$name*" | Select-Object -First 1).UninstallString

                if ($uninstallString) {
                    Start-Process -FilePath "cmd.exe" -ArgumentList "/c $uninstallString /S /quiet" -Wait
                    $result = "Kaldirildi: $name"
                } else {
                    $result = "Yazilim bulunamadi: $name"
                    $success = $false
                }
            }

            "file_collect" {
                $filePath = $payload.path
                if (-not $filePath) { throw "path parametresi eksik" }
                if (-not (Test-Path $filePath)) { throw "Dosya bulunamadi: $filePath" }

                $fileInfo = Get-Item $filePath
                if ($fileInfo.Length -gt 5MB) { throw "Dosya cok buyuk (max 5MB): $($fileInfo.Length) bytes" }

                $content = [Convert]::ToBase64String([IO.File]::ReadAllBytes($filePath))
                $result = @{
                    file_name = $fileInfo.Name
                    file_size = $fileInfo.Length
                    content_base64 = $content
                    collected_at = (Get-Date -Format "o")
                } | ConvertTo-Json -Compress
            }

            "update_agent" {
                $updateUrl = $payload.url
                if (-not $updateUrl) { throw "url parametresi eksik" }
                $result = "Agent guncelleme henuz desteklenmiyor"
                $success = $false
            }

            "custom" {
                $customScript = $payload.script
                if ($customScript) {
                    $result = Invoke-Expression $customScript 2>&1 | Out-String
                } else {
                    $result = "Custom payload alindi: $($payload | ConvertTo-Json -Compress)"
                }
            }

            default {
                $result = "Bilinmeyen gorev tipi: $taskType"
                $success = $false
            }
        }
    }
    catch {
        $success = $false
        $result = "HATA: $($_.Exception.Message)"
        Write-AgentLog "Gorev hatasi [$taskType]: $($_.Exception.Message)" "ERROR"
    }

    # Sonuç boyut limiti (10KB)
    if ($result.Length -gt 10240) {
        $result = $result.Substring(0, 10000) + "`n... (kesildi, toplam: $($result.Length) karakter)"
    }

    # Sonucu gönder
    $body = @{
        task_id = $taskId
        success = $success
        result  = $result
    }
    Invoke-AgentRequest -Endpoint "agent/task-result" -Method "POST" -Body $body | Out-Null
    Write-AgentLog "Gorev tamamlandi [$taskType] basari=$success"
}

function Poll-Tasks {
    $result = Invoke-AgentRequest -Endpoint "agent/tasks" -Method "GET"
    if ($result -and $result.success -and $result.tasks) {
        foreach ($task in $result.tasks) {
            $taskHash = @{
                id        = $task.id
                task_type = $task.task_type
                payload   = if ($task.payload -is [string]) { $task.payload | ConvertFrom-Json -AsHashtable } else { $task.payload }
            }
            Execute-Task -Task $taskHash
        }
    }
}

# ═══════════════════════════════════════════════════════════
#  DERİN TELEMETRİ GÖNDERİMİ (5 dk'da bir)
# ═══════════════════════════════════════════════════════════

function Send-DeepTelemetry {
    $telemetry = Collect-DeepTelemetry
    $body = @{
        cpu     = $telemetry.cpu.usage_percent
        ram     = $telemetry.memory.usage_percent
        disk    = $telemetry.disks.usage_percent
        net_in  = $telemetry.network.total_rx_bytes
        net_out = $telemetry.network.total_tx_bytes
        extra   = $telemetry
    }

    $result = Invoke-AgentRequest -Endpoint "agent/heartbeat" -Method "POST" -Body $body
    if ($result -and $result.success) {
        Write-AgentLog "Derin telemetri gonderildi (tum katmanlar)"
    }
}

# ═══════════════════════════════════════════════════════════
#  ANA DÖNGÜ
# ═══════════════════════════════════════════════════════════

function Start-AgentLoop {
    Write-AgentLog "============================================"
    Write-AgentLog "Emare Security OS RMM Agent v$($Script:Config.Version)"
    Write-AgentLog "Sunucu: $($Script:Config.ServerUrl)"
    Write-AgentLog "============================================"

    # Key yükle veya kayıt ol
    if (-not (Load-AgentKey)) {
        $registered = Register-Agent
        if (-not $registered) {
            Write-AgentLog "Kayit basarisiz, 30 saniye sonra tekrar denenecek..." "ERROR"
            Start-Sleep -Seconds 30
            return Start-AgentLoop
        }
    }

    $heartbeatTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $taskTimer = [System.Diagnostics.Stopwatch]::StartNew()
    $deepTimer = [System.Diagnostics.Stopwatch]::StartNew()

    # İlk derin telemetri
    Send-DeepTelemetry

    Write-AgentLog "Agent dongüsü baslatildi [heartbeat=${Script:Config.HeartbeatSec}s task_poll=${Script:Config.TaskPollSec}s deep=${Script:Config.DeepCollectSec}s]"

    while ($true) {
        try {
            # Heartbeat
            if ($heartbeatTimer.Elapsed.TotalSeconds -ge $Script:Config.HeartbeatSec) {
                Send-Heartbeat
                $heartbeatTimer.Restart()
            }

            # Task polling
            if ($taskTimer.Elapsed.TotalSeconds -ge $Script:Config.TaskPollSec) {
                Poll-Tasks
                $taskTimer.Restart()
            }

            # Derin telemetri
            if ($deepTimer.Elapsed.TotalSeconds -ge $Script:Config.DeepCollectSec) {
                Send-DeepTelemetry
                $deepTimer.Restart()
            }

            Start-Sleep -Seconds 5
        }
        catch {
            Write-AgentLog "Ana dongü hatasi: $($_.Exception.Message)" "ERROR"
            Start-Sleep -Seconds 10
        }
    }
}

# ═══════════════════════════════════════════════════════════
#  BAŞLAT
# ═══════════════════════════════════════════════════════════

# CLI parametreleri
param(
    [string]$Server = "",
    [switch]$Register,
    [switch]$DeepScan,
    [switch]$Service
)

if ($Server) { $Script:Config.ServerUrl = $Server }

if ($Register) {
    # Sadece kayıt ol ve çık
    Register-Agent
    exit 0
}

if ($DeepScan) {
    # Tek seferlik derin tarama
    $data = Collect-DeepTelemetry
    $data | ConvertTo-Json -Depth 10 | Set-Content "$env:USERPROFILE\Desktop\EmareDeepScan.json" -Encoding UTF8
    Write-Host "Derin tarama tamamlandi: $env:USERPROFILE\Desktop\EmareDeepScan.json"
    exit 0
}

# Normal çalıştırma
Start-AgentLoop
