# ============================================================================
# Makefile для сборки магистерской курсовой ВМК МГУ
# Главный исходник: tex/thesis.tex (XeLaTeX + biber для ГОСТ-библиографии).
# Результат сборки:  dist/thesis.pdf
#
# Зависимости:
#   - TeX Live 2023+ или MacTeX с пакетами: fontspec, polyglossia,
#     biblatex, biblatex-gost (см. установку ниже).
#   - biber (входит в TeX Live).
#   - Шрифты: Times New Roman, Arial, Courier New (в macOS — из коробки).
#
# Установка отсутствующих пакетов:
#   tlmgr install biblatex-gost polyglossia titlesec setspace tocloft \
#                 caption booktabs longtable enumitem microtype mathtools \
#                 bm xcolor hyperref minted listings
#
# Использование:
#   make build      — собрать PDF (полный 3-проходный цикл: xelatex/biber/xelatex/xelatex)
#   make quick      — один проход xelatex (для быстрой проверки шаблона)
#   make watch      — собрать и пересобирать при изменениях (требует latexmk)
#   make clean      — удалить временные файлы из dist/
#   make distclean  — удалить всё в dist/
# ============================================================================

LATEX        := xelatex
LATEX_FLAGS  := -interaction=nonstopmode -halt-on-error -file-line-error -shell-escape
BIBER        := biber
LATEXMK      := latexmk

SRC_DIR  := tex
SRC      := $(SRC_DIR)/thesis.tex
OUT_DIR  := dist
OUT_PDF  := $(OUT_DIR)/thesis.pdf
JOBNAME  := thesis

# Принудительно меняем рабочую директорию на tex/, чтобы относительные пути
# (chapters/, figures/, bib/) разрешались правильно.
.PHONY: all build quick watch clean distclean deps help

all: build

build: $(OUT_DIR)
	@echo "==> [0/4] mkdir для aux-подпапок (chapters/)"
	mkdir -p $(OUT_DIR)/chapters
	@echo "==> [1/4] xelatex (1st pass)"
	cd $(SRC_DIR) && $(LATEX) $(LATEX_FLAGS) -jobname=$(JOBNAME) -output-directory=../$(OUT_DIR) thesis.tex
	@echo "==> [2/4] biber"
	cd $(SRC_DIR) && $(BIBER) --output-directory=../$(OUT_DIR) $(JOBNAME)
	@echo "==> [3/4] xelatex (2nd pass)"
	cd $(SRC_DIR) && $(LATEX) $(LATEX_FLAGS) -jobname=$(JOBNAME) -output-directory=../$(OUT_DIR) thesis.tex
	@echo "==> [4/4] xelatex (3rd pass — финализация ссылок)"
	cd $(SRC_DIR) && $(LATEX) $(LATEX_FLAGS) -jobname=$(JOBNAME) -output-directory=../$(OUT_DIR) thesis.tex
	@echo ""
	@echo "✓ PDF собран: $(OUT_PDF)"
	@if [ -f $(OUT_PDF) ]; then \
		echo "  Размер: $$(du -h $(OUT_PDF) | cut -f1)"; \
		echo "  Страниц: $$(pdfinfo $(OUT_PDF) 2>/dev/null | grep Pages | awk '{print $$2}')"; \
	fi

quick: $(OUT_DIR)
	@echo "==> xelatex (одиночный проход — без biber)"
	cd $(SRC_DIR) && $(LATEX) $(LATEX_FLAGS) -jobname=$(JOBNAME) -output-directory=../$(OUT_DIR) thesis.tex

watch: $(OUT_DIR)
	@command -v $(LATEXMK) >/dev/null 2>&1 || { echo "ERROR: latexmk не установлен. Установите: tlmgr install latexmk"; exit 1; }
	cd $(SRC_DIR) && $(LATEXMK) -xelatex -pvc -interaction=nonstopmode -jobname=$(JOBNAME) -output-directory=../$(OUT_DIR) thesis.tex

clean:
	@echo "==> Очистка временных файлов LaTeX"
	rm -rf $(OUT_DIR)/*.aux $(OUT_DIR)/*.log $(OUT_DIR)/*.toc $(OUT_DIR)/*.bbl $(OUT_DIR)/*.bcf \
	       $(OUT_DIR)/*.run.xml $(OUT_DIR)/*.blg $(OUT_DIR)/*.out $(OUT_DIR)/*.fls \
	       $(OUT_DIR)/*.fdb_latexmk $(OUT_DIR)/*.synctex.gz $(OUT_DIR)/chapters

distclean:
	@echo "==> Удаление всего в $(OUT_DIR)/"
	rm -rf $(OUT_DIR)

$(OUT_DIR):
	mkdir -p $(OUT_DIR)

deps:
	@echo "==> Проверка инструментов сборки"
	@for tool in $(LATEX) $(BIBER); do \
		if command -v $$tool >/dev/null 2>&1; then \
			echo "  ✓ $$tool: $$($$tool --version 2>&1 | head -1)"; \
		else \
			echo "  ✗ $$tool: НЕ НАЙДЕН"; \
		fi; \
	done
	@echo "==> Проверка LaTeX-пакетов (через kpsewhich)"
	@for pkg in fontspec polyglossia biblatex titlesec setspace; do \
		if kpsewhich $$pkg.sty >/dev/null 2>&1; then \
			echo "  ✓ $$pkg"; \
		else \
			echo "  ✗ $$pkg — установите: tlmgr install $$pkg"; \
		fi; \
	done
	@if kpsewhich russian-gost.lbx >/dev/null 2>&1; then \
		echo "  ✓ biblatex-gost (russian-gost.lbx)"; \
	else \
		echo "  ✗ biblatex-gost — установите: tlmgr --usermode install biblatex-gost"; \
	fi

help:
	@echo "Доступные цели:"
	@echo "  make build      — полная сборка PDF (xelatex+biber+xelatex×2)"
	@echo "  make quick      — один проход xelatex (быстро, без библиографии)"
	@echo "  make watch      — авто-пересборка при изменениях (нужен latexmk)"
	@echo "  make clean      — удалить временные файлы"
	@echo "  make distclean  — удалить весь $(OUT_DIR)/"
	@echo "  make deps       — проверить наличие инструментов и пакетов"
