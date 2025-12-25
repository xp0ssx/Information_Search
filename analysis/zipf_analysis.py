#!/usr/bin/env python3
"""Zipf analysis: compute rank-frequency and plot log-log fit.

Outputs:
- analysis/zipf.json  -- stats (slope, intercept, r2, total_terms, total_tokens)
- analysis/zipf.png   -- log-log plot (if matplotlib available)
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean


def read_vocab(vocab_path: Path):
    freqs = []
    with vocab_path.open('r', encoding='utf-8') as vf:
        for line in vf:
            line = line.rstrip('\n')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            term = parts[0]
            try:
                df = int(parts[1])
            except Exception:
                continue
            freqs.append((term, df))
    return freqs


def fit_zipf(freqs_sorted):
    # freqs_sorted: list of df descending
    # fit log(freq) = a + b * log(rank) -> slope = b (expected ~ -1)
    xs = []
    ys = []
    for rank, f in enumerate(freqs_sorted, start=1):
        if f <= 0:
            continue
        xs.append(math.log(rank))
        ys.append(math.log(f))

    n = len(xs)
    if n < 2:
        return None
    x_mean = mean(xs)
    y_mean = mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    den = sum((x - x_mean) ** 2 for x in xs)
    slope = num / den
    intercept = y_mean - slope * x_mean
    # compute r2
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return {'slope': slope, 'intercept': intercept, 'r2': r2, 'n': n}


def main():
    repo = Path(__file__).resolve().parents[1]
    vocab = repo / 'index' / 'vocab.tsv'
    outdir = repo / 'analysis'
    outdir.mkdir(parents=True, exist_ok=True)

    if not vocab.exists():
        print('vocab.tsv not found at', vocab)
        return

    freqs = read_vocab(vocab)
    freqs_sorted = [df for _, df in sorted(freqs, key=lambda x: x[1], reverse=True)]
    total_terms = len(freqs_sorted)
    total_tokens = sum(freqs_sorted)

    fit = fit_zipf(freqs_sorted[:100000])  # fit on top 100k ranks for stability

    result = {
        'total_terms': total_terms,
        'total_tokens': total_tokens,
        'fit': fit,
    }

    with (outdir / 'zipf.json').open('w', encoding='utf-8') as jf:
        json.dump(result, jf, ensure_ascii=False, indent=2)

    # attempt plotting
    try:
        import matplotlib.pyplot as plt

        ranks = list(range(1, len(freqs_sorted) + 1))
        xs = ranks[:20000]
        ys = freqs_sorted[:20000]
        plt.figure(figsize=(6, 4))
        plt.loglog(xs, ys, marker='.', markersize=2, linewidth=0)
        if fit:
            import numpy as np
            x_fit = np.array([1, xs[-1]])
            y_fit = math.exp(fit['intercept']) * x_fit ** fit['slope']
            plt.loglog(x_fit, y_fit, color='red', label=f"s={fit['slope']:.3f}, r2={fit['r2']:.3f}")
            plt.legend()
        plt.xlabel('rank')
        plt.ylabel('frequency')
        plt.title('Zipf rank-frequency')
        plt.tight_layout()
        plt.savefig(outdir / 'zipf.png', dpi=150)
        print('Saved analysis/zipf.json and analysis/zipf.png')
    except Exception as e:
        print('Saved analysis/zipf.json (plot not created:', e, ')')


if __name__ == '__main__':
    main()
