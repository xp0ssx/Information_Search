"""Minimal Flask web UI for boolean search.

Requirements: Flask (install with `pip install flask`).

Usage (from repo root):
  python3 webapp/app.py --index indexes/raw --host 127.0.0.1 --port 8080

The app exposes:
  /        - simple form
  /search  - GET endpoint with query parameter `q` and optional `page`

This is intentionally tiny: no templates, simple HTML generation.
"""

from __future__ import annotations

import argparse
import html
from math import ceil
from urllib.parse import quote_plus, unquote_plus
from pathlib import Path
from typing import Dict, List, Tuple


def create_app(index_dir: Path):
    from flask import Flask, request

    app = Flask(__name__)

    try:
        from bin.search_cli import load_vocab, load_forward, tokenize_query, to_postfix, eval_postfix, get_postings_for_term
    except Exception:
        import importlib.machinery, importlib.util
        repo_root = Path(__file__).resolve().parents[1]
        mod_path = repo_root / 'bin' / 'search_cli.py'
        loader = importlib.machinery.SourceFileLoader('search_cli', str(mod_path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        load_vocab = module.load_vocab
        load_forward = module.load_forward
        tokenize_query = module.tokenize_query
        to_postfix = module.to_postfix
        eval_postfix = module.eval_postfix
        get_postings_for_term = module.get_postings_for_term

    vocab = load_vocab(index_dir / 'vocab.tsv')
    forward = load_forward(index_dir / 'forward.tsv')
    all_docs = set(forward.keys())
    repo_root = Path(__file__).resolve().parents[1]
    corpus_dir = repo_root / 'corpus'
    corpus_texts = load_corpus_texts(corpus_dir)

    def loader(term: str) -> List[int]:
        return get_postings_for_term(term, vocab, index_dir / 'postings.bin')

    PER_PAGE = 50

    @app.route('/')
    def index():
        return (
            '<html><head><meta charset="utf-8"><title>Search</title></head>'
            '<body>'
            '<h2>Boolean search</h2>'
            '<form action="/search" method="get">'
            '<input name="q" size="60" placeholder="Введите запрос, например: (актёр || режиссёр) && !сериал">'
            '<input type="submit" value="Search">'
            '</form>'
            '<p>Operators: <code>&&</code> (AND), <code>||</code> (OR), <code>!</code> (NOT), parentheses.</p>'
            '</body></html>'
        )

    @app.route('/search')
    def search():
        q = request.args.get('q', '')
        page = int(request.args.get('page', '1') or '1')
        if not q.strip():
            return '<p>Empty query. <a href="/">Back</a></p>'

        toks = tokenize_query(q)
        postfix = to_postfix(toks)
        res = eval_postfix(postfix, loader, all_docs)
        results = sorted(res)
        total = len(results)
        pages = max(1, ceil(total / PER_PAGE))
        if page < 1:
            page = 1
        if page > pages:
            page = pages
        start = (page - 1) * PER_PAGE
        end = start + PER_PAGE
        slice_docs = results[start:end]

        html_parts = [
            '<html><head><meta charset="utf-8"><title>Results</title></head><body>',
            f'<p><a href="/">New search</a> — results for: <b>{html.escape(q)}</b></p>',
            f'<p>Found {total} documents. Showing {start+1}–{min(end, total)}</p>',
            '<ol start="{}">'.format(start + 1)
        ]
        for docnum in slice_docs:
            if docnum in forward:
                docid, title = forward[docnum]
                back_q = quote_plus(q)
                html_parts.append(
                    f'<li><a href="/doc/{docnum}?q={back_q}&page={page}">{html.escape(title)}</a> <small>({html.escape(docid)})</small></li>'
                )
        html_parts.append('</ol>')

        html_parts.append('<div>')
        if page > 1:
            html_parts.append(f'<a href="/search?q={html.escape(q)}&page={page-1}">Prev</a> ')
        if page < pages:
            html_parts.append(f'<a href="/search?q={html.escape(q)}&page={page+1}">Next</a>')
        html_parts.append('</div>')

        html_parts.append('</body></html>')
        return '\n'.join(html_parts)

    @app.route('/doc/<int:docnum>')
    def doc_view(docnum: int):
        q = request.args.get('q', '')
        page = int(request.args.get('page', '1') or '1')
        if docnum not in forward:
            back_url = (f'/search?q={quote_plus(q)}&page={page}') if q else '/'
            return (f'<p>Document not found. <a href="{back_url}">Back</a></p>', 404)
        docid, title = forward[docnum]
        text = corpus_texts.get(docid)
        if text is None:
            body = '<p>Text for this document is not available in corpus parts.</p>'
        else:
            snippet = html.escape(text[:1000])
            body = f'<h2>{html.escape(title)}</h2><p><b>docid:</b> {html.escape(docid)}</p>'
            body += f'<h3>Snippet</h3><p>{snippet}</p>'
            body += f'<h3>Full text</h3><pre style="white-space: pre-wrap;">{html.escape(text)}</pre>'
        back_url = (f'/search?q={quote_plus(q)}&page={page}') if q else '/'
        return ('<html><head><meta charset="utf-8"><title>' + html.escape(title) + '</title></head><body>' + body + f'<p><a href="{back_url}">Back</a></p></body></html>')

    return app


def load_corpus_texts(corpus_dir: Path) -> Dict[str, str]:
    """Load corpus parts and return mapping docid -> text."""
    docs: Dict[str, str] = {}
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
    ap.add_argument('--index', type=str, default='indexes/raw', help='Path to index directory')
    ap.add_argument('--host', type=str, default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8080)
    args = ap.parse_args()

    idx = Path(args.index)
    if not (idx / 'vocab.tsv').exists():
        print('Index not found at', idx)
        raise SystemExit(1)

    app = create_app(idx)
    app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()
