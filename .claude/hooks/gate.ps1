# PreToolUse(Edit|Write|NotebookEdit): docs/PRD.md가 approved가 아니면 docs/·.claude/·CLAUDE.md 밖 수정을 막는다.
$ErrorActionPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$data = [Console]::In.ReadToEnd() | ConvertFrom-Json
$root = if ($env:CLAUDE_PROJECT_DIR) { $env:CLAUDE_PROJECT_DIR } else { $data.cwd }
$prd = Join-Path $root 'docs/PRD.md'
if (-not (Test-Path $prd)) { exit 0 }
if ((Get-Content $prd -Encoding utf8 -TotalCount 5) -match '상태:\s*approved') { exit 0 }
$path = [string]($data.tool_input.file_path ?? $data.tool_input.notebook_path)
if (-not $path) { exit 0 }
# '..'을 풀어 docs/../src 같은 우회를 막는다.
$rel = [IO.Path]::GetFullPath($path, $root).Replace('\', '/')
# 루트도 같은 방식으로 풀어야 8.3 짧은 이름(ADMINI~1 등)과 비교가 맞는다.
$base = [IO.Path]::GetFullPath($root).Replace('\', '/').TrimEnd('/') + '/'
if ($rel.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) { $rel = $rel.Substring($base.Length) }
# .claude/worktrees/ 아래는 코드 사본이므로 허용하지 않는다.
if ($rel -match '^(docs/|\.claude/(?!worktrees/)|CLAUDE(\.local)?\.md$)') { exit 0 }
[Console]::Error.WriteLine("[metarche] PRD 미승인: $rel 수정 금지. docs/PRD.md 승인 전에는 문서만 고칩니다.")
exit 2
