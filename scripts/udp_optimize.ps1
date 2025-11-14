# UDP Performance Optimization Script for Windows
# Run as Administrator
#
# Usage:
#   .\udp_optimize.ps1 query   - Show current settings
#   .\udp_optimize.ps1 apply   - Apply optimizations (backs up to udp_backup.reg)
#   .\udp_optimize.ps1 revert  - Restore from backup

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("query", "apply", "revert")]
    [string]$Action
)

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "This script must be run as Administrator!"
    exit 1
}

$backupFile = "udp_backup.reg"

# Define registry settings
$regSettings = @(
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\AFD\Parameters"
        Name = "DefaultReceiveWindow"
        Type = "DWORD"
        Value = 16777216  # 16MB
        Description = "UDP Receive Buffer Size"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\AFD\Parameters"
        Name = "LargeBufferSize"
        Type = "DWORD"
        Value = 4096
        Description = "Large Buffer Size"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\AFD\Parameters"
        Name = "MediumBufferSize"
        Type = "DWORD"
        Value = 1504
        Description = "Medium Buffer Size"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
        Name = "TcpWindowSize"
        Type = "DWORD"
        Value = 65535
        Description = "TCP Window Size"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
        Name = "MaxConnectionsPerServer"
        Type = "DWORD"
        Value = 16
        Description = "Max Connections Per Server"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
        Name = "MaxFreeTcbs"
        Type = "DWORD"
        Value = 16000
        Description = "Max Free TCBs"
    },
    @{
        Path = "HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
        Name = "DefaultTTL"
        Type = "DWORD"
        Value = 64
        Description = "Default TTL"
    }
)

function Query-Settings {
    Write-Host "`n=== Current UDP/TCP Performance Settings ===" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($setting in $regSettings) {
        $path = $setting.Path
        $name = $setting.Name
        
        # Ensure path exists
        if (-not (Test-Path $path)) {
            Write-Host "[$name] Path does not exist: $path" -ForegroundColor Yellow
            Write-Host "  Description: $($setting.Description)" -ForegroundColor Gray
            Write-Host "  Current: NOT SET" -ForegroundColor Yellow
            Write-Host "  Recommended: $($setting.Value)" -ForegroundColor Green
            Write-Host ""
            continue
        }
        
        try {
            $currentValue = Get-ItemProperty -Path $path -Name $name -ErrorAction Stop
            Write-Host "[$name] $($setting.Description)" -ForegroundColor White
            Write-Host "  Path: $path" -ForegroundColor Gray
            Write-Host "  Current: $($currentValue.$name)" -ForegroundColor Yellow
            Write-Host "  Recommended: $($setting.Value)" -ForegroundColor Green
        }
        catch {
            Write-Host "[$name] $($setting.Description)" -ForegroundColor White
            Write-Host "  Path: $path" -ForegroundColor Gray
            Write-Host "  Current: NOT SET" -ForegroundColor Yellow
            Write-Host "  Recommended: $($setting.Value)" -ForegroundColor Green
        }
        Write-Host ""
    }
}

function Backup-Settings {
    Write-Host "Creating backup..." -ForegroundColor Cyan
    
    $backupContent = "Windows Registry Editor Version 5.00`r`n`r`n"
    
    foreach ($setting in $regSettings) {
        $path = $setting.Path
        $name = $setting.Name
        
        if (Test-Path $path) {
            try {
                $currentValue = Get-ItemProperty -Path $path -Name $name -ErrorAction Stop
                $regPath = $path -replace "HKLM:\\", "HKEY_LOCAL_MACHINE\"
                $backupContent += "[$regPath]`r`n"
                $backupContent += "`"$name`"=dword:$("{0:x8}" -f $currentValue.$name)`r`n`r`n"
            }
            catch {
                # Value doesn't exist, note it in backup
                $regPath = $path -replace "HKLM:\\", "HKEY_LOCAL_MACHINE\"
                $backupContent += "; [$regPath]`r`n"
                $backupContent += "; `"$name`" was not set`r`n`r`n"
            }
        }
    }
    
    $backupContent | Out-File -FilePath $backupFile -Encoding ASCII
    Write-Host "Backup saved to: $backupFile" -ForegroundColor Green
}

function Apply-Settings {
    Write-Host "`n=== Applying UDP/TCP Optimizations ===" -ForegroundColor Cyan
    
    # Create backup first
    Backup-Settings
    Write-Host ""
    
    $changedCount = 0
    
    foreach ($setting in $regSettings) {
        $path = $setting.Path
        $name = $setting.Name
        $value = $setting.Value
        
        # Ensure registry path exists
        if (-not (Test-Path $path)) {
            Write-Host "Creating registry path: $path" -ForegroundColor Yellow
            New-Item -Path $path -Force | Out-Null
        }
        
        try {
            # Get current value
            $currentValue = $null
            try {
                $current = Get-ItemProperty -Path $path -Name $name -ErrorAction Stop
                $currentValue = $current.$name
            }
            catch {
                $currentValue = $null
            }
            
            if ($currentValue -eq $value) {
                Write-Host "[UNCHANGED] $name = $value" -ForegroundColor Gray
            }
            else {
                Set-ItemProperty -Path $path -Name $name -Value $value -Type $setting.Type
                Write-Host "[APPLIED] $name = $value (was: $currentValue)" -ForegroundColor Green
                $changedCount++
            }
        }
        catch {
            Write-Host "[ERROR] Failed to set $name : $_" -ForegroundColor Red
        }
    }
    
    Write-Host "`n$changedCount settings changed." -ForegroundColor Cyan
    
    if ($changedCount -gt 0) {
        Write-Host "`n⚠️  IMPORTANT: Restart your computer for changes to take effect!" -ForegroundColor Yellow
    }
}

function Revert-Settings {
    if (-not (Test-Path $backupFile)) {
        Write-Error "Backup file not found: $backupFile"
        Write-Host "Run 'apply' first to create a backup, or restore manually." -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host "`n=== Reverting to Backed Up Settings ===" -ForegroundColor Cyan
    Write-Host "Importing: $backupFile" -ForegroundColor Yellow
    
    try {
        $result = reg import $backupFile 2>&1
        
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Settings restored successfully!" -ForegroundColor Green
            Write-Host "`n⚠️  IMPORTANT: Restart your computer for changes to take effect!" -ForegroundColor Yellow
        }
        else {
            Write-Error "Failed to import registry file: $result"
        }
    }
    catch {
        Write-Error "Error importing registry: $_"
    }
}

# Main execution
switch ($Action) {
    "query" {
        Query-Settings
    }
    "apply" {
        Apply-Settings
    }
    "revert" {
        Revert-Settings
    }
}

Write-Host "`nDone!" -ForegroundColor Cyan