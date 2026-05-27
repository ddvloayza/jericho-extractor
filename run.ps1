# ─────────────────────────────────────────────────────────────────────────────
#  Jericho Extractor — run.ps1
#  Usage:  .\run.ps1 <comando> [cuenta]
#
#  Ejemplos:
#    .\run.ps1 help
#    .\run.ps1 extract
#    .\run.ps1 reports Portal-Prod
#    .\run.ps1 reports-all
#    .\run.ps1 audit Portal-Prod
#    .\run.ps1 audit-all
#    .\run.ps1 diagrams Portal-Prod
#    .\run.ps1 diagrams-all
#    .\run.ps1 all Portal-Prod
#    .\run.ps1 all-accounts
#    .\run.ps1 clean Portal-Prod
#    .\run.ps1 clean-all
# ─────────────────────────────────────────────────────────────────────────────

param(
    [string]$Command = "help",
    [string]$Account = "Portal-Prod",
    [string]$Config  = "config.json"
)

$PYTHON    = "python"
$OUTPUT    = "output"
$ACCOUNTS  = @("Analytics-Prod", "Intelica-Network", "Interchange-Prod", "Portal-Prod")

function Print-Help {
    Write-Host ""
    Write-Host "  Jericho Extractor" -ForegroundColor Cyan
    Write-Host "  ──────────────────────────────────────────────────────" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Extraccion:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 extract              Extrae inventario (vars de entorno)"
    Write-Host "    .\run.ps1 extract-all          Extrae con config.json (multi-cuenta)"
    Write-Host ""
    Write-Host "  Reportes HTML:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 reports    [cuenta]  Genera todos los HTMLs"
    Write-Host "    .\run.ps1 reports-all           Genera HTMLs para todas las cuentas"
    Write-Host "    .\run.ps1 audit      [cuenta]  Solo audit_report.html"
    Write-Host "    .\run.ps1 audit-all             Audit para todas las cuentas"
    Write-Host ""
    Write-Host "  Diagramas draw.io:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 diagrams   [cuenta]  Genera network_diagram.drawio"
    Write-Host "    .\run.ps1 diagrams-all          draw.io para todas las cuentas"
    Write-Host ""
    Write-Host "  Todo junto:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 all        [cuenta]  Reports + diagrams"
    Write-Host "    .\run.ps1 all-accounts          Reports + diagrams para todas"
    Write-Host ""
    Write-Host "  Limpieza:" -ForegroundColor Yellow
    Write-Host "    .\run.ps1 clean      [cuenta]  Borra reports/ y diagrams/"
    Write-Host "    .\run.ps1 clean-all             Limpia todas las cuentas"
    Write-Host ""
    Write-Host "  Cuenta por defecto: Portal-Prod" -ForegroundColor DarkGray
    Write-Host ""
}

function Run-Extract {
    Write-Host "[extract] Extrayendo con variables de entorno..." -ForegroundColor Cyan
    & $PYTHON main.py
}

function Run-ExtractAll {
    Write-Host "[extract-all] Extrayendo con $Config..." -ForegroundColor Cyan
    & $PYTHON main.py --config $Config
}

function Run-Reports($acc) {
    Write-Host "[reports] Generando reportes para $acc..." -ForegroundColor Cyan
    & $PYTHON visualize.py --account $acc --format html
}

function Run-ReportsAll {
    Write-Host "[reports-all] Generando reportes para todas las cuentas..." -ForegroundColor Cyan
    foreach ($acc in $ACCOUNTS) {
        Write-Host "  -> $acc" -ForegroundColor DarkGray
        & $PYTHON visualize.py --account $acc --format html
    }
}

function Run-Audit($acc) {
    Write-Host "[audit] Generando audit_report.html para $acc..." -ForegroundColor Cyan
    & $PYTHON visualize.py --account $acc --format html --only audit
}

function Run-AuditAll {
    Write-Host "[audit-all] Generando audit_report.html para todas las cuentas..." -ForegroundColor Cyan
    foreach ($acc in $ACCOUNTS) {
        Write-Host "  -> $acc" -ForegroundColor DarkGray
        & $PYTHON visualize.py --account $acc --format html --only audit
    }
}

function Run-Diagrams($acc) {
    Write-Host "[diagrams] Generando network_diagram.drawio para $acc..." -ForegroundColor Cyan
    & $PYTHON diagram_generator.py --account $acc
}

function Run-DiagramsAll {
    Write-Host "[diagrams-all] Generando .drawio para todas las cuentas..." -ForegroundColor Cyan
    foreach ($acc in $ACCOUNTS) {
        Write-Host "  -> $acc" -ForegroundColor DarkGray
        & $PYTHON diagram_generator.py --account $acc
    }
}

function Run-All($acc) {
    Run-Reports $acc
    Run-Diagrams $acc
    Write-Host "[all] Completado para $acc" -ForegroundColor Green
    Write-Host "  Reports  -> $OUTPUT\$acc\reports\" -ForegroundColor DarkGray
    Write-Host "  Diagrams -> $OUTPUT\$acc\diagrams\" -ForegroundColor DarkGray
}

function Run-AllAccounts {
    Run-ReportsAll
    Run-DiagramsAll
    Write-Host "[all-accounts] Completado para todas las cuentas" -ForegroundColor Green
}

function Run-Clean($acc) {
    Write-Host "[clean] Limpiando $acc..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force "$OUTPUT\$acc\reports"  -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force "$OUTPUT\$acc\diagrams" -ErrorAction SilentlyContinue
    Write-Host "[clean] Listo" -ForegroundColor Green
}

function Run-CleanAll {
    Write-Host "[clean-all] Limpiando todas las cuentas..." -ForegroundColor Yellow
    foreach ($acc in $ACCOUNTS) {
        Write-Host "  -> $acc" -ForegroundColor DarkGray
        Remove-Item -Recurse -Force "$OUTPUT\$acc\reports"  -ErrorAction SilentlyContinue
        Remove-Item -Recurse -Force "$OUTPUT\$acc\diagrams" -ErrorAction SilentlyContinue
    }
    Write-Host "[clean-all] Listo" -ForegroundColor Green
}

# ── Dispatcher ────────────────────────────────────────────────────────────────
switch ($Command) {
    "help"          { Print-Help }
    "extract"       { Run-Extract }
    "extract-all"   { Run-ExtractAll }
    "reports"       { Run-Reports $Account }
    "reports-all"   { Run-ReportsAll }
    "audit"         { Run-Audit $Account }
    "audit-all"     { Run-AuditAll }
    "diagrams"      { Run-Diagrams $Account }
    "diagrams-all"  { Run-DiagramsAll }
    "all"           { Run-All $Account }
    "all-accounts"  { Run-AllAccounts }
    "clean"         { Run-Clean $Account }
    "clean-all"     { Run-CleanAll }
    default {
        Write-Host "Comando desconocido: $Command" -ForegroundColor Red
        Print-Help
    }
}
