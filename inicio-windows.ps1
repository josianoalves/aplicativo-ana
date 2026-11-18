param([switch]$Desativar)
$shortcutPath = Join-Path ([Environment]::GetFolderPath('Startup')) 'RADAR SHOPEE AI.lnk'
if ($Desativar) {
    if (Test-Path -LiteralPath $shortcutPath) { Remove-Item -LiteralPath $shortcutPath }
    Write-Host 'Inicializacao automatica desativada.'
} else {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $PSScriptRoot 'iniciar.bat'
    $shortcut.Arguments = '--no-browser'
    $shortcut.WorkingDirectory = $PSScriptRoot
    $shortcut.WindowStyle = 7
    $shortcut.Save()
    Write-Host 'O Radar iniciara quando voce entrar no Windows.'
}
