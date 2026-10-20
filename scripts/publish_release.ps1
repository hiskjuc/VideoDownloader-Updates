# scripts/publish_release.ps1
param (
    [Parameter(Mandatory=$true)][string]$Version,
    [Parameter(Mandatory=$true)][string]$Notes,
    [Parameter(Mandatory=$true)][string]$InstallerPath
)

$ErrorActionPreference = "Stop";

function Invoke-ExternalCommand {
    param ([scriptblock]$Command)
    $oldEAP =$ErrorActionPreference;
    $ErrorActionPreference = "Continue";
    try {
        $output = &$Command;
        $exitCode =$LASTEXITCODE;

        $outStr = "";
        if ($null -ne$output) {
            $outArray = @($output);
            $outStr = [System.String]::Join([System.Environment]::NewLine,$outArray);
        }

        return @{ Output = $outStr; ExitCode =$exitCode };
    } finally {
        $ErrorActionPreference =$oldEAP;
    }
}

if (-not (Get-Command -Name "gh" -ErrorAction SilentlyContinue)) {
    Write-Host "ERRO: GitHub CLI (gh) não encontrado. Instale com: winget install GitHub.cli" -ForegroundColor Red;
    exit 1;
}

$cleanVersion =$Version.Trim();
if ($cleanVersion.StartsWith("v") -or $cleanVersion.StartsWith("V")) {
    $cleanVersion =$cleanVersion.Substring(1).Trim();
}

if ($cleanVersion -notmatch "^\d+\.\d+\.\d+$") {
    Write-Host "ERRO: Versão inválida '$Version'. Use o formato semântico X.Y.Z (ex: 1.1.0)." -ForegroundColor Red;
    exit 1;
}

$tag = "v$cleanVersion";
Write-Host "--- Preparando publicação da release $tag ---" -ForegroundColor Cyan;

# 1. Validar arquivo do instalador
if (-not (Test-Path -LiteralPath "$InstallerPath" -PathType Leaf)) {
    Write-Host "ERRO: O instalador não foi encontrado em: $InstallerPath" -ForegroundColor Red;
    exit 1;
}

$installerItem = Get-Item -LiteralPath "$InstallerPath";
if ($installerItem.Name -cne "VideoDownloader_Setup.exe") {
    Write-Host "ERRO: O arquivo do instalador deve se chamar exatamente 'VideoDownloader_Setup.exe' (recebido: '$($installerItem.Name)')." -ForegroundColor Red;
    exit 1;
}

if ($installerItem.Length -le 0) {
    Write-Host "ERRO: O arquivo VideoDownloader_Setup.exe está vazio." -ForegroundColor Red;
    exit 1;
}

# 2. Conferir consistência com version.py
if (-not (Test-Path -LiteralPath "version.py" -PathType Leaf)) {
    Write-Host "ERRO: Arquivo version.py não encontrado na raiz do projeto." -ForegroundColor Red;
    exit 1;
}

$versionPyContent = Get-Content -LiteralPath "version.py" -Raw -Encoding UTF8;
if ($versionPyContent -notmatch '__version__\s*=\s*"([^"]+)"') {
    Write-Host "ERRO: Não foi possível ler __version__ em version.py." -ForegroundColor Red;
    exit 1;
}
$pyVersion =$matches[1].Trim();

$cfgOwner = "";
if ($versionPyContent -match 'GITHUB_OWNER\s*=\s*"([^"]*)"') {
    $cfgOwner =$matches[1].Trim();
}

if ([string]::IsNullOrWhiteSpace($cfgOwner) -or$cfgOwner -eq "SEU_USUARIO") {
    Write-Host "ERRO: GITHUB_OWNER não está configurado corretamente em version.py. Valor lido: '$cfgOwner'." -ForegroundColor Red;
    exit 1;
}

$cfgRepo = "VideoDownloader-Updates";
if ($versionPyContent -match 'GITHUB_REPO\s*=\s*"([^"]+)"') {
    $cfgRepo =$matches[1].Trim();
}

if ($pyVersion -ne$cleanVersion) {
    Write-Host "ERRO: Divergência de versão! Parâmetro informado ($cleanVersion) != version.py ($pyVersion)." -ForegroundColor Red;
    exit 1;
}

# 3. Conferir consistência com o arquivo do Inno Setup (.iss)
$issCandidates = @("installer\VideoDownloader.iss", "installer\VideoDownloader_Setup.iss");
$issFile =$null;
$issCandidates | ForEach-Object {
    $candidate =$_;
    if (-not $issFile -and (Test-Path -LiteralPath "$candidate" -PathType Leaf)) {
        $issFile =$candidate;
    }
};

if (-not $issFile) {
    Write-Host "ERRO: Arquivo .iss do instalador não encontrado na pasta installer\." -ForegroundColor Red;
    exit 1;
}

$issContent = Get-Content -LiteralPath "$issFile" -Raw -Encoding UTF8;
if ($issContent -notmatch '(?m)^AppVersion\s*=\s*([^\r\n]+)') {
    Write-Host "ERRO: Diretiva AppVersion não encontrada em $issFile." -ForegroundColor Red;
    exit 1;
}
$issVersion =$matches[1].Trim();

if ($issVersion -ne$cleanVersion) {
    Write-Host "ERRO: Divergência de versão! version.py ($cleanVersion) != $issFile AppVersion ($issVersion)." -ForegroundColor Red;
    exit 1;
}

# 4. Verificar autenticação e repositório no GitHub CLI
$authCheck = Invoke-ExternalCommand { & gh auth status 2>&1 };
if ($authCheck.ExitCode -ne 0) {
    Write-Host "ERRO: GitHub CLI não autenticado. Execute 'gh auth login'." -ForegroundColor Red;
    exit 1;
}

$userCheck = Invoke-ExternalCommand { & gh api user -q ".login" 2>&1 };
if ($userCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($userCheck.Output)) {
    Write-Host "ERRO: Não foi possível obter o usuário autenticado no GitHub." -ForegroundColor Red;
    exit 1;
}
$ghUser =$userCheck.Output.Trim();

if ($cfgOwner.ToLowerInvariant() -ne$ghUser.ToLowerInvariant()) {
    Write-Host "ERRO: GITHUB_OWNER configurado em version.py ('$cfgOwner') difere da conta autenticada no gh ('$ghUser')." -ForegroundColor Red;
    exit 1;
}

$fullRepo = "$ghUser/$cfgRepo";
$repoCheck = Invoke-ExternalCommand { & gh api "repos/$fullRepo" 2>&1 };
if ($repoCheck.ExitCode -ne 0) {
    Write-Host "ERRO: O repositório '$fullRepo' não existe ou não está acessível:" -ForegroundColor Red;
    Write-Host $repoCheck.Output -ForegroundColor Red;
    exit 1;
}

$isPrivateCheck = Invoke-ExternalCommand { & gh api "repos/$fullRepo" -q ".private" 2>&1 };
if ($isPrivateCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($isPrivateCheck.Output)) {
    Write-Host "ERRO: Não foi possível verificar a visibilidade do repositório '$fullRepo'." -ForegroundColor Red;
    exit 1;
}
$isPrivate =$isPrivateCheck.Output.Trim().ToLowerInvariant();
if ($isPrivate -eq "true") {
    Write-Host "ERRO: O repositório '$fullRepo' é privado. O atualizador exige um repositório público para distribuir atualizações." -ForegroundColor Red;
    exit 1;
} elseif ($isPrivate -ne "false") {
    Write-Host "ERRO: Valor inesperado ao consultar a visibilidade do repositório: '$isPrivate'." -ForegroundColor Red;
    exit 1;
}

# 5. Garantir que a release e a tag ainda não existem (diferenciando 404 de falhas de rede)
$releaseLookup = Invoke-ExternalCommand { & gh api "repos/$fullRepo/releases/tags/$tag" 2>&1 };
if ($releaseLookup.ExitCode -eq 0) {
    Write-Host "ERRO: Já existe uma release publicada para a tag $tag em$fullRepo." -ForegroundColor Red;
    exit 1;
}
if ($releaseLookup.Output -notmatch "(?i)(HTTP 404|Not Found)") {
    Write-Host "ERRO: Falha ao consultar releases existentes em ${fullRepo}:" -ForegroundColor Red;
    Write-Host $releaseLookup.Output -ForegroundColor Red;
    exit 1;
}

$tagLookup = Invoke-ExternalCommand { & gh api "repos/$fullRepo/git/ref/tags/$tag" 2>&1 };
if ($tagLookup.ExitCode -eq 0) {
    Write-Host "ERRO: A tag Git $tag já existe no repositório $fullRepo." -ForegroundColor Red;
    exit 1;
}
if ($tagLookup.Output -notmatch "(?i)(HTTP 404|Not Found)") {
    Write-Host "ERRO: Falha ao verificar tags existentes em ${fullRepo}:" -ForegroundColor Red;
    Write-Host $tagLookup.Output -ForegroundColor Red;
    exit 1;
}

# 6. Preparar notas da release e manifesto SHA-256 em diretórios temporários exclusivos
$baseTempPath = ([System.IO.Path]::GetTempPath());
$notesRandomId = ([System.Guid]::NewGuid().ToString("N"));
$checksumRandomId = ([System.Guid]::NewGuid().ToString("N"));

$notesFileName = "vd_notes_" + $notesRandomId + ".md";
$checksumFolderName = "vd_checksum_" + $checksumRandomId;

$notesTempFile = Join-Path -Path "$baseTempPath" -ChildPath "$notesFileName";
$checksumTempDir = Join-Path -Path "$baseTempPath" -ChildPath "$checksumFolderName";
New-Item -ItemType Directory -Path "$checksumTempDir" -Force | Out-Null;
$checksumFile = Join-Path -Path "$checksumTempDir" -ChildPath "checksums.txt";

try {
    if (Test-Path -LiteralPath "$Notes" -PathType Leaf) {
        $notesText = Get-Content -LiteralPath "$Notes" -Raw -Encoding UTF8;
    } else {
        $notesText = $Notes;
    }

    if ([string]::IsNullOrWhiteSpace($notesText)) {
        Write-Host "ERRO: As notas da release não podem estar vazias." -ForegroundColor Red;
        exit 1;
    }

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false);
    [System.IO.File]::WriteAllText($notesTempFile, $notesText, $utf8NoBom);

    # 7. Gerar checksums.txt em UTF-8 sem BOM
    $hash = (Get-FileHash -LiteralPath "$($installerItem.FullName)" -Algorithm SHA256).Hash.ToLowerInvariant();
    $checksumLine = "$hash  VideoDownloader_Setup.exe`n";
    [System.IO.File]::WriteAllText($checksumFile, $checksumLine, $utf8NoBom);

    Write-Host "SHA-256 calculado: $hash" -ForegroundColor Gray;
    Write-Host "Publicando release $tag em $fullRepo..." -ForegroundColor Cyan;

    $releaseCreate = Invoke-ExternalCommand { & gh release create "$tag" "$($installerItem.FullName)" "$checksumFile" --repo "$fullRepo" --title "VideoDownloader $tag" --notes-file "$notesTempFile" 2>&1 };
    if ($releaseCreate.ExitCode -ne 0) {
        Write-Host "ERRO: O comando 'gh release create' falhou:`n$($releaseCreate.Output)" -ForegroundColor Red;
        exit 1;
    }

    $releaseUrlCheck = Invoke-ExternalCommand { & gh release view "$tag" --repo "$fullRepo" --json url -q ".url" 2>&1 };
    if ($releaseUrlCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($releaseUrlCheck.Output)) {
        Write-Host "AVISO: A release foi criada com sucesso, mas a API falhou ao recuperar o link de confirmação." -ForegroundColor Yellow;
        Write-Host "Por favor, verifique manualmente no GitHub se a tag '$tag' está visível." -ForegroundColor Yellow;
    } else {
        $releaseUrl =$releaseUrlCheck.Output.Trim();
        Write-Host "Release publicada e verificada com sucesso!" -ForegroundColor Green;
        Write-Host "URL: $releaseUrl" -ForegroundColor Green;
    }
}
finally {
    if (Test-Path -LiteralPath "$notesTempFile") {
        Remove-Item -LiteralPath "$notesTempFile" -Force -ErrorAction SilentlyContinue;
    }
    if (Test-Path -LiteralPath "$checksumTempDir") {
        Remove-Item -LiteralPath "$checksumTempDir" -Recurse -Force -ErrorAction SilentlyContinue;
    }
}