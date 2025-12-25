Короткая инструкция

Запускать из корня репозитория.

1) Собрать полный индекс без стемминга (raw):

```bash
python3 indexer/build_index.py --full --outdir indexes --corpus corpus
```

2) Собрать полный стеммированный индекс (SimpleStemmer):

```bash
python3 indexer/build_index.py --full --stem --outdir indexes --corpus corpus
```

Верификация:

1) Верифицировать raw‑индекс (проверить top 20 терминов):

```bash
python3 indexer/verify_index.py --index indexes/raw --corpus corpus --top 20
```

2) Верифицировать стеммированный индекс (применить тот же SimpleStemmer):

```bash
python3 indexer/verify_index.py --index indexes/stemmed --corpus corpus --top 20 --stem
```
