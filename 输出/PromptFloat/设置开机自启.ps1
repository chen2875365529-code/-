$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$target = Join-Path $here 'prompt_float.py'
$pyw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $pyw) {
    $py = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if ($py) { $pyw = Join-Path (Split-Path $py) 'pythonw.exe' }
}
if (-not $pyw) { throw '未找到 pythonw.exe' }
$startup = [Environment]::GetFolderPath('Startup')
$lnk = Join-Path $startup 'PromptFloat.lnk'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + $target + '"'
$s.WorkingDirectory = $here
$s.IconLocation = (Join-Path $here 'icon.ico') + ',0'
$s.Description = '桌面悬浮提示词面板'
$s.WindowStyle = 7
$s.Save()
Write-Host "已设置开机自启: $lnk" -ForegroundColor Green
Write-Host "取消自启: 删除该文件即可" -ForegroundColor DarkGray
