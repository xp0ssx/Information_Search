"""Простейшая утилита булевого поиска по бинарному индексу.

Поддерживает чтение `vocab.tsv` и `postings.bin` в формате проекта
(vocab: term\tdf\toffset\tlength, postings: varint(df) затем varint(gap) doc gaps).

Использование примеры:
  echo "россия && кино" | python3 bin/search_cli.py --index indexes/raw
  python3 bin/search_cli.py --index indexes/raw --query "(актёр || режиссёр) && !сериал"

Синтаксис запросов: слова, скобки, операторы: && (AND) | || (OR) | ! (NOT). Пробелы не значимы.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Set, Tuple


def read_varint_stream(b: bytes, pos: int = 0) -> Tuple[int, int]:
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
    docs: List[int] = []
    prev = 0
    for _ in range(df):
        gap, pos = read_varint_stream(block, pos)
        doc = prev + gap
        docs.append(doc)
        prev = doc
    return docs


def load_vocab(vocab_path: Path) -> Dict[str, Tuple[int, int, int]]:
    """Вернуть словарь term -> (df, offset, length)"""
    d: Dict[str, Tuple[int, int, int]] = {}
    with vocab_path.open('r', encoding='utf-8') as vf:
        for line in vf:
            line = line.rstrip('\n')
            if not line:
                continue
            term, df_s, off_s, len_s = line.split('\t')
            d[term] = (int(df_s), int(off_s), int(len_s))
    return d


def get_postings_for_term(term: str, vocab: Dict[str, Tuple[int, int, int]], postings_path: Path) -> List[int]:
    """Вернуть список docnum для терма или пустой список если терма нет."""
    info = vocab.get(term)
    if not info:
        info = vocab.get(term.lower())
        if not info:
            return []
    _, off, length = info
    with postings_path.open('rb') as pb:
        pb.seek(off)
        block = pb.read(length)
    return decode_postings(block)


_OP_PRECEDENCE = {'!': 3, '&&': 2, '||': 1}


def tokenize_query(s: str) -> List[str]:
    tokens: List[str] = []
    i = 0
    L = len(s)
    while i < L:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ch == '(' or ch == ')':
            tokens.append(ch)
            i += 1
            continue
        if s.startswith('&&', i):
            tokens.append('&&')
            i += 2
            continue
        if s.startswith('||', i):
            tokens.append('||')
            i += 2
            continue
        if ch == '!':
            tokens.append('!')
            i += 1
            continue
        j = i
        while j < L and not s[j].isspace() and s[j] not in '()!':
            if s.startswith('&&', j) or s.startswith('||', j):
                break
            j += 1
        tok = s[i:j]
        tokens.append(tok)
        i = j
    return tokens


def to_postfix(tokens: List[str]) -> List[str]:
    out: List[str] = []
    stack: List[str] = []
    for tok in tokens:
        if tok == '(':
            stack.append(tok)
        elif tok == ')':
            while stack and stack[-1] != '(':
                out.append(stack.pop())
            if stack and stack[-1] == '(':
                stack.pop()
        elif tok in _OP_PRECEDENCE:
            while stack and stack[-1] in _OP_PRECEDENCE:
                top = stack[-1]
                if (_OP_PRECEDENCE[top] > _OP_PRECEDENCE[tok]) or (
                    _OP_PRECEDENCE[top] == _OP_PRECEDENCE[tok] and tok != '!'
                ):
                    out.append(stack.pop())
                    continue
                break
            stack.append(tok)
        else:
            out.append(tok)
    while stack:
        out.append(stack.pop())
    return out


def eval_postfix(postfix: List[str], postings_loader: Callable[[str], Iterable[int]], all_docs: Set[int]) -> Set[int]:
    st: List[Set[int]] = []
    for tok in postfix:
        if tok == '!':
            if not st:
                st.append(set(all_docs))
            else:
                a = st.pop()
                st.append(set(all_docs) - a)
        elif tok == '&&':
            b = st.pop() if st else set()
            a = st.pop() if st else set()
            st.append(a & b)
        elif tok == '||':
            b = st.pop() if st else set()
            a = st.pop() if st else set()
            st.append(a | b)
        else:
            docs = set(postings_loader(tok))
            st.append(docs)
    return st[-1] if st else set()


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--index', type=str, default='indexes/raw', help='Path to index directory')
    ap.add_argument('--query', type=str, help='Single query string (if omitted, read from stdin)')
    args = ap.parse_args()

    idx = Path(args.index)
    vocab_path = idx / 'vocab.tsv'
    postings_path = idx / 'postings.bin'
    forward_path = idx / 'forward.tsv'

    if not vocab_path.exists() or not postings_path.exists() or not forward_path.exists():
        print('Index files not found in', idx)
        sys.exit(1)

    vocab = load_vocab(vocab_path)
    forward = load_forward(forward_path)
    all_docs = set(forward.keys())

    def loader(term: str) -> List[int]:
        return get_postings_for_term(term, vocab, postings_path)

    def process_query(q: str):
        toks = tokenize_query(q)
        postfix = to_postfix(toks)
        res = eval_postfix(postfix, loader, all_docs)
        out = sorted(res)
        for docnum in out[:50]:
            if docnum in forward:
                docid, title = forward[docnum]
                print(f"{docid}\t{title}")

    if args.query:
        process_query(args.query)
    else:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            process_query(line)


if __name__ == '__main__':
    main()
