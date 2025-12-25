"""Скрипт скачивания страниц из категории Википедии.

Особенности:
- аргументы командной строки: --max-pages, --max-depth, --output-dir, --resume
- сохраняет каждую страницу в `output_dir/docs.jsonl` в формате JSONL (одна строка = 1 документ)
- ведёт файл `output_dir/processed.txt` для продолжения (resume)
- печатает прогресс (скачано N / max)
- корректно обрабатывает прерывания (KeyboardInterrupt)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from typing import Iterable

import wikipediaapi
import requests
from urllib3.exceptions import ProtocolError


def iter_pages(categorymembers, level: int = 0, max_level: int = 2) -> Iterable[wikipediaapi.WikipediaPage]:
    for c in categorymembers.values():
        if c.ns == wikipediaapi.Namespace.CATEGORY and level < max_level:
            yield from iter_pages(c.categorymembers, level=level + 1, max_level=max_level)
        elif c.ns == wikipediaapi.Namespace.MAIN:
            yield c


def slugify_title(title: str) -> str:
    return title.replace('/', '_')


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode('utf-8')).hexdigest()


def save_doc_jsonl(path: str, doc: dict):
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(doc, ensure_ascii=False) + '\n')


def load_processed(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, 'r', encoding='utf-8') as fh:
        return set(line.strip() for line in fh if line.strip())


def append_processed(path: str, title: str):
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(title + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download Wikipedia pages from a category (controlled).')
    parser.add_argument('--language', '-l', default='ru', help='Wikipedia language code (default: ru)')
    parser.add_argument('--category', '-c', default='Категория:Кинематограф', help='Category name to crawl')
    parser.add_argument('--output-dir', '-o', default='wiki_cinema', help='Directory to save output')
    parser.add_argument('--max-pages', type=int, default=0, help='Maximum number of pages to download (0 = unlimited)')
    parser.add_argument('--max-depth', type=int, default=2, help='Category depth to traverse (default: 2)')
    parser.add_argument('--resume', action='store_true', help='Resume from previous run using processed.txt')
    parser.add_argument('--sleep', type=float, default=0.0, help='Seconds to sleep between requests (politeness)')
    parser.add_argument('--retries', type=int, default=3, help='Number of retries for transient HTTP errors')
    parser.add_argument('--retry-backoff', type=float, default=2.0, help='Backoff multiplier (seconds) between retries')
    args = parser.parse_args(argv)

    os.makedirs(args.output_dir, exist_ok=True)
    jsonl_path = os.path.join(args.output_dir, 'docs.jsonl')
    processed_path = os.path.join(args.output_dir, 'processed.txt')

    wiki = wikipediaapi.Wikipedia(language=args.language,
                                  user_agent='InformationSearchBot/1.0 (contact)')

    cat = wiki.page(args.category)
    if not cat.exists():
        print(f"Category not found: {args.category}", file=sys.stderr)
        return 2

    processed = set()
    if args.resume:
        processed = load_processed(processed_path)

    pages_iter = iter_pages(cat.categorymembers, level=0, max_level=args.max_depth)

    def safe_fetch_text(title: str, wiki_obj: wikipediaapi.Wikipedia, attempts: int = 3, backoff: float = 2.0):
        """Try to fetch page text with retries and recreate session if needed.

        Returns (text, wiki_obj) where wiki_obj may be a fresh Wikipedia instance after recreation.
        """
        w = wiki_obj
        for i in range(1, attempts + 1):
            try:
                p = w.page(title)
                return (p.text or '', w)
            except (requests.exceptions.RequestException, ProtocolError) as e:
                print(f"Warning: network error fetching '{title}' (attempt {i}/{attempts}): {e}", file=sys.stderr)
            except Exception as e:
                # catch-all to avoid crashing the whole run on unexpected parse/network errors
                print(f"Warning: error fetching '{title}' (attempt {i}/{attempts}): {e}", file=sys.stderr)

            if i == attempts:
                print(f"Skipping page '{title}' after {attempts} attempts.", file=sys.stderr)
                return ('', w)

            sleep_time = backoff * i
            time.sleep(sleep_time)
            # recreate wiki/session in hope of clearing transient connection state
            try:
                w = wikipediaapi.Wikipedia(language=args.language,
                                           user_agent='InformationSearchBot/1.0 (contact)')
            except Exception:
                # if recreation fails, keep using previous instance and try again
                w = wiki_obj

    downloaded = 0
    total_bytes = 0
    start_time = time.time()

    try:
        for page in pages_iter:
            title = page.title
            if args.resume and title in processed:
                continue
            if args.max_pages and downloaded >= args.max_pages:
                break

            # fetch with retries; this function may recreate the wiki/session on failures
            text, wiki = safe_fetch_text(title, wiki, attempts=args.retries, backoff=args.retry_backoff)

            if not text:
                # nothing fetched (skipped after retries) — record as processed to avoid retry loops
                append_processed(processed_path, title)
                print(f"Skipped: {slugify_title(title)} (no text)", file=sys.stderr)
                downloaded += 1
                continue

            b = len(text.encode('utf-8'))

            doc = {
                'id': sha1(title),
                'title': title,
                'text': text,
                'source': f'wikipedia:{args.language}',
                'retrieved_at': datetime.utcnow().isoformat() + 'Z',
                'bytes': b,
            }

            save_doc_jsonl(jsonl_path, doc)
            append_processed(processed_path, title)

            downloaded += 1
            total_bytes += b

            elapsed = time.time() - start_time
            avg_per = downloaded / elapsed if elapsed > 0 else 0
            msg = (f"Downloaded: {downloaded} pages; Total bytes: {total_bytes}; Last: {slugify_title(title)}; "
                   f"Elapsed: {int(elapsed)}s; avg pages/s: {avg_per:.2f}")
            if args.max_pages:
                msg = f"{msg}; Target: {args.max_pages}"
            print(msg)

            if args.sleep:
                time.sleep(args.sleep)

    except KeyboardInterrupt:
        print('\nInterrupted by user — exiting gracefully. Progress saved.')

    print(f"Finished. Downloaded {downloaded} pages, total {total_bytes} bytes.")


if __name__ == '__main__':
    sys.exit(main())