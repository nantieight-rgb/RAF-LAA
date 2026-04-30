"""
RAF:LAA Parser — converts token stream into AST.

Grammar (EBNF):
  field     = "Field" "{" basin signature "}"
  basin     = "Basin" "{" drift "}"
  drift     = "Drift" "{" curvature echo gravity "}"
  curvature = "Curvature" ":" NUMBER
  echo      = "Echo" ":" SYMBOL
  gravity   = "Gravity" ":" NUMBER
  signature = "Signature" ":" SYMBOL
"""

from .lexer import Token, TT, tokenize
from .ast_nodes import (
    Field, Basin, Drift,
    Curvature, Echo, Gravity, Signature,
)


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self._tokens = tokens
        self._pos = 0

    # ── Token access ────────────────────────────────────────────────────────
    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, tt: TT, value: str | None = None) -> Token:
        tok = self._advance()
        if tok.type != tt:
            raise ParseError(
                f"Expected {tt.name}"
                + (f" '{value}'" if value else "")
                + f", got {tok.type.name} '{tok.value}' at pos {tok.pos}"
            )
        if value is not None and tok.value != value:
            raise ParseError(
                f"Expected '{value}', got '{tok.value}' at pos {tok.pos}"
            )
        return tok

    # ── Grammar rules ────────────────────────────────────────────────────────
    def parse_field(self) -> Field:
        self._expect(TT.KEYWORD, "Field")
        self._expect(TT.LBRACE)
        basin = self._parse_basin()
        sig   = self._parse_signature()
        self._expect(TT.RBRACE)
        return Field(basin=basin, signature=sig, pes_timestamp=0.0)

    def _parse_basin(self) -> Basin:
        self._expect(TT.KEYWORD, "Basin")
        self._expect(TT.LBRACE)
        drift = self._parse_drift()
        self._expect(TT.RBRACE)
        return Basin(drift=drift)

    def _parse_drift(self) -> Drift:
        self._expect(TT.KEYWORD, "Drift")
        self._expect(TT.LBRACE)
        curv    = self._parse_curvature()
        echo    = self._parse_echo()
        gravity = self._parse_gravity()
        self._expect(TT.RBRACE)
        return Drift(curvature=curv, echo=echo, gravity=gravity)

    def _parse_curvature(self) -> Curvature:
        self._expect(TT.KEYWORD, "Curvature")
        self._expect(TT.COLON)
        tok = self._expect(TT.NUMBER)
        return Curvature(value=float(tok.value))

    def _parse_echo(self) -> Echo:
        self._expect(TT.KEYWORD, "Echo")
        self._expect(TT.COLON)
        tok = self._advance()
        if tok.type not in (TT.SYMBOL, TT.KEYWORD):
            raise ParseError(f"Expected symbol for Echo, got '{tok.value}'")
        return Echo(symbol=tok.value)

    def _parse_gravity(self) -> Gravity:
        self._expect(TT.KEYWORD, "Gravity")
        self._expect(TT.COLON)
        tok = self._expect(TT.NUMBER)
        return Gravity(value=float(tok.value))

    def _parse_signature(self) -> Signature:
        self._expect(TT.KEYWORD, "Signature")
        self._expect(TT.COLON)
        tok = self._advance()
        if tok.type not in (TT.SYMBOL, TT.KEYWORD, TT.NUMBER):
            raise ParseError(f"Expected pluis_token for Signature, got '{tok.value}'")
        return Signature(pluis_token=tok.value)


def parse(src: str, pes_timestamp: float | None = None) -> Field:
    from .pes import now_pes
    tokens = tokenize(src)
    parser = Parser(tokens)
    field  = parser.parse_field()
    if parser._peek().type != TT.EOF:
        tok = parser._peek()
        raise ParseError(f"Unexpected token '{tok.value}' at pos {tok.pos}")
    # Stamp PES on parsed Field
    object.__setattr__(field, 'pes_timestamp',
                       pes_timestamp if pes_timestamp is not None else now_pes())
    return field
