import pytest
import importlib.machinery
import importlib.util
from pathlib import Path

# Load search_cli module by path to avoid import errors when running under pytest
repo_root = Path(__file__).resolve().parents[1]
mod_path = repo_root / 'bin' / 'search_cli.py'
loader = importlib.machinery.SourceFileLoader('search_cli', str(mod_path))
spec = importlib.util.spec_from_loader(loader.name, loader)
search_cli = importlib.util.module_from_spec(spec)
loader.exec_module(search_cli)


def test_tokenize_query_simple():
    s = "( a && b ) || !c"
    toks = search_cli.tokenize_query(s)
    assert toks == ['(', 'a', '&&', 'b', ')', '||', '!', 'c']


def test_to_postfix():
    toks = ['(', 'a', '&&', 'b', ')', '||', '!', 'c']
    postfix = search_cli.to_postfix(toks)
    # one valid postfix: a b && c ! ||
    assert postfix == ['a', 'b', '&&', 'c', '!', '||']


def test_eval_postfix_basic():
    # build simple postings loader
    postings = {
        'a': [1, 2, 3],
        'b': [2, 3],
        'c': [3]
    }

    def loader(t):
        return postings.get(t, [])

    all_docs = {1, 2, 3, 4}
    postfix = ['a', 'b', '&&', 'c', '!', '||']
    res = search_cli.eval_postfix(postfix, loader, all_docs)
    # a&&b = {2,3}; c! = all_docs - {3} = {1,2,4}; union -> {1,2,3,4}
    assert res == {1, 2, 3, 4}
