"""Проверка корректности postings: декодируем postings.bin и сверяем с корпусом.

Процесс:
- читаем `index/vocab.tsv` и выбираем топ-K терминов по df
- для каждого терма декодируем блок в `index/postings.bin`
- сопоставляем номера документов с docid через `index/forward.tsv`
- находим текст документа в корпусе и повторно токенизируем
- проверяем, что терм действительно присутствует в токенах документа

Использование: python indexer/verify_index.py --index /path/to/index --corpus /path/to/corpus
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple


def read_varint_stream(b: bytes, pos: int = 0) -> Tuple[int, int]:
    """Декодировать varint из байтовой строки b, начиная с позиции pos. Вернуть (значение, новая_позиция)."""
    shift = 0
    result = 0
    while True:
        if pos >= len(b):
            raise EOFError('varint truncated')
        byte = b[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return result, pos


def decode_postings(block: bytes) -> List[int]:
    pos = 0
    df, pos = read_varint_stream(block, pos)
    docs = []
    prev = 0
    for _ in range(df):
        gap, pos = read_varint_stream(block, pos)
        doc = prev + gap
        docs.append(doc)
        prev = doc
    return docs


def load_forward(forward_path: Path) -> Dict[int, Tuple[str, str]]:
    m = {}
    with forward_path.open('r', encoding='utf-8') as fh:
        for line in fh:
            line = line.rstrip('\n')
            if not line:
                continue
            parts = line.split('\t', 2)
            if len(parts) < 3:
                continue
            docnum = int(parts[0])
            docid = parts[1]
            title = parts[2]
            m[docnum] = (docid, title)
    return m


def load_corpus_texts(corpus_dir: Path) -> Dict[str, str]:
    # Построить словарь docid -> текст
    docs = {}
    for p in sorted(corpus_dir.glob('part_*.tsv')):
        with p.open('r', encoding='utf-8') as fh:
            for line in fh:
                line = line.rstrip('\n')
                if not line:
                    continue
                parts = line.split('\t', 2)
                if len(parts) < 3:
                    continue
                docid, title, text = parts
                if docid.lower() in ('id', 'docid', 'document_id'):
                    continue
                docs[docid] = text
    return docs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', type=str, default='index')
    ap.add_argument('--corpus', type=str, default=str(Path('..') / 'corpus'))
    ap.add_argument('--stem', action='store_true', help='Apply project SimpleStemmer to tokens before checking (use for stemmed indexes)')
    ap.add_argument('--top', type=int, default=10, help='Number of top df terms to verify')
    args = ap.parse_args()

    idx = Path(args.index)
    corpus = Path(args.corpus)

    vocab_path = idx / 'vocab.tsv'
    postings_path = idx / 'postings.bin'
    forward_path = idx / 'forward.tsv'

    if not vocab_path.exists():
        print('vocab.tsv not found in', vocab_path)
        sys.exit(1)

    # прочитать vocab и собрать топ-термы по df
    terms: List[Tuple[str, int, int, int]] = []  # (term, df, offset, length)
    with vocab_path.open('r', encoding='utf-8') as vf:
        for line in vf:
            line = line.rstrip('\n')
            if not line:
                continue
            term, df_s, off_s, len_s = line.split('\t')
            terms.append((term, int(df_s), int(off_s), int(len_s)))

    terms_sorted = sorted(terms, key=lambda x: x[1], reverse=True)
    selected = terms_sorted[: args.top]

    forward = load_forward(forward_path)
    corpus_texts = load_corpus_texts(corpus)

    # импорт токенизатора: сначала обычный импорт, затем загрузка по пути как запасной вариант
    try:
        from corpus_analyze.tokenize import tokenize_text
    except Exception:
        # attempt to load by path relative to repo root
        try:
            import importlib.machinery
            import importlib.util
            repo_root = Path(__file__).resolve().parents[1]
            mod_path = repo_root / 'corpus_analyze' / 'tokenize.py'
            loader = importlib.machinery.SourceFileLoader('corpus_tokenize', str(mod_path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            tokenize_text = module.tokenize_text
        except Exception as e:
            print('Не удалось загрузить модуль токенизатора по пути:', e)
            sys.exit(1)

    # если пользователь попросил учитывать стемминг при проверке — загрузить локальный SimpleStemmer
    stemmer = None
    if args.stem:
        try:
            import importlib.machinery
            import importlib.util
            repo_root = Path(__file__).resolve().parents[1]
            mod_path = repo_root / 'indexer' / 'stemmer.py'
            loader = importlib.machinery.SourceFileLoader('verify_stemmer', str(mod_path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            SimpleStemmer = module.SimpleStemmer
            stemmer = SimpleStemmer()
            print('Verify: using SimpleStemmer for token normalization')
        except Exception as e:
            print('Verify: не удалось загрузить SimpleStemmer, продолжим без стемминга:', e)
            stemmer = None

    mismatches = 0
    total_checked = 0

    with postings_path.open('rb') as pb:
        for term, df, off, length in selected:
            pb.seek(off)
            block = pb.read(length)
            docs = decode_postings(block)
            print(f"Term: '{term}' df={df} postings_len={len(docs)}")
            if len(docs) != df:
                print(f"  WARNING: df mismatch (vocab {df} vs decoded {len(docs)})")

            # проверить, что терм присутствует в токенах документа
            for docnum in docs[:100]:
                total_checked += 1
                if docnum not in forward:
                    print(f"  docnum {docnum} not found in forward.tsv")
                    mismatches += 1
                    continue
                docid, title = forward[docnum]
                text = corpus_texts.get(docid)
                if text is None:
                    print(f"  docid {docid} (docnum {docnum}) not found in corpus parts")
                    mismatches += 1
                    continue
                toks = tokenize_text(text)
                # если проверяем стеммированный индекс, привести токены к стему
                if stemmer is not None:
                    stem_cache = {}
                    stemmed_toks = []
                    for t in toks:
                        if t in stem_cache:
                            stemmed_toks.append(stem_cache[t])
                        else:
                            try:
                                if hasattr(stemmer, 'stem'):
                                    s = stemmer.stem(t)
                                elif hasattr(stemmer, 'parse'):
                                    parsed = stemmer.parse(t)
                                    s = parsed[0].normal_form if parsed else t
                                else:
                                    s = t
                            except Exception:
                                s = t
                            stem_cache[t] = s
                            stemmed_toks.append(s)

                    if term not in stemmed_toks and term.lower() not in stemmed_toks:
                        print(f"  MISMATCH: term '{term}' не найден в docnum {docnum} (docid={docid})")
                        mismatches += 1
                else:
                    toks = [t.lower() for t in toks]
                    if term not in toks:
                        # попытка проверки с приведением регистра
                        if term.lower() not in toks:
                            print(f"  MISMATCH: term '{term}' не найден в docnum {docnum} (docid={docid})")
                            mismatches += 1

    print(f"Проверка завершена: total_checked={total_checked}, mismatches={mismatches}")


if __name__ == '__main__':
    main()
