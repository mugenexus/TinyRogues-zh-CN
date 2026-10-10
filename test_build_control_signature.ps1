$ErrorActionPreference = 'Stop'

# Load the actual build validator without expanding archives or generating a patch.
$tokens = $null
$parseErrors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile(
    (Join-Path $PSScriptRoot 'build_patch.ps1'), [ref]$tokens, [ref]$parseErrors
)
if ($parseErrors.Count -gt 0) {
    throw 'Could not parse build_patch.ps1.'
}
$signatureFunction = $ast.Find({
    param($node)
    $node -is [Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -eq 'Get-ControlSignature'
}, $true)
if ($null -eq $signatureFunction) {
    throw 'Get-ControlSignature was not found.'
}
Invoke-Expression $signatureFunction.Extent.Text

$labelCases = @(
    @{ Source = 'instead of ((emptying))'; Translation = 'instead of ((清空))' },
    @{ Source = '<g>(multiplicative)</g>'; Translation = '<g>（乘算）</g>' }
)
foreach ($case in $labelCases) {
    if ((Get-ControlSignature $case.Source) -cne (Get-ControlSignature $case.Translation)) {
        throw "Translatable label rejected: $($case.Source)"
    }
}

# Removing real variables or formatting markers must still fail validation.
$requiredTokens = @(
    '(duration)', '(actionName)', '(x0)', '(xx0)', '(x0x1)', '((duration))',
    '(unknownPlaceholder)', '<sprite name="Heart">', '{0}', '\n', '(*)', '(br)',
    '[[', ']]', '##', '//'
)
foreach ($token in $requiredTokens) {
    if ((Get-ControlSignature $token) -ceq (Get-ControlSignature '')) {
        throw "Required token was ignored: $token"
    }
    if ((Get-ControlSignature ("value $token")) -ceq (Get-ControlSignature '值')) {
        throw "Missing token was accepted: $token"
    }
}
if ((Get-ControlSignature '(duration) (duration)') -ceq (Get-ControlSignature '(duration)')) {
    throw 'Duplicate placeholder removal was accepted.'
}

$invalid = @(
    Import-Csv -LiteralPath (Join-Path $PSScriptRoot 'translations_zh.csv') |
        Where-Object {
            [string]::IsNullOrWhiteSpace($_.translation_zh) -or
            (Get-ControlSignature $_.source_text) -cne (Get-ControlSignature $_.translation_zh)
        }
)
if ($invalid.Count -gt 0) {
    throw "CSV build validation failed for: $($invalid.key -join ', ')"
}
Write-Output 'Build control signature checks passed, including all CSV rows.'
