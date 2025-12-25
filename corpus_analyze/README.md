# Tokenization (короткая инструкция)

Этот каталог содержит инструменты для токенизации корпуса (`corpus/`).

Скрипт: `tokenize.py` — Unicode‑aware токенайзер (NFC, casefold), который
генерирует примеры токенизации и статистику.

Короткие команды (из корня репозитория):

```bash
# обработать первые 200 документов и сохранить результат в corpus_analyze/
python3 corpus_analyze/tokenize.py --sample 200 --outdir corpus_analyze --corpus corpus

# обработать весь корпус (весь набор part_*.tsv)
python3 corpus_analyze/tokenize.py --full --outdir corpus_analyze --corpus corpus
```

Выходы (в `corpus_analyze/`):

- `sample_tokenized.tsv` — таблица с тремя колонками: `docid`, `title`, `tokens` (первые 200 документов\*). 
- `tokens_stats.json` — статистика токенизации: число документов, общее число токенов, число уникальных терминов и топ‑термов.
