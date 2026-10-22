# Génère les PDF de docs/ à partir des sources HTML de ce dossier, avec Microsoft Edge (sans
# dépendance à installer). Usage, depuis la racine du dépôt :
#   powershell -ExecutionPolicy Bypass -File docs\sources\generer-pdf.ps1
$ErrorActionPreference = "Stop"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$sources = $PSScriptRoot
$docs = Split-Path $sources -Parent
$profil = Join-Path $env:TEMP "simtis-edge-pdf"

$documents = @(
    @{ Source = "cahier-des-charges.html"; Pdf = "Cahier_des_charges_SIMTIS_V4.pdf" },
    @{ Source = "architecture-fonctionnelle.html"; Pdf = "Architecture_fonctionnelle_SIMTIS_V2.pdf" },
    @{ Source = "architecture-technique.html"; Pdf = "Architecture_technique_SIMTIS_V2.pdf" }
)

foreach ($doc in $documents) {
    $html = (Join-Path $sources $doc.Source) -replace "\\", "/"
    $pdf = Join-Path $docs $doc.Pdf
    Start-Process -FilePath $edge -Wait -ArgumentList @(
        "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        "--user-data-dir=$profil", "--print-to-pdf=`"$pdf`"", "file:///$html"
    )
    Write-Output ("{0} ({1:N0} Ko)" -f $doc.Pdf, ((Get-Item $pdf).Length / 1KB))
}
