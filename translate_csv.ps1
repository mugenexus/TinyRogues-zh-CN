param(
    [string]$CsvPath = (Join-Path $PSScriptRoot 'translations_zh.csv'),
    [string]$OldTranslationPath = '',
    [int]$BatchCharacterLimit = 3200,
    [int]$DelayMilliseconds = 150
)

$ErrorActionPreference = 'Stop'

function Get-ControlTokens {
    param([string]$Text)

    $pattern = '\\n|\\r|\\t|<[^>]+>|\{[^{}]+\}|\(\*\)|\(br\)|\((?:x\d+(?:%?x\d+)?|[a-z][A-Za-z0-9_]*)\)|\[\[|\]\]|##|//'
    return @([regex]::Matches($Text, $pattern) | ForEach-Object { $_.Value })
}

function Protect-Text {
    param([string]$Text)

    $tokens = New-Object System.Collections.Generic.List[string]
    $pattern = '\\n|\\r|\\t|<[^>]+>|\{[^{}]+\}|\(\*\)|\(br\)|\((?:x\d+(?:%?x\d+)?|[a-z][A-Za-z0-9_]*)\)|\[\[|\]\]|##|//'
    $protected = [regex]::Replace($Text, $pattern, {
        param($match)
        $index = $tokens.Count
        $tokens.Add($match.Value)
        return '<x id="TRP{0:D4}"/>' -f $index
    })

    return [pscustomobject]@{
        Text = $protected
        Tokens = $tokens
    }
}

function Restore-Text {
    param(
        [string]$Text,
        [System.Collections.Generic.List[string]]$Tokens
    )

    $restored = [regex]::Replace($Text, '[\u00AD\u200B-\u200D\u2060\uFEFF]', '')
    for ($i = 0; $i -lt $Tokens.Count; $i++) {
        $restored = $restored.Replace(('<x id="TRP{0:D4}"/>' -f $i), $Tokens[$i])
        $restored = $restored.Replace(('__TRP{0:D4}__' -f $i), $Tokens[$i])
    }
    return $restored.Trim()
}

function Test-ControlTokens {
    param(
        [string]$Source,
        [string]$Translation
    )

    $sourceTokens = @(Get-ControlTokens $Source)
    $translatedTokens = @(Get-ControlTokens $Translation)
    if ($sourceTokens.Count -ne $translatedTokens.Count) {
        return $false
    }

    $sourceTokens = @($sourceTokens | Sort-Object)
    $translatedTokens = @($translatedTokens | Sort-Object)
    for ($i = 0; $i -lt $sourceTokens.Count; $i++) {
        if ($sourceTokens[$i] -cne $translatedTokens[$i]) {
            return $false
        }
    }
    return $true
}

function Read-XUnityDictionary {
    param([string]$Path)

    $dictionary = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $dictionary
    }

    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('//')) {
            continue
        }

        $separator = -1
        for ($i = 0; $i -lt $line.Length; $i++) {
            if ($line[$i] -eq '=' -and ($i -eq 0 -or $line[$i - 1] -ne '\')) {
                $separator = $i
                break
            }
        }
        if ($separator -le 0) {
            continue
        }

        $source = $line.Substring(0, $separator).Replace('\=', '=')
        $translation = $line.Substring($separator + 1).Replace('\=', '=')
        if ($translation -match '[\u4e00-\u9fff]' -and (Test-ControlTokens $source $translation)) {
            $dictionary[$source] = $translation
        }
    }
    return $dictionary
}

function Invoke-GoogleBatch {
    param([object[]]$Items)

    $parts = for ($i = 0; $i -lt $Items.Count; $i++) {
        '<<<TR{0:D4}>>> {1}' -f $i, $Items[$i].Protected.Text
    }
    $query = [uri]::EscapeDataString(($parts -join "`n"))
    $uri = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=$query"
    $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 60
    $joined = (($response[0] | ForEach-Object { $_[0] }) -join '')

    $results = @{}
    $matches = [regex]::Matches(
        $joined,
        '(?s)<<<TR(?<index>\d{4})>>>\s*(?<text>.*?)(?=<<<TR\d{4}>>>|\z)'
    )
    foreach ($match in $matches) {
        $index = [int]$match.Groups['index'].Value
        $results[$index] = $match.Groups['text'].Value.Trim()
    }
    return $results
}

if (-not (Test-Path -LiteralPath $CsvPath)) {
    throw "CSV 不存在：$CsvPath"
}

$csvBaseName = [IO.Path]::GetFileNameWithoutExtension($CsvPath)
$backupPath = Join-Path (Split-Path -Parent $CsvPath) ($csvBaseName + '.untranslated.csv')
if (-not (Test-Path -LiteralPath $backupPath)) {
    Copy-Item -LiteralPath $CsvPath -Destination $backupPath
}

$rows = @(Import-Csv -LiteralPath $CsvPath)
$oldDictionary = if ([string]::IsNullOrWhiteSpace($OldTranslationPath)) {
    @{}
}
else {
    Read-XUnityDictionary $OldTranslationPath
}
$oldMatched = 0

foreach ($row in $rows) {
    if ([string]::IsNullOrWhiteSpace($row.translation_zh) -and $oldDictionary.ContainsKey($row.source_text)) {
        $row.translation_zh = $oldDictionary[$row.source_text]
        $row.notes = (($row.notes + '; reused validated old translation').Trim(';', ' '))
        $oldMatched++
    }
}

$sourceGroups = @(
    $rows |
        Where-Object { [string]::IsNullOrWhiteSpace($_.translation_zh) } |
        Group-Object source_text
)

$queue = New-Object System.Collections.Generic.List[object]
foreach ($group in $sourceGroups) {
    $protected = Protect-Text $group.Name
    $queue.Add([pscustomobject]@{
        Source = $group.Name
        Rows = @($group.Group)
        Protected = $protected
    })
}

$translated = 0
$failed = New-Object System.Collections.Generic.List[string]
$position = 0

while ($position -lt $queue.Count) {
    $batch = New-Object System.Collections.Generic.List[object]
    $characters = 0

    while ($position -lt $queue.Count) {
        $candidate = $queue[$position]
        $cost = $candidate.Protected.Text.Length + 20
        if ($batch.Count -gt 0 -and $characters + $cost -gt $BatchCharacterLimit) {
            break
        }
        $batch.Add($candidate)
        $characters += $cost
        $position++
    }

    $attempt = 0
    $batchResults = $null
    while ($attempt -lt 4 -and $null -eq $batchResults) {
        try {
            $batchResults = Invoke-GoogleBatch -Items $batch.ToArray()
        }
        catch {
            Write-Warning ("翻译批次失败：{0}" -f $_.Exception.Message)
            $attempt++
            if ($attempt -ge 4) {
                foreach ($item in $batch) {
                    $failed.Add($item.Source)
                }
                break
            }
            Start-Sleep -Seconds ([math]::Pow(2, $attempt))
        }
    }

    if ($null -ne $batchResults) {
        for ($i = 0; $i -lt $batch.Count; $i++) {
            if (-not $batchResults.ContainsKey($i)) {
                $failed.Add($batch[$i].Source)
                continue
            }

            $restored = Restore-Text $batchResults[$i] $batch[$i].Protected.Tokens
            if (-not (Test-ControlTokens $batch[$i].Source $restored)) {
                $failed.Add($batch[$i].Source)
                continue
            }

            foreach ($row in $batch[$i].Rows) {
                $row.translation_zh = $restored
                $row.notes = (($row.notes + '; machine translated, controls validated').Trim(';', ' '))
                $translated++
            }
        }
    }

    if (($position % 250) -lt $batch.Count) {
        $rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8
        Write-Output "进度：$position / $($queue.Count)"
    }
    Start-Sleep -Milliseconds $DelayMilliseconds
}

$rows | Export-Csv -LiteralPath $CsvPath -NoTypeInformation -Encoding UTF8
$failedPath = Join-Path (Split-Path -Parent $CsvPath) 'translation_failed.txt'
@($failed) | Set-Content -LiteralPath $failedPath -Encoding UTF8

Write-Output "旧词库匹配：$oldMatched"
Write-Output "机器翻译行：$translated"
Write-Output "失败原文：$(@($failed).Count)"
