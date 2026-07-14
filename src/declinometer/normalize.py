"""Length-preserving text preparation for signal matching.

The detector never mutates the text it reports spans against. Instead it
builds a *matching copy* of the original output that is:

- case-folded (character by character, only when folding keeps the length),
- typographic-quote-folded (curly apostrophes and quotes become ASCII), and
- masked: code fences, inline code, double-quoted spans, and blockquote
  lines are replaced with spaces.

Because every transformation preserves the character count, an offset into
the matching copy is also an offset into the original text, so signal spans
reported to the user always point at the exact characters that fired.

Masking exists because quoted or fenced material is *mentioned*, not
*spoken*: an answer that explains "the model replied 'I cannot help with
that'" or that prints a refusal string inside a code sample is not itself a
refusal, and must not count as one.
"""

from __future__ import annotations

import re

__all__ = [
    "fold",
    "mask",
    "prepare",
    "word_count",
    "count_code_fences",
    "count_list_items",
]

# Typographic characters folded to their ASCII equivalents so one lexicon
# spelling ("i can't") matches both straight and curly punctuation.
_QUOTE_FOLD = {
    "‘": "'",  # left single quotation mark
    "’": "'",  # right single quotation mark (the common apostrophe)
    "‚": "'",
    "‛": "'",
    "“": '"',  # left double quotation mark
    "”": '"',  # right double quotation mark
    "„": '"',
    "‟": '"',
    "«": '"',  # guillemets
    "»": '"',
    "–": "-",  # en dash
    "—": "-",  # em dash
    " ": " ",  # no-break space
}

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# Double-quoted spans on a single line, bounded so a stray unmatched quote
# cannot swallow half the document.
_DQUOTE_RE = re.compile(r'"[^"\n]{1,300}"')
_BLOCKQUOTE_RE = re.compile(r"^[ \t]{0,3}>.*$", re.MULTILINE)

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")
_LIST_ITEM_RE = re.compile(r"^[ \t]*(?:[-*+]|\d{1,3}[.)])[ \t]+\S", re.MULTILINE)


def fold(text: str) -> str:
    """Lowercase and quote-fold *text* without changing its length.

    Characters whose Unicode lowercase form is longer than one character
    (e.g. 'İ' -> 'i̇') are kept as-is: correctness of span offsets beats
    matching an exotic capital letter.
    """
    out = []
    for ch in text:
        ch = _QUOTE_FOLD.get(ch, ch)
        low = ch.lower()
        out.append(low if len(low) == 1 else ch)
    return "".join(out)


def _blank(match: "re.Match[str]") -> str:
    """Replace a matched region with spaces, preserving newlines."""
    return "".join("\n" if c == "\n" else " " for c in match.group(0))


def mask(folded: str) -> str:
    """Blank out quoted/fenced regions of an already-folded text.

    Order matters: fences first (they may contain quotes), then inline
    code, then double-quoted spans, then blockquote lines.
    """
    masked = _FENCE_RE.sub(_blank, folded)
    masked = _INLINE_CODE_RE.sub(_blank, masked)
    masked = _DQUOTE_RE.sub(_blank, masked)
    masked = _BLOCKQUOTE_RE.sub(_blank, masked)
    return masked


def prepare(text: str) -> str:
    """Fold and mask *text* into the matching copy used by the detector."""
    return mask(fold(text))


def word_count(text: str) -> int:
    """Count word-like tokens; used for hedge density and substance checks."""
    return len(_WORD_RE.findall(text))


def count_code_fences(text: str) -> int:
    """Number of complete fenced code blocks in the original text."""
    return len(_FENCE_RE.findall(text))


def count_list_items(text: str) -> int:
    """Number of Markdown bullet or numbered list lines in the original text."""
    return len(_LIST_ITEM_RE.findall(text))
