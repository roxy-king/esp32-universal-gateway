$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../tools/ap-info.ps1')
function Assert-True($Value, $Message) { if (!$Value) { throw $Message } }
$line = "AP: Gateway-Setup-test1234 password: demoPass8`r`n"
$info = ConvertFrom-GatewayBootText ("boot noise`r`n" + $line)
Assert-True ($info.SSID -eq 'Gateway-Setup-test1234') 'SSID parsing failed'
Assert-True ($info.Password -eq 'demoPass8') 'Password parsing failed'
Assert-True ($null -eq (ConvertFrom-GatewayBootText $line.TrimEnd("`r","`n"))) 'Partial record must not be accepted'
Assert-True ($null -eq (ConvertFrom-GatewayBootText "AP: OtherNetwork password: demoPass8`n")) 'Unrelated network accepted'
Assert-True ($null -eq (ConvertFrom-GatewayBootText "AP: Gateway-Setup-test password: short`n")) 'Short password accepted'
$spaced = ConvertFrom-GatewayBootText "AP: Gateway-Setup-test password:  spaced pass! `n"
Assert-True ($spaced.Password -ceq ' spaced pass! ') 'Password whitespace was changed'
Assert-True ($null -eq (ConvertFrom-GatewayBootText 'no boot record')) 'Noise accepted'
foreach ($file in @('flash.ps1','read-hotspot.ps1')) {
    $tokens = $null; $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot "../$file"), [ref]$tokens, [ref]$errors)
    Assert-True ($errors.Count -eq 0) "PowerShell syntax error in $file"
}
Write-Host 'PASS: boot parser, split-record handling, whitespace preservation and script syntax.'
