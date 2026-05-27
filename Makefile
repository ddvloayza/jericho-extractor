# ─────────────────────────────────────────────────────────────────────────────
#  Jericho Extractor — Makefile
#  Usage:  make <target> [ACCOUNT=<name>]
# ─────────────────────────────────────────────────────────────────────────────

PYTHON     := python
OUTPUT_DIR := output
ACCOUNTS   := Analytics-Prod Intelica-Network Interchange-Prod Portal-Prod

# Default account for single-account targets
ACCOUNT ?= Portal-Prod

.PHONY: help \
        extract extract-all \
        reports reports-all \
        diagrams diagrams-all \
        all all-accounts \
        clean clean-reports clean-diagrams clean-all \
        open

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Jericho Extractor"
	@echo "  ────────────────────────────────────────────────────────"
	@echo ""
	@echo "  Extraccion:"
	@echo "    make extract              Extrae inventario (usa vars de entorno)"
	@echo "    make extract-all          Extrae con config.json (multi-cuenta)"
	@echo ""
	@echo "  Reportes HTML:"
	@echo "    make reports              Genera todos los HTMLs  (ACCOUNT=Portal-Prod)"
	@echo "    make reports-all          Genera HTMLs para todas las cuentas"
	@echo "    make audit                Solo audit_report.html  (ACCOUNT=Portal-Prod)"
	@echo ""
	@echo "  Diagramas draw.io:"
	@echo "    make diagrams             Genera .drawio         (ACCOUNT=Portal-Prod)"
	@echo "    make diagrams-all         Genera .drawio para todas las cuentas"
	@echo ""
	@echo "  Todo junto:"
	@echo "    make all                  Reports + diagrams     (ACCOUNT=Portal-Prod)"
	@echo "    make all-accounts         Reports + diagrams para todas las cuentas"
	@echo ""
	@echo "  Limpieza:"
	@echo "    make clean-reports        Borra reports/         (ACCOUNT=Portal-Prod)"
	@echo "    make clean-diagrams       Borra diagrams/        (ACCOUNT=Portal-Prod)"
	@echo "    make clean                Borra reports/ y diagrams/ (ACCOUNT=Portal-Prod)"
	@echo "    make clean-all            Borra reports/ y diagrams/ de todas las cuentas"
	@echo ""
	@echo "  Opciones:"
	@echo "    ACCOUNT=<nombre>          Cuenta a usar (default: Portal-Prod)"
	@echo "    CONFIG=config.json        Archivo de config para extract-all"
	@echo ""

# ── Extraccion ────────────────────────────────────────────────────────────────
extract:
	@echo "[extract] Extrayendo con variables de entorno..."
	$(PYTHON) main.py

extract-all:
	@echo "[extract-all] Extrayendo con $(CONFIG)..."
	$(PYTHON) main.py --config $(CONFIG)

# ── Reportes HTML ─────────────────────────────────────────────────────────────
reports:
	@echo "[reports] Generando todos los reportes para $(ACCOUNT)..."
	$(PYTHON) visualize.py --account $(ACCOUNT) --format html

reports-all:
	@echo "[reports-all] Generando reportes para todas las cuentas..."
	@for account in $(ACCOUNTS); do \
		echo "  -> $$account"; \
		$(PYTHON) visualize.py --account $$account --format html; \
	done

audit:
	@echo "[audit] Generando audit_report.html para $(ACCOUNT)..."
	$(PYTHON) visualize.py --account $(ACCOUNT) --format html --only audit

audit-all:
	@echo "[audit-all] Generando audit_report.html para todas las cuentas..."
	@for account in $(ACCOUNTS); do \
		echo "  -> $$account"; \
		$(PYTHON) visualize.py --account $$account --format html --only audit; \
	done

# ── Diagramas draw.io ─────────────────────────────────────────────────────────
diagrams:
	@echo "[diagrams] Generando network_diagram.drawio para $(ACCOUNT)..."
	$(PYTHON) diagram_generator.py --account $(ACCOUNT)

diagrams-all:
	@echo "[diagrams-all] Generando .drawio para todas las cuentas..."
	@for account in $(ACCOUNTS); do \
		echo "  -> $$account"; \
		$(PYTHON) diagram_generator.py --account $$account; \
	done

# ── Todo junto ────────────────────────────────────────────────────────────────
all: reports diagrams
	@echo "[all] Completado para $(ACCOUNT)"
	@echo "  Reports  -> $(OUTPUT_DIR)/$(ACCOUNT)/reports/"
	@echo "  Diagrams -> $(OUTPUT_DIR)/$(ACCOUNT)/diagrams/"

all-accounts: reports-all diagrams-all
	@echo "[all-accounts] Completado para todas las cuentas"

# ── Limpieza ──────────────────────────────────────────────────────────────────
clean-reports:
	@echo "[clean-reports] Borrando $(OUTPUT_DIR)/$(ACCOUNT)/reports/..."
	@rm -rf $(OUTPUT_DIR)/$(ACCOUNT)/reports/

clean-diagrams:
	@echo "[clean-diagrams] Borrando $(OUTPUT_DIR)/$(ACCOUNT)/diagrams/..."
	@rm -rf $(OUTPUT_DIR)/$(ACCOUNT)/diagrams/

clean: clean-reports clean-diagrams
	@echo "[clean] Limpiado $(ACCOUNT)"

clean-all:
	@echo "[clean-all] Limpiando todas las cuentas..."
	@for account in $(ACCOUNTS); do \
		echo "  -> $$account"; \
		rm -rf $(OUTPUT_DIR)/$$account/reports/; \
		rm -rf $(OUTPUT_DIR)/$$account/diagrams/; \
	done
	@echo "[clean-all] Listo"
