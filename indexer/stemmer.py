"""Простой русскоязычный стеммер на правилах (встроенный).

Небольшая самодельная реализация для учебных целей. Удаляет распространённые
суффиксы с минимальной длиной стема, чтобы не переусердствовать. Это не
полноценный лемматизатор.
"""
from __future__ import annotations

from typing import List


class SimpleStemmer:
    def __init__(self):
        self.suffixes: List[str] = [
            'иями','ями','иями','ями','ями','ями',
            'иями','иями','иями','ствами','енность','остью',
            'овского','евского','ического','ического','ального',
            'ями','ами','ями','ями','ями','ями',
            'ого','его','ому','ему','ими','ыми','ее','ое','ие','ые',
            'ая','яя','ые','ие','ий','ой','ый','ость','ост','ение','ание',
            'ия','иям','иях','ями','ями','ями','ям','ах','ях','ами','ами',
            'ие','ия','ью','ью','ью','ью','ть','ти','ться','ется','аться',
            'ешь','ет','ют','ют','им','ым','ого','его','ому','ему','ом','ем',
            'ах','ях','ах','ях','у','ю','ы','и','а','я','е','о','ь'
        ]
        self.suffixes = sorted(set(self.suffixes), key=lambda s: -len(s))

    def stem(self, word: str) -> str:
        if not word:
            return word
        w = word.lower()
    # быстрое правило: для коротких слов (<=3) не менять
        if len(w) <= 3:
            return w

        for suf in self.suffixes:
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[: len(w) - len(suf)]
        return w

    def parse(self, word: str):
        """Шим-совместимость: возвращает список с объектом, у которого есть normal_form."""
        class _Res:
            def __init__(self, nf):
                self.normal_form = nf

            def __repr__(self):
                return f"<SimpleParse normal_form={self.normal_form}>"

        return [_Res(self.stem(word))]


def demo():
    s = SimpleStemmer()
    examples = ['машины', 'машин', 'машиной', 'машинам', 'играющий', 'играют', 'играл']
    for e in examples:
        print(e, '->', s.stem(e))


if __name__ == '__main__':
    demo()
