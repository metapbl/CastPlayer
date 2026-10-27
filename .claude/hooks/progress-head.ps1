# SessionStart: docs/PROGRESS.md 머리(<!-- head:end --> 위, 최대 40줄)를 컨텍스트에 넣는다.
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { (Get-Location).Path }
$file = Join-Path $root 'docs/PROGRESS.md'
if (-not (Test-Path $file)) { exit 0 }
$head = foreach ($line in Get-Content $file -Encoding utf8 -TotalCount 60) {
    if ($line -match '<!--\s*head:end') { break }
    $line
}
'[metarche] docs/PROGRESS.md 머리 (자동 주입)'
@($head) | Select-Object -First 40
exit 0
