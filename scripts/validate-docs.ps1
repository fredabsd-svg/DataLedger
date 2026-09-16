param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path -LiteralPath $Root).Path
$requiredDocuments = @(
    'README.md',
    'AGENTS.md',
    'docs/escopo.md',
    'docs/planos/DL-001-documentacao-inicial.md',
    '.github/pull_request_template.md'
)
$problems = [System.Collections.Generic.List[string]]::new()

foreach ($relativePath in $requiredDocuments) {
    if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot $relativePath) -PathType Leaf)) {
        $problems.Add("Arquivo obrigatório ausente: $relativePath")
    }
}

# A leitura estrita impede que bytes inválidos sejam silenciosamente substituídos.
$utf8 = [System.Text.UTF8Encoding]::new($false, $true)
$documents = @(Get-ChildItem -LiteralPath $repositoryRoot -Recurse -Force -File -Filter '*.md' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '[\\/](\.git|node_modules|\.venv|venv|__pycache__|\.pytest_cache|staticfiles|[^\\/]+\.(dist-info|egg-info))[\\/]' })

foreach ($document in $documents) {
    $displayPath = [System.IO.Path]::GetRelativePath($repositoryRoot, $document.FullName)
    try {
        $content = $utf8.GetString([System.IO.File]::ReadAllBytes($document.FullName))
    } catch {
        $problems.Add("UTF-8 inválido: $displayPath")
        continue
    }
    if ($content -notmatch '(?m)^# .+') {
        $problems.Add("Título principal ausente: $displayPath")
    }
    if ($content -match '(?m)[ \t]+\r?$') {
        $problems.Add("Espaço ao final de linha: $displayPath")
    }
    if (-not $content.EndsWith("`n")) {
        $problems.Add("Nova linha final ausente: $displayPath")
    }

    # Só links inline para caminhos locais são verificados; URLs e âncoras
    # dependem de validadores próprios e não devem gerar falsa homologação.
    $prose = [regex]::Replace($content, '(?ms)^```.*?^```[^\r\n]*', '')
    foreach ($match in [regex]::Matches($prose, '\[[^\]]+\]\(([^)]+)\)')) {
        $destination = $match.Groups[1].Value.Trim().Trim('<', '>')
        if ($destination -match '^[a-zA-Z][a-zA-Z0-9+.-]*:' -or $destination.StartsWith('#')) {
            continue
        }
        $destination = [Uri]::UnescapeDataString(($destination -split '[?#]', 2)[0])
        if ([string]::IsNullOrWhiteSpace($destination)) { continue }
        $target = Join-Path $document.DirectoryName $destination
        if (-not (Test-Path -LiteralPath $target)) {
            $problems.Add("Link relativo inexistente em ${displayPath}: $destination")
        }
    }
}

if ($problems.Count -gt 0) {
    throw ($problems -join [Environment]::NewLine)
}

Write-Output "Documentação válida: $($documents.Count) arquivos Markdown verificados."
