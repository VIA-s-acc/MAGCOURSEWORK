# Сборка курсовой и сопроводительного материала.
#   make build   — собрать оба PDF (dist/thesis.pdf и dist/supplement_proofs.pdf)
#   make clean   — удалить dist/

DIST = dist
XELATEX = xelatex -interaction=nonstopmode -output-directory=$(DIST)

.PHONY: build thesis supplement clean
build: thesis supplement

thesis:
	mkdir -p $(DIST)/chapters
	$(XELATEX) thesis.tex
	-biber --output-directory $(DIST) $(DIST)/thesis
	$(XELATEX) thesis.tex
	$(XELATEX) thesis.tex
	@echo "thesis.pdf:" && pdfinfo $(DIST)/thesis.pdf 2>/dev/null | grep Pages || true

supplement:
	mkdir -p $(DIST)
	$(XELATEX) supplement_proofs.tex
	$(XELATEX) supplement_proofs.tex
	$(XELATEX) supplement_proofs.tex
	@echo "supplement_proofs.pdf:" && pdfinfo $(DIST)/supplement_proofs.pdf 2>/dev/null | grep Pages || true

clean:
	rm -rf $(DIST)
