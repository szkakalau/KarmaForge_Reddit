# KarmaForge & Claude Code Key Cleanup Script
# Run AFTER closing all Claude Code sessions to ensure no active session keeps writing keys back.
# Usage: powershell -ExecutionPolicy Bypass -File cleanup_keys.ps1

$keys = @{
    "sk-4ddfe58c9b2f45a893c1f732d787b817" = "[REDACTED_KF_KEY]"
    "sk-b4ec548dcd5c4dfab1beef54368137ce" = "[REDACTED_KF_KEY_2]"
    "sk-52c47e25ec594bd39fb2913fdd22821e" = "[REDACTED_AUTH_TOKEN]"
}

$paths = @(
    "C:\Users\castr\.claude\projects",
    "C:\Users\castr\.claude\file-history",
    "c:\Users\castr\Desktop\OPC Project\KarmaForge_Reddit爆款引擎\.claude"
)

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$total = 0

foreach ($path in $paths) {
    if (-not (Test-Path $path)) { continue }

    Get-ChildItem -Path $path -Recurse -File -Include "*.json", "*.jsonl", "*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -notin @(".exe", ".dll", ".png", ".jpg", ".gif", ".ico", ".woff", ".woff2") } |
        ForEach-Object {
            try {
                $content = [System.IO.File]::ReadAllText($_.FullName, $utf8NoBom)
                $changed = $false
                foreach ($key in $keys.Keys) {
                    if ($content.Contains($key)) {
                        $content = $content.Replace($key, $keys[$key])
                        $changed = $true
                    }
                }
                if ($changed) {
                    [System.IO.File]::WriteAllText($_.FullName, $content, $utf8NoBom)
                    Write-Output "Cleaned: $($_.FullName)"
                    $total++
                }
            } catch {
                # Skip locked/binary files
            }
        }
}

Write-Output ""
Write-Output "=== Cleanup complete: $total files modified ==="
