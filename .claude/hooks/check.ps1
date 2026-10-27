# PostToolUse(Edit|Write|NotebookEdit): 고친 파일에 확장자별 검사를 돌리고, 실패하면 출력을 Claude에게 돌려준다(exit 2).
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
# 확장자별 검사 명령. 고친 파일 경로가 맨 뒤에 붙는다. 비어 있으면 아무것도 하지 않는다.
# docs 단계에서 PRD §6 "편집 때 자동 검사"대로 채운다. 예: '.py' = @('ruff check', 'pyright')
# shortcut: 명령은 공백으로만 나누므로 공백이 든 인자는 못 쓴다. 필요해지면 배열 형식으로 바꾼다.
$checks = @{
    '.py' = @('.venv\Scripts\ruff.exe check')   # PRD §6 (D063). pyright는 O107 뒤
}
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $data.cwd }
$path = [string]($data.tool_input.file_path ?? $data.tool_input.notebook_path)
if (-not $path) { exit 0 }
$full = [IO.Path]::GetFullPath($path, $root)
$base = [IO.Path]::GetFullPath($root).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path $full)) { exit 0 }
$cmds = $checks[[IO.Path]::GetExtension($full)]
if (-not $cmds) { exit 0 }
Set-Location $root
$failed = foreach ($cmd in @($cmds)) {
    $exe, $rest = -split $cmd
    $args_ = @($rest | Where-Object { $_ })   # 인자가 하나면 문자열로 와서 글자 단위로 펼쳐지므로 배열로
    if (-not (Get-Command $exe)) { "[metarche] 검사 도구 없음: $exe. 설치하거나 .claude/hooks/check.ps1에서 빼십시오."; continue }
    $out = & $exe @args_ $full 2>&1
    if ($LASTEXITCODE -ne 0) { "[metarche] 검사 실패: $cmd $full"; $out | Select-Object -First 30 }
}
if ($failed) { [Console]::Error.WriteLine(($failed -join "`n")); exit 2 }
exit 0
