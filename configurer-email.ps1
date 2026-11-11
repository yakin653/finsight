# Active l'envoi reel des codes MarketPulse par Gmail (SMTP).
#
# - Le mot de passe d'application est lu en saisie masquee. Il n'est jamais affiche ni journalise :
#   il est ecrit uniquement dans .env (ignore par Git), d'ou docker compose le passe a l'API.
# - Seules les cinq lignes SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD et SMTP_FROM sont touchees.
#   Les autres lignes de .env (valeurs, commentaires, ordre, fins de ligne) restent identiques.
# - L'ancien .env est copie dans .env.bak (ignore par Git lui aussi) avant toute ecriture.
#
# Texte sans accents : compatible Windows PowerShell 5.1.
param([string]$Email = "yakinnmiri@gmail.com")

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root ".env"
$backup = Join-Path $root ".env.bak"
if (-not (Test-Path -LiteralPath $envFile)) { Write-Host ".env introuvable dans $root" -ForegroundColor Red; exit 1 }
if ($Email -notmatch '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$') {
    Write-Host "Adresse e-mail invalide. Rien n'a ete modifie." -ForegroundColor Red
    exit 1
}

# Saisie masquee. Google affiche le mot de passe par groupes de 4 : les espaces sont acceptes et retires.
$secure = Read-Host "Colle le mot de passe d'application Google (16 lettres, avec ou sans espaces), puis Entree" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
$plain = $plain -replace '\s', ''
if ($plain -notmatch '^[A-Za-z0-9]{16}$') {
    # Seule la longueur est affichee, jamais le contenu.
    Write-Host "Un mot de passe d'application fait exactement 16 lettres, sans autre signe (recu : $($plain.Length) caracteres hors espaces). Rien n'a ete modifie." -ForegroundColor Red
    exit 1
}

# Sauvegarde de l'ancien .env avant toute ecriture.
Copy-Item -LiteralPath $envFile -Destination $backup -Force

# Reecriture ligne a ligne : une ligne SMTP existante est remplacee a sa place, une ligne absente
# est ajoutee a la fin. Les fins de ligne d'origine (CRLF ou LF) sont conservees. UTF-8 sans BOM.
$text = [System.IO.File]::ReadAllText($envFile)
$newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
$tail = if ($text.Length -eq 0 -or $text.EndsWith("`n")) { $newline } else { "" }
$lines = New-Object System.Collections.Generic.List[string]
foreach ($line in ($text -split "\r?\n")) { $lines.Add($line) }
if ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq "") { $lines.RemoveAt($lines.Count - 1) }

$wanted = [ordered]@{
    SMTP_HOST     = "smtp.gmail.com"
    SMTP_PORT     = "587"
    SMTP_USER     = $Email
    SMTP_PASSWORD = $plain
    SMTP_FROM     = $Email
}
foreach ($key in $wanted.Keys) {
    $hits = @()
    for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -cmatch "^\s*$key=") { $hits += $i } }
    if ($hits.Count -eq 0) {
        $lines.Add("$key=$($wanted[$key])")
    } else {
        $lines[$hits[0]] = "$key=$($wanted[$key])"
        for ($j = $hits.Count - 1; $j -ge 1; $j--) { $lines.RemoveAt($hits[$j]) }
    }
}
[System.IO.File]::WriteAllText($envFile, ($lines -join $newline) + $tail, (New-Object System.Text.UTF8Encoding($false)))
$plain = $null
$wanted = $null
$lines = $null
Write-Host "1/3 .env mis a jour (envoi par Gmail). Ancien fichier : .env.bak" -ForegroundColor Green

Push-Location $root
docker compose up -d | Out-Null
$composeExit = $LASTEXITCODE
Pop-Location
if ($composeExit -ne 0) {
    Write-Host "docker compose a echoue : l'API n'a pas ete relancee. Lance : docker desktop restart, puis relance ce script." -ForegroundColor Red
    exit 1
}

$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 3
    try { Invoke-RestMethod http://127.0.0.1:8000/health -TimeoutSec 5 | Out-Null; $ready = $true; break } catch { }
}
if (-not $ready) { Write-Host "L'API ne repond pas. Lance : docker desktop restart, puis relance ce script." -ForegroundColor Red; exit 1 }

# L'API doit annoncer un envoi reel : sinon un test reussi ne prouverait que la boite de test locale.
$mode = ""
try { $mode = (Invoke-RestMethod http://127.0.0.1:8000/auth/providers -TimeoutSec 10).mail } catch { }
if ($mode -ne "smtp") {
    Write-Host "L'API n'a pas pris la nouvelle configuration (mode d'envoi : '$mode', attendu : 'smtp')." -ForegroundColor Red
    Write-Host "Lance : docker desktop restart, puis relance ce script."
    exit 1
}
Write-Host "2/3 API relancee, envoi reel actif." -ForegroundColor Green

# Envoi d'un message de test (sans code) : la cause exacte s'affiche si Gmail refuse.
docker exec finsight-backend python -m app.mailcheck $Email
if ($LASTEXITCODE -ne 0) {
    Write-Host "3/3 L'envoi a echoue (cause ci-dessus). Si ce sont les identifiants : cree un nouveau mot de passe" -ForegroundColor Red
    Write-Host "d'application sur https://myaccount.google.com/apppasswords puis relance ce script."
    exit 1
}
Write-Host "3/3 Message de test envoye a $Email. Regarde ta boite Gmail (et le dossier Spam)." -ForegroundColor Green
Write-Host "Tu peux maintenant utiliser Mot de passe oublie sur http://localhost:3000/forgot-password"
