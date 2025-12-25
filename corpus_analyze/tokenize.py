#!/usr/bin/env python3
"""Tokenizer placed inside corpus_analyze (per user request).

This is the same tokenizer used in `corpus_builder/tokenize.py` but defaults
to reading the corpus from ../corpus and writing outputs into the current
directory (`corpus_analyze`). Run from the repository root or from this
directory.

Usage examples (from repo root):
  ./corpus_analyze/tokenize.py --sample 200
  ./corpus_analyze/tokenize.py --full

Outputs created in this directory:
- sample_tokenized.tsv  (first 200 docs tokens)
- tokens_stats.json     (tokenization statistics)
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from glob import glob
from pathlib import Path
from typing import Iterable



def normalize_text(s: str) -> str:
    if not s:
        return ''
    # NFC and casefold for consistent token shapes
    s = unicodedata.normalize('NFC', s)
    s = s.casefold()

    # Replace various no-break spaces and BOM with normal space / nothing
    s = s.replace('\u00A0', ' ').replace('\u202F', ' ').replace('\uFEFF', '')

    # Remove soft hyphen and zero-width characters that break tokenization
    for ch in ('\u00AD', '\u200B', '\u200C', '\u200D'):
        s = s.replace(ch, '')

    # Normalize different dashes to simple hyphen-minus
    s = re.sub(r'[\u2010\u2011\u2012\u2013\u2014\u2015\u2212]', '-', s)

    # Collapse multiple whitespace
    s = ' '.join(s.split())
    return s


def tokenize_text(s: str) -> list[str]:
    """Unicode-aware tokenizer without external libs.

    Rules:
    - Tokens are sequences of Unicode letters or digits.
    - Internal apostrophes or hyphens are allowed if surrounded by letters/digits
      (keeps "rock-'n'-roll" pieces and hyphenated words).
    - Underscores and other punctuation are separators.
    """
    s = normalize_text(s)
    tokens: list[str] = []

    def is_letter_or_digit(ch: str) -> bool:
        cat = unicodedata.category(ch)
        return cat.startswith('L') or cat == 'Nd'

    cur = []
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
        if is_letter_or_digit(ch):
            cur.append(ch)
            i += 1
            continue

        # allow internal hyphen/apostrophe if between letters/digits
        if ch in ("-", "'", "’") and cur:
            # lookahead for a letter/digit
            if i + 1 < L and is_letter_or_digit(s[i + 1]):
                cur.append(ch)
                i += 1
                continue

        # separator -> flush
        if cur:
            tok = ''.join(cur)
            # strip leading/trailing punctuation like '-' or '\'' which shouldn't happen
            tok = tok.strip("-'")
            if tok:
                tokens.append(tok)
            cur = []
        i += 1

    # flush last
    if cur:
        tok = ''.join(cur).strip("-'")
        if tok:
            tokens.append(tok)
    return tokens


def iter_corpus_parts(corpus_dir: Path) -> Iterable[Path]:
    pattern = str(corpus_dir / "part_*.tsv")
    for p in sorted(glob(pattern)):
        yield Path(p)



def process_sample(outdir: Path, sample_docs: int = 200, corpus_dir: Path = Path('..') / 'corpus') -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    sample_path = outdir / 'sample_tokenized.tsv'
    stats = {
        'docs_processed': 0,
        'total_tokens': 0,
        'unique_terms': 0,
        'top_terms': []
    }
    counter = Counter()

    with sample_path.open('w', encoding='utf-8') as outf:
        outf.write('docid\ttitle\ttokens\n')
        for part in iter_corpus_parts(corpus_dir):
            with part.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not line:
                        continue
                    parts = line.split('\t', 2)
                    if len(parts) < 3:
                        continue
                    docid, title, text = parts
                    if docid.lower() in ('id', 'docid', 'document_id'):
                        continue

                    tokens = tokenize_text(text)
                    outf.write(f"{docid}\t{title}\t{' '.join(tokens)}\n")

                    counter.update(tokens)
                    stats['docs_processed'] += 1
                    stats['total_tokens'] += len(tokens)
                    if stats['docs_processed'] >= sample_docs:
                        break
            if stats['docs_processed'] >= sample_docs:
                break

    stats['unique_terms'] = len(counter)
    stats['top_terms'] = counter.most_common(100)

    with (outdir / 'tokens_stats.json').open('w', encoding='utf-8') as sf:
        json.dump(stats, sf, ensure_ascii=False, indent=2)

    return stats


def process_full(outdir: Path, corpus_dir: Path = Path('..') / 'corpus') -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    sample_path = outdir / 'sample_tokenized.tsv'
    counter = Counter()
    docs_written = 0

    with sample_path.open('w', encoding='utf-8') as outf:
        outf.write('docid\ttitle\ttokens\n')
        for part in iter_corpus_parts(corpus_dir):
            with part.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.rstrip('\n')
                    if not line:
                        continue
                    parts = line.split('\t', 2)
                    if len(parts) < 3:
                        continue
                    docid, title, text = parts
                    if docid.lower() in ('id', 'docid', 'document_id'):
                        continue

                    tokens = tokenize_text(text)
                    counter.update(tokens)
                    if docs_written < 200:
                        outf.write(f"{docid}\t{title}\t{' '.join(tokens)}\n")
                    docs_written += 1

    stats = {
        'docs_processed': docs_written,
        'total_tokens': sum(counter.values()),
        'unique_terms': len(counter),
        'top_terms': counter.most_common(100)
    }

    with (outdir / 'tokens_stats.json').open('w', encoding='utf-8') as sf:
        json.dump(stats, sf, ensure_ascii=False, indent=2)

    return stats


def main():
    import argparse
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--sample', type=int, help='Process first N documents and exit')
    group.add_argument('--full', action='store_true', help='Process entire corpus')
    ap.add_argument('--outdir', type=str, default='.', help='Output directory (default: current dir)')
    ap.add_argument('--corpus', type=str, default=str(Path('..') / 'corpus'), help='Corpus directory with part_*.tsv')
    args = ap.parse_args()

    outdir = Path(args.outdir)
    corpus_dir = Path(args.corpus)

    if args.sample:
        stats = process_sample(outdir, sample_docs=args.sample, corpus_dir=corpus_dir)
        print(f"Sample tokenization done: docs={stats['docs_processed']}, total_tokens={stats['total_tokens']}, unique_terms={stats['unique_terms']}")
    else:
        stats = process_full(outdir, corpus_dir=corpus_dir)
        print(f"Full tokenization done: docs={stats['docs_processed']}, total_tokens={stats['total_tokens']}, unique_terms={stats['unique_terms']}")


if __name__ == '__main__':
    main()
