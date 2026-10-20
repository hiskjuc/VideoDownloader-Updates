# scripts/setup_updates_repo.ps1
$ErrorActionPreference = "Stop";

function Invoke-ExternalCommand {
    param ([scriptblock]$Command)
    $oldEAP = $ErrorActionPreference;
    $ErrorActionPreference = "Continue";
    try {
        $output = & $Command;
        $exitCode = $LASTEXITCODE;

        $outStr = "";
        if ($null -ne $output) {
            $outArray = @($output);
            $outStr = [System.String]::Join([System.Environment]::NewLine, $outArray);
        }

        return @{ Output = $outStr; ExitCode = $exitCode };
    } finally {
        $ErrorActionPreference = $oldEAP;
    }
}

Write-Host "--- Preparando Repositório de Atualizações (VideoDownloader-Updates) ---" -ForegroundColor Cyan;

if (-not (Get-Command -Name "git" -ErrorAction SilentlyContinue)) {
    Write-Host "ERRO: Git não encontrado. Instale com: winget install Git.Git" -ForegroundColor Red;
    exit 1;
}

if (-not (Get-Command -Name "gh" -ErrorAction SilentlyContinue)) {
    Write-Host "ERRO: GitHub CLI (gh) não encontrado. Instale com: winget install GitHub.cli" -ForegroundColor Red;
    exit 1;
}

$authCheck = Invoke-ExternalCommand { & gh auth status 2>&1 };
if ($authCheck.ExitCode -ne 0) {
    Write-Host "Você não está autenticado no GitHub CLI." -ForegroundColor Yellow;
    Write-Host "Execute 'gh auth login' no terminal, conclua a autenticação no navegador e rode este script novamente." -ForegroundColor Yellow;
    exit 1;
}

$userCheck = Invoke-ExternalCommand { & gh api user -q ".login" 2>&1 };
if ($userCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($userCheck.Output)) {
    Write-Host "ERRO: Não foi possível obter o usuário autenticado do GitHub." -ForegroundColor Red;
    exit 1;
}
$ghUser = $userCheck.Output.Trim();

$repoName = "VideoDownloader-Updates";
$fullRepo = "$ghUser/$repoName";
Write-Host "Conta autenticada: $ghUser" -ForegroundColor Green;

$repoCheck = Invoke-ExternalCommand { & gh api "repos/$fullRepo" 2>&1 };
if ($repoCheck.ExitCode -eq 0) {
    # Verifica se o repositório é público
    $isPrivateCheck = Invoke-ExternalCommand { & gh api "repos/$fullRepo" -q ".private" 2>&1 };
    if ($isPrivateCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($isPrivateCheck.Output)) {
        Write-Host "ERRO: Não foi possível verificar a visibilidade do repositório '$fullRepo'." -ForegroundColor Red;
        exit 1;
    }

    $isPrivate = $isPrivateCheck.Output.Trim().ToLowerInvariant();
    if ($isPrivate -eq "true") {
        Write-Host "ERRO: O repositório '$fullRepo' é privado. O atualizador exige um repositório público para distribuir releases sem token." -ForegroundColor Red;
        exit 1;
    } elseif ($isPrivate -ne "false") {
        Write-Host "ERRO: Valor inesperado ao consultar a visibilidade do repositório: '$isPrivate'." -ForegroundColor Red;
        exit 1;
    }

    $repoUrlCheck = Invoke-ExternalCommand { & gh repo view "$fullRepo" --json url -q ".url" 2>&1 };
    if ($repoUrlCheck.ExitCode -ne 0) {
        Write-Host "ERRO: Não foi possível obter a URL do repositório '$fullRepo'." -ForegroundColor Red;
        exit 1;
    }

    $repoUrl = $repoUrlCheck.Output.Trim();
    Write-Host "O repositório já existe e é público: $repoUrl" -ForegroundColor Cyan;
    Write-Host "Configure em version.py: GITHUB_OWNER = `"$ghUser`"" -ForegroundColor Yellow;
    exit 0;
}

$repoCheckText = $repoCheck.Output;
if ($repoCheckText -notmatch "(?i)(HTTP 404|Not Found)") {
    Write-Host "ERRO: Falha ao consultar '$fullRepo'. Verifique sua conexão ou permissões:" -ForegroundColor Red;
    Write-Host $repoCheckText -ForegroundColor Red;
    exit 1;
}

$confirm = Read-Host -Prompt "O repositório '$fullRepo' não existe. Deseja criá-lo agora como PÚBLICO (somente para releases)? [S/N]";
if ($confirm -notmatch "^[sS]$") {
    Write-Host "Operação cancelada pelo usuário. Nenhum repositório foi criado." -ForegroundColor Yellow;
    exit 0;
}

$baseTempPath = ([System.IO.Path]::GetTempPath());
$randomId = ([System.Guid]::NewGuid().ToString("N"));
$tempFolderName = "vd_updates_init_" + $randomId;
$tempRepoDir = Join-Path -Path "$baseTempPath" -ChildPath "$tempFolderName";
New-Item -ItemType Directory -Path "$tempRepoDir" -Force | Out-Null;

$pushedLocation = $false;

try {
    $readmePath = Join-Path -Path "$tempRepoDir" -ChildPath "README.md";
    $readmeLines = @(
        "# VideoDownloader Releases",
        "",
        "Este repositório hospeda exclusivamente os instaladores oficiais e manifestos de verificação (SHA-256) das versões públicas do **VideoDownloader**."
    );
    $readmeContent = ($readmeLines -join "`n") + "`n";
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false);
    [System.IO.File]::WriteAllText($readmePath, $readmeContent, $utf8NoBom);

    Push-Location -LiteralPath "$tempRepoDir";
    $pushedLocation = $true;

    $gitInit = Invoke-ExternalCommand { & git init 2>&1 };
    if ($gitInit.ExitCode -ne 0) { throw "Falha ao executar 'git init'.`n$($gitInit.Output)" }

    $gitBranch = Invoke-ExternalCommand { & git branch -M main 2>&1 };
    if ($gitBranch.ExitCode -ne 0) { throw "Falha ao definir a branch 'main'.`n$($gitBranch.Output)" }

    $gitConfName = Invoke-ExternalCommand { & git config --local user.name "$ghUser" 2>&1 };
    if ($gitConfName.ExitCode -ne 0) { throw "Falha ao configurar user.name local no repositório temporário.`n$($gitConfName.Output)" }

    $gitConfEmail = Invoke-ExternalCommand { & git config --local user.email "$ghUser@users.noreply.github.com" 2>&1 };
    if ($gitConfEmail.ExitCode -ne 0) { throw "Falha ao configurar user.email local no repositório temporário.`n$($gitConfEmail.Output)" }

    $gitAdd = Invoke-ExternalCommand { & git add -- "README.md" 2>&1 };
    if ($gitAdd.ExitCode -ne 0) { throw "Falha ao executar 'git add README.md'.`n$($gitAdd.Output)" }

    $gitCommit = Invoke-ExternalCommand { & git commit -m "chore: initialize updates distribution repository" 2>&1 };
    if ($gitCommit.ExitCode -ne 0) { throw "Falha ao criar o commit inicial do README.md.`n$($gitCommit.Output)" }

    $ghCreate = Invoke-ExternalCommand { & gh repo create "$fullRepo" --public --description "Distribuição oficial de instaladores e atualizações do VideoDownloader" --source "." --push 2>&1 };
    if ($ghCreate.ExitCode -ne 0) {
        Write-Host "ERRO: Falha ao criar o repositório no GitHub.`n$($ghCreate.Output)" -ForegroundColor Red;
        exit 1;
    }

    Pop-Location;
    $pushedLocation =$false;

    $createdUrlCheck = Invoke-ExternalCommand { & gh repo view "$fullRepo" --json url -q ".url" 2>&1 };
    if ($createdUrlCheck.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($createdUrlCheck.Output)) {
        Write-Host "ERRO: O repositório foi criado, mas não foi possível consultar sua URL final." -ForegroundColor Red;
        exit 1;
    }
    $createdUrl =$createdUrlCheck.Output.Trim();

    Write-Host "Repositório público criado com sucesso: $createdUrl" -ForegroundColor Green;
    Write-Host "Agora defina GITHUB_OWNER = `"$ghUser`" em version.py." -ForegroundColor Yellow;
}
finally {
    if ($pushedLocation) {
        Pop-Location;
    }
    if (Test-Path -LiteralPath "$tempRepoDir") {
        Remove-Item -LiteralPath "$tempRepoDir" -Recurse -Force -ErrorAction SilentlyContinue;
    }
}