"""Построение простого обратного индекса из `corpus/part_*.tsv`.

Файлы, создаваемые в папке индекса:
- vocab.tsv        : term\tdf\toffset\tlength (смещение/длина в postings.bin)
- postings.bin     : бинарные блоки для каждого терма: varint(df) затем varint(gap) ...
- forward.tsv      : docnum\tdocid\ttitle
- doclens.json     : {docnum: token_count}
- meta.json        : метаданные сборки

Скрипт поддерживает параметр --sample N для быстрой обработки первых N документов.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def write_varint(f, value: int) -> int:
    """Записать беззнаковый varint (аналог LEB128). Возвращает число записанных байт."""
    written = 0
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            f.write(bytes([to_write | 0x80]))
            written += 1
        else:
            f.write(bytes([to_write]))
            written += 1
            break
    return written


def build_index(corpus_dir: Path, outdir: Path, sample: int | None = None, stem: bool = False, stemmer=None, clean: bool = False):
    base = outdir
    base.mkdir(parents=True, exist_ok=True)
    target = base / ('stemmed' if stem else 'raw')
    if clean:
        import shutil
        if target.exists():
            shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    # Ленивый импорт токенизатора из corpus_analyze
    try:
        from corpus_analyze.tokenize import tokenize_text
    except Exception:
    # запасной вариант: простой сплит по пробелам
        def tokenize_text(s: str):
            return s.split()

    postings: Dict[str, List[int]] = defaultdict(list)
    doclens: Dict[int, int] = {}
    forward_lines: List[str] = []
    stem_cache: Dict[str, str] = {}

    docs_seen = 0

    # обойти части корпуса в лексикографическом порядке
    parts = sorted([p for p in corpus_dir.glob('part_*.tsv')])
    docnum = 0
    for part in parts:
        with part.open('r', encoding='utf-8') as fh:
            for line in fh:
                line = line.rstrip('\n')
                if not line:
                    continue
                parts_line = line.split('\t', 2)
                if len(parts_line) < 3:
                    continue
                docid, title, text = parts_line
                if docid.lower() in ('id', 'docid', 'document_id'):
                    continue

                docnum += 1
                docs_seen += 1
                tokens = tokenize_text(text)
                doclens[docnum] = len(tokens)
                forward_lines.append(f"{docnum}\t{docid}\t{title}\n")

                # добавить соответствие term -> docnum один раз на документ
                seen = set()
                for tok in tokens:
                    if tok in seen:
                        continue
                    seen.add(tok)
                    # опционально стемминг/лемматизация
                    norm_tok = tok
                    if stem and stemmer:
                        if tok in stem_cache:
                            norm_tok = stem_cache[tok]
                        else:
                            try:
                                if hasattr(stemmer, 'stem'):
                                    norm_tok = stemmer.stem(tok)
                                elif hasattr(stemmer, 'parse'):
                                    parsed = stemmer.parse(tok)
                                    if parsed:
                                        first = parsed[0]
                                        if hasattr(first, 'normal_form'):
                                            norm_tok = first.normal_form
                                        else:
                                            norm_tok = str(first)
                                else:
                                    norm_tok = tok
                            except Exception:
                                norm_tok = tok
                            stem_cache[tok] = norm_tok

                    # отфильтровать токены, не содержащие букв или цифр (только пунктуация)
                    if not any(ch.isalnum() for ch in norm_tok):
                        continue
                    postings[norm_tok].append(docnum)

                if sample and docs_seen >= sample:
                    break
        if sample and docs_seen >= sample:
            break

    # записать forward.tsv
    with (target / 'forward.tsv').open('w', encoding='utf-8') as ff:
        ff.writelines(forward_lines)

    # записать postings.bin и vocab.tsv
    vocab_path = target / 'vocab.tsv'
    postings_path = target / 'postings.bin'

    # обеспечить детерминированный порядок терминов
    terms = sorted(postings.keys())

    with postings_path.open('wb') as pb, vocab_path.open('w', encoding='utf-8') as vf:
        for term in terms:
            docs = postings[term]
            df = len(docs)
            offset = pb.tell()

            # записать df
            write_varint(pb, df)
            # записать gap-кодированные номера документов
            prev = 0
            for d in docs:
                gap = d - prev
                write_varint(pb, gap)
                prev = d

            length = pb.tell() - offset
            vf.write(f"{term}\t{df}\t{offset}\t{length}\n")


    # записать doclens и meta
    meta = {
        'docs_count': docs_seen,
        'unique_terms': len(terms),
        'total_tokens': sum(doclens.values()),
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'sample': sample if sample else False,
        'file_hashes': {},
        'git_commit': None,
        'outdir': str(target),
    }

    # Добавить информацию о стемминге и используемом стеммере (если есть)
    try:
        meta['stemmed'] = bool(stem)
        meta['index_type'] = 'stemmed' if stem else 'raw'
        if stem and stemmer is not None:
            try:
                meta['stemmer'] = stemmer.__class__.__name__
            except Exception:
                meta['stemmer'] = str(type(stemmer))
    except Exception:
        pass

    # вычислить sha1 важных файлов, чтобы понимать, когда нужно переиндексировать
    try:
        repo_root = Path(__file__).resolve().parents[1]
        files = {
            'build_index.py': Path(__file__),
            'tokenize.py': repo_root / 'corpus_analyze' / 'tokenize.py',
        }
        for name, path in files.items():
            if path.exists():
                h = hashlib.sha1()
                with path.open('rb') as fh:
                    while True:
                        chunk = fh.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                meta['file_hashes'][name] = h.hexdigest()
    except Exception:
        pass
    try:
        repo_root = Path(__file__).resolve().parents[1]
        proc = subprocess.run(['git', '-C', str(repo_root), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True)
        meta['git_commit'] = proc.stdout.strip()
    except Exception:
        meta['git_commit'] = None

    with (target / 'doclens.json').open('w', encoding='utf-8') as jf:
        json.dump(doclens, jf, ensure_ascii=False, indent=2)

    with (target / 'meta.json').open('w', encoding='utf-8') as mf:
        json.dump(meta, mf, ensure_ascii=False, indent=2)

    print(f"Индекс собран: docs={docs_seen}, terms={len(terms)}, postings_bytes={postings_path.stat().st_size}, path={target}")
    return target


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--sample', type=int, help='Process first N documents and exit')
    group.add_argument('--full', action='store_true', help='Process entire corpus')
    ap.add_argument('--stem', action='store_true', help='Apply pymorphy2 lemmatization to tokens')
    ap.add_argument('--corpus', type=str, default=str(Path('..') / 'corpus'))
    ap.add_argument('--outdir', type=str, default='indexes')
    ap.add_argument('--force', action='store_true', help='Remove legacy index folders (index, index_stemmed) and clean target before building')
    args = ap.parse_args()

    corpus_dir = Path(args.corpus)
    outdir = Path(args.outdir)
    sample = None if args.full else args.sample
    stem = bool(args.stem)

    stemmer = None
    if stem:
        try:
            import importlib.machinery
            import importlib.util
            repo_root = Path(__file__).resolve().parents[1]
            mod_path = repo_root / 'indexer' / 'stemmer.py'
            loader = importlib.machinery.SourceFileLoader('local_stemmer', str(mod_path))
            spec = importlib.util.spec_from_loader(loader.name, loader)
            module = importlib.util.module_from_spec(spec)
            loader.exec_module(module)
            SimpleStemmer = module.SimpleStemmer
            stemmer = SimpleStemmer()
            print('Using self-written SimpleStemmer (loaded by path)')
        except Exception:
            try:
                from indexer.stemmer import SimpleStemmer
                stemmer = SimpleStemmer()
                print('Using self-written SimpleStemmer (package)')
            except Exception:
                try:
                    import pymorphy2
                    stemmer = pymorphy2.MorphAnalyzer()
                    print('Using pymorphy2 as fallback stemmer')
                except Exception as e:
                    print('Failed to initialize any stemmer:', e)
                    print('Proceeding without stemming')
                    stem = False

    if args.force:
        import shutil
        for legacy in (Path('index'), Path('index_stemmed')):
            if legacy.exists():
                try:
                    shutil.rmtree(legacy)
                    print(f'Removed legacy folder: {legacy}')
                except Exception as e:
                    print(f'Could not remove {legacy}: {e}')

    build_index(corpus_dir, outdir, sample=sample, stem=stem, stemmer=stemmer, clean=args.force)


if __name__ == '__main__':
    main()
