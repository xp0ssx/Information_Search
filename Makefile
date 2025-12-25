VENV ?= myenv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: all venv install tokenize index serve test clean

all: venv install tokenize index

venv:
	@if [ ! -d "$(VENV)" ]; then \
		python3 -m venv "$(VENV)"; \
	fi
	@echo "Virtualenv ready: $(VENV)"
	@$(PIP) install --upgrade pip setuptools wheel

install: venv requirements.txt
	@echo "Installing python packages into $(VENV)"
	@$(PIP) install -r requirements.txt

tokenize: venv
	@echo "Running tokenizer (full corpus)"
	@$(PY) corpus_analyze/tokenize.py --full --outdir corpus_analyze --corpus corpus

index: venv
	@echo "Building full index (raw + stemmed optional)"
	@$(PY) indexer/build_index.py --full --outdir indexes --corpus corpus --force

serve: venv
	@echo "Starting web UI (Flask)"
	@$(PY) webapp/app.py --index indexes/raw --host 127.0.0.1 --port 8080

test: venv
	@echo "Running pytest"
	@$(PIP) install pytest || true
	@$(PY) -m pytest -q

clean:
	@echo "Cleaning generated artifacts"
	@rm -rf $(VENV)
	@rm -f corpus_analyze/sample_tokenized.tsv corpus_analyze/tokens_stats.json
	@rm -rf indexes/*
