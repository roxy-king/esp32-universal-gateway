param(
    [string]$Port,
    [ValidateRange(3,60)][int]$TimeoutSeconds = 15,
    [switch]$PassThru
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'tools/ap-info.ps1')
if (!$Port) { $Port = Read-Host 'ESP32 COM port, e.g. COM5' }
if ($Port -notmatch '^COM[0-9]+$') { throw 'Invalid COM port' }

$serial = New-Object System.IO.Ports.SerialPort $Port,115200,None,8,one
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.ReadTimeout = 300
$info = $null
try {
    # Allow the port to settle after esptool exits. Never erase or write flash here.
    $openDeadline = [DateTime]::UtcNow.AddSeconds(5)
    while (!$serial.IsOpen) {
        try { $serial.Open() }
        catch {
            if ([DateTime]::UtcNow -ge $openDeadline) { throw }
            Start-Sleep -Milliseconds 250
        }
    }
    $serial.DiscardInBuffer()
    # DTR stays low; RTS pulses EN on the USB-to-UART port for normal boot.
    $serial.RtsEnable = $true
    Start-Sleep -Milliseconds 150
    $serial.RtsEnable = $false
    Write-Host 'Reading startup information at 115200... Tap RST if nothing appears.'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $buffer = ''
    while ([DateTime]::UtcNow -lt $deadline) {
        $buffer += $serial.ReadExisting()
        $info = ConvertFrom-GatewayBootText $buffer
        if ($null -ne $info) { break }
        if ($buffer.Length -gt 16384) { $buffer = $buffer.Substring($buffer.Length - 8192) }
        Start-Sleep -Milliseconds 50
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
if ($null -eq $info) {
    throw 'No complete hotspot information received. Close serial monitors, check the COM port and USB-to-UART cable, then run read-hotspot.cmd and tap RST while it waits. Flashing does not need to be repeated.'
}
if ($PassThru) { return $info }
Write-Host ''
Write-Host '========== ESP32 Wi-Fi setup =========='
Write-Host ('Hotspot / SSID : ' + $info.SSID)
Write-Host ('Password       : ' + $info.Password)
Write-Host ('Setup page     : ' + $info.Address)
Write-Host 'Connect your phone to this hotspot, then open the setup page.'
Write-Host 'If the hotspot is hidden, hold BOOT for 4 seconds (do not press RST).'
Write-Host 'Keep this password private. It is displayed here, not saved to a file.'
