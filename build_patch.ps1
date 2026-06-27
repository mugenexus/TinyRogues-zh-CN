param(
    [string]$CsvPath = (Join-Path $PSScriptRoot 'translations_zh.csv'),
    [Parameter(Mandatory = $true)]
    [string]$FontBundlePath,
    [string]$BepInExZip = (Join-Path $PSScriptRoot 'BepInEx-Unity.IL2CPP-win-x64-6.0.0-be.759+9aedb90.zip'),
    [string]$XUnityZip = (Join-Path $PSScriptRoot 'XUnity.AutoTranslator-BepInEx-IL2CPP-5.6.1.zip'),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'TinyRogues_zh_patch')
)

$ErrorActionPreference = 'Stop'

function Escape-XUnityText {
    param([string]$Text)
    $normalized = $Text.TrimEnd('\')
    return $normalized.Replace("`r`n", '\n').Replace("`r", '\n').Replace("`n", '\n').Replace('=', '\=')
}

function Find-XUnityDictionarySeparator {
    param([string]$Line)

    if ($Line.StartsWith('r:"', [StringComparison]::Ordinal)) {
        $marker = $Line.LastIndexOf('"=', [StringComparison]::Ordinal)
        if ($marker -ge 0) {
            return $marker + 1
        }
        return -1
    }

    $insideTag = $false
    for ($index = 0; $index -lt $Line.Length; $index++) {
        $character = $Line[$index]
        $escaped = $index -gt 0 -and $Line[$index - 1] -eq '\'
        if (-not $escaped -and $character -eq '<') {
            $insideTag = $true
            continue
        }
        if (-not $escaped -and $character -eq '>') {
            $insideTag = $false
            continue
        }
        if (-not $insideTag -and -not $escaped -and $character -eq '=') {
            return $index
        }
    }

    return -1
}

function ConvertTo-XUnityDictionaryLine {
    param([string]$Line)

    if ([string]::IsNullOrWhiteSpace($Line) -or $Line.StartsWith('//', [StringComparison]::Ordinal)) {
        return $Line
    }

    $separator = Find-XUnityDictionarySeparator $Line
    if ($separator -le 0) {
        return $Line
    }

    $source = $Line.Substring(0, $separator)
    $translation = $Line.Substring($separator + 1)
    $source = [regex]::Replace($source, '(?<!\\)=', '\=')
    $translation = [regex]::Replace($translation, '(?<!\\)=', '\=')
    return $source + '=' + $translation
}

function Get-ControlSignature {
    param([string]$Text)
    $pattern = '\r\n|\r|\n|\\n|\\r|\\t|<[^>]+>|\{[^{}]+\}|\(\*\)|\(br\)|\((?:x\d+(?:%?x\d+)?|[a-z][A-Za-z0-9_]*)\)|\[\[|\]\]|##|//'
    return (([regex]::Matches($Text, $pattern) |
        ForEach-Object {
            if ($_.Value -eq "`r`n" -or $_.Value -eq "`r" -or $_.Value -eq "`n") {
                '\n'
            }
            else {
                $_.Value
            }
        } |
        Sort-Object) -join [char]0)
}

function Test-LikelyRuntimeText {
    param(
        [string]$Text,
        [string]$Key
    )

    if ($Text -match '^\{nb\[{8,}|^sf\[{8,}' -or $Text -match '[\[\]@`]{8,}') {
        return $false
    }
    if ($Key -like 'AUTO_*' -and $Text -match '([A-Za-z0-9])\1{7,}') {
        return $false
    }
    if ($Text -match 'SIL OPEN FONT LICENSE|Open Font License|VeriSign|Certification Authority|Universal Render Pipeline|SRDebugger|Developed by Stompy Robot|FontForge|nullCRA') {
        return $false
    }
    if ($Key -like 'AUTO_RESOURCES_ASSETS_*' -and
        $Text -notmatch '[.!?:]|\[\[|<sprite|<color|<i>|<g>|//|##' -and
        $Text -match '(?: Effect| Event| Parent| Layout(?: Group| Element)?| Icon| Text| Display| Canvas| Animator| Sprite| Projectile| Trigger| Branch| Manager| Controller| Renderer| Shader| Material| Cache| Gate)$') {
        return $false
    }
    if ($Text.Length -gt 16 -and $Text -notmatch '\s' -and $Text -notmatch '<[^>]+>|\[\[') {
        $letters = ([regex]::Matches($Text, '[A-Za-z]')).Count
        $symbols = ([regex]::Matches($Text, '[^A-Za-z0-9]')).Count
        if ($symbols -gt $letters) {
            return $false
        }
    }
    return $true
}

foreach ($required in @(
    $CsvPath,
    $BepInExZip,
    $XUnityZip,
    $FontBundlePath
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "缺少构建输入：$required"
    }
}

$workspace = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (-not $output.StartsWith($workspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw "输出目录必须位于工作区内：$output"
}
if ([IO.Path]::GetFileName($output) -ne 'TinyRogues_zh_patch') {
    throw "拒绝清理非预期输出目录：$output"
}

if (Test-Path -LiteralPath $output) {
    Remove-Item -LiteralPath $output -Recurse -Force
}

New-Item -ItemType Directory -Path $output | Out-Null

Expand-Archive -LiteralPath $BepInExZip -DestinationPath $output -Force
Copy-Item -LiteralPath $FontBundlePath -Destination (Join-Path $output 'arialuni_sdf_u2019')

Expand-Archive -LiteralPath $XUnityZip -DestinationPath $output -Force

$configDirectory = Join-Path $output 'BepInEx\config'
$translationDirectory = Join-Path $output 'BepInEx\Translation\zh\Text'
$sourceDirectory = Join-Path $output 'Source'
New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $translationDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $sourceDirectory -Force | Out-Null

$config = @'
[Service]
Endpoint=
FallbackEndpoint=

[General]
Language=zh
FromLanguage=en

[Files]
Directory=Translation\{Lang}\Text
OutputFile=Translation\{Lang}\Text\_AutoGeneratedTranslations.txt
SubstitutionFile=Translation\{Lang}\Text\_Substitutions.txt
PreprocessorsFile=Translation\{Lang}\Text\_Preprocessors.txt
PostprocessorsFile=Translation\{Lang}\Text\_Postprocessors.txt

[TextFrameworks]
EnableIMGUI=False
EnableUGUI=True
EnableUIElements=True
EnableNGUI=False
EnableTextMeshPro=True
EnableTextMesh=False
EnableFairyGUI=False

[Behaviour]
MaxCharactersPerTranslation=2500
IgnoreWhitespaceInDialogue=True
MinDialogueChars=1
EnableUIResizing=True
ForceUIResizing=False
UseStaticTranslations=False
OverrideFont=
OverrideFontSize=
OverrideFontTextMeshPro=
FallbackFontTextMeshPro=arialuni_sdf_u2019
HandleRichText=True
PersistRichTextMode=Final
EnableTranslationScoping=False
EnableSilentMode=True
ReloadTranslationsOnFileChange=True
GeneratePartialTranslations=False
OutputUntranslatableText=False
DisableTextMeshProScrollInEffects=False
IgnoreVirtualTextSetterCallingRules=True

[Texture]
EnableTextureTranslation=False
EnableTextureDumping=False

[ResourceRedirector]
EnableTextAssetRedirector=False
LogAllLoadedResources=False
EnableDumping=False

[Http]
DisableCertificateValidation=False

[Debug]
EnableConsole=False

[Migrations]
Enable=True
Tag=5.6.1
'@
$utf8Bom = New-Object Text.UTF8Encoding($true)
[IO.File]::WriteAllText(
    (Join-Path $configDirectory 'AutoTranslatorConfig.ini'),
    $config,
    $utf8Bom
)

$rows = @(Import-Csv -LiteralPath $CsvPath)
$invalid = @(
    $rows | Where-Object {
        [string]::IsNullOrWhiteSpace($_.translation_zh) -or
        (Get-ControlSignature $_.source_text) -cne (Get-ControlSignature $_.translation_zh)
    }
)
if ($invalid.Count -gt 0) {
    throw "存在 $($invalid.Count) 条空译文或控制符不一致，停止构建。"
}

$dictionaryLines = New-Object System.Collections.Generic.List[string]
$groups = @($rows | Group-Object source_text)
foreach ($group in $groups) {
    $selected = @(
        $group.Group |
            Sort-Object @{ Expression = { if ($_.key -like 'AUTO_*') { 1 } else { 0 } } }
    )[0]

    if ($selected.source_text -match '^[^A-Za-z0-9\u4e00-\u9fff]*$') {
        continue
    }
    if (-not (Test-LikelyRuntimeText $selected.source_text $selected.key)) {
        continue
    }

    $source = Escape-XUnityText $selected.source_text
    $translation = Escape-XUnityText $selected.translation_zh
    $dictionaryLines.Add($source + '=' + $translation)
}

$dictionaryLines.Sort([StringComparer]::Ordinal)
[IO.File]::WriteAllLines(
    (Join-Path $translationDirectory 'TinyRogues_zh.txt'),
    $dictionaryLines,
    $utf8Bom
)
$runtimeOverrideLines = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime_overrides_zh.txt') -Encoding UTF8 |
    ForEach-Object { ConvertTo-XUnityDictionaryLine $_ }
[IO.File]::WriteAllLines(
    (Join-Path $translationDirectory 'RuntimeOverrides_zh.txt'),
    $runtimeOverrideLines,
    $utf8Bom
)
[IO.File]::WriteAllText(
    (Join-Path $translationDirectory 'RuntimeFragments_zh.txt'),
    '',
    $utf8Bom
)
$fallbackPlugin = Join-Path $PSScriptRoot 'TinyRogues.TmpFallback\bin\Release\netstandard2.1\TinyRogues.TmpFallback.dll'
if (-not (Test-Path -LiteralPath $fallbackPlugin)) {
    throw "缺少 TMP 补充插件，请先执行 dotnet build -c Release：$fallbackPlugin"
}
$fallbackPluginDirectory = Join-Path $output 'BepInEx\plugins\TinyRogues.TmpFallback'
New-Item -ItemType Directory -Path $fallbackPluginDirectory -Force | Out-Null
Copy-Item -LiteralPath $fallbackPlugin -Destination $fallbackPluginDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime_regex_zh.txt') `
    -Destination (Join-Path $fallbackPluginDirectory 'RuntimeRegex_zh.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime_fragments_zh.txt') `
    -Destination (Join-Path $fallbackPluginDirectory 'RuntimeFragments_zh.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime_item_fragments_zh.txt') `
    -Destination (Join-Path $fallbackPluginDirectory 'RuntimeItemFragments_zh.txt')
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'runtime_plugin_overrides_zh.txt') `
    -Destination (Join-Path $fallbackPluginDirectory 'RuntimePluginOverrides_zh.txt')

$dialogueRows = @(
    $rows | Where-Object {
        ($_.key -notlike 'AUTO_*' -or $_.source_file -like '*global-metadata.dat') -and
        $_.source_text.Length -ge 6 -and
        $_.source_text -match '[.!?]|\\n' -and
        $_.translation_zh -cne $_.source_text
    }
)
$dialogueMap = [ordered]@{}
foreach ($row in $dialogueRows) {
    $source = Escape-XUnityText $row.source_text
    $dialogueMap[$source] = Escape-XUnityText $row.translation_zh
}
foreach ($line in Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime_dialogue_overrides_zh.txt') -Encoding UTF8) {
    $converted = ConvertTo-XUnityDictionaryLine $line
    $separator = Find-XUnityDictionarySeparator $converted
    if ($separator -gt 0) {
        $source = $converted.Substring(0, $separator)
        $translation = $converted.Substring($separator + 1)
        $dialogueMap[$source] = $translation
    }
}
$dialogueLines = @(
    $dialogueMap.GetEnumerator() | ForEach-Object {
        $_.Key + '=' + $_.Value
    }
)
[IO.File]::WriteAllLines(
    (Join-Path $fallbackPluginDirectory 'RuntimeDialogue_zh.txt'),
    $dialogueLines,
    $utf8Bom
)
[IO.File]::WriteAllText(
    (Join-Path $translationDirectory '_AutoGeneratedTranslations.txt'),
    '',
    $utf8Bom
)
foreach ($name in @('_Preprocessors.txt', '_Postprocessors.txt', '_Substitutions.txt')) {
    [IO.File]::WriteAllText((Join-Path $translationDirectory $name), '', $utf8Bom)
}

Copy-Item -LiteralPath $CsvPath -Destination (Join-Path $sourceDirectory 'translations_zh.csv')

$readme = @"
# Tiny Rogues 简体中文运行时补丁

适配扫描版本：Unity 2022.3.62f2 / IL2CPP

## 安装

1. 退出游戏。
2. 将本目录内的全部文件复制到 Tiny Rogues.exe 所在目录。
3. 首次启动会生成当前版本的 IL2CPP 互操作程序集，耗时可能较长。
4. 看到主菜单后即可检查中文显示。

## 卸载

删除安装时新增的以下项目：

- BepInEx
- dotnet
- winhttp.dll
- doorstop_config.ini
- .doorstop_version
- arialuni_sdf_u2019

本补丁不会替换 Tiny Rogues_Data、GameAssembly.dll 或游戏可执行文件。

## 说明

- BepInEx：6.0.0-be.759
- XUnity.AutoTranslator：5.6.1
- 静态词库：$($dictionaryLines.Count) 条
- 在线翻译：关闭
- IMGUI 钩子：关闭
- TMP 字体：arialuni_sdf_u2019

完整校对源表位于 Source\translations_zh.csv。
"@
[IO.File]::WriteAllText((Join-Path $output 'README.md'), $readme, $utf8Bom)

$manifest = Get-ChildItem -LiteralPath $output -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        [pscustomobject]@{
            Path = $_.FullName.Substring($output.Length + 1)
            Size = $_.Length
            SHA256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    }
$manifest | Export-Csv -LiteralPath (Join-Path $output 'manifest.csv') -NoTypeInformation -Encoding UTF8

Write-Output "补丁目录：$output"
Write-Output "静态词库：$($dictionaryLines.Count) 条"
Write-Output "文件数量：$($manifest.Count)"
