"""
RAF:LAA Lexer — tokenizes RAF:LAA source into a flat token stream.

Tokens:
  KEYWORD   — Field, Basin, Drift, Curvature, Echo, Gravity, Signature
  LBRACE    — {
  RBRACE    — }
  COLON     — :
  NUMBER    — integer or float (e.g. 0.42, -1.5, 3)
  SYMBOL    — any non-keyword, non-punctuation token (S-Unit IDs, pluis tokens, etc.)
"""

import re
from dataclasses import dataclass
from enum import Enum, auto


class TT(Enum):
    KEYWORD = auto()
    LBRACE  = auto()
    RBRACE  = auto()
    COLON   = auto()
    NUMBER  = auto()
    SYMBOL  = auto()
    EOF     = auto()


KEYWORDS = {"Field", "Basin", "Drift", "Curvature", "Echo", "Gravity", "Signature"}

_TOKEN_RE = re.compile(
    r'(?P<NUMBER>-?\d+(?:\.\d+)?)'
    r'|(?P<LBRACE>\{)'
    r'|(?P<RBRACE>\})'
    r'|(?P<COLON>:)'
    r'|(?P<WORD>[A-Za-z][A-Za-z0-9_\-]*)'
    r'|(?P<SKIP>\s+|#[^\n]*)'   # whitespace and comments
)


@dataclass
class Token:
    type:  TT
    value: str
    pos:   int


def tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    for m in _TOKEN_RE.finditer(src):
        if m.lastgroup == "SKIP":
            continue
        if m.lastgroup == "NUMBER":
            tokens.append(Token(TT.NUMBER, m.group(), m.start()))
        elif m.lastgroup == "LBRACE":
            tokens.append(Token(TT.LBRACE, "{", m.start()))
        elif m.lastgroup == "RBRACE":
            tokens.append(Token(TT.RBRACE, "}", m.start()))
        elif m.lastgroup == "COLON":
            tokens.append(Token(TT.COLON, ":", m.start()))
        elif m.lastgroup == "WORD":
            word = m.group()
            tt = TT.KEYWORD if word in KEYWORDS else TT.SYMBOL
            tokens.append(Token(tt, word, m.start()))
    tokens.append(Token(TT.EOF, "", len(src)))
    return tokens
