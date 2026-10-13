"""Canonical ecosystem names.

The classifier writes ecosystems as free text, so "bnb", "bnb chain" and
"binance" coexisted: dashboard filters split one chain three ways and the L2
ecosystem veto kept same-chain duplicates apart. Canonical ids follow
config/chains.yaml; "multi" means no particular chain.
"""
import re
from typing import Optional

MULTI = "multi"

_ALIASES = {
    "bnb": "bnb", "bsc": "bnb", "binance": "bnb", "binance smart": "bnb", "bnb smart": "bnb",
    "eth": "ethereum", "ethereum": "ethereum",
    "sol": "solana", "solana": "solana",
    "arb": "arbitrum", "arbitrum": "arbitrum", "arbitrum one": "arbitrum",
    "op": "optimism", "op mainnet": "optimism", "optimism": "optimism",
    "matic": "polygon", "polygon": "polygon", "polygon pos": "polygon",
    "avax": "avalanche", "avalanche": "avalanche", "avalanche c": "avalanche",
    "apt": "aptos", "aptos": "aptos",
    "strk": "starknet", "starknet": "starknet",
    "base": "base", "sui": "sui", "near": "near", "stellar": "stellar", "xlm": "stellar",
    "monad": "monad", "berachain": "berachain", "sonic": "sonic", "megaeth": "megaeth",
    "xrp": "xrp", "xrpl": "xrp", "xrp ledger": "xrp",
}

_MULTI_WORDS = {
    "multi", "multichain", "multi chain", "cross chain", "crosschain", "omnichain",
    "all", "any", "various", "evm", "web3", "general", "blockchain", "agnostic", "chain agnostic",
}

# Trailing words that do not change which chain is meant ("Sui Network", "BNB Chain").
_SUFFIX_RE = re.compile(r"\s+(network|chain|blockchain|ecosystem|protocol|mainnet|l1|l2)$")


def normalize_ecosystem(value: Optional[str]) -> Optional[str]:
    """Canonical ecosystem id, "multi" for no particular chain, None when empty."""
    if value is None:
        return None
    text = re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
    if not text:
        return None
    if text in _MULTI_WORDS:
        return MULTI
    while True:
        if text in _ALIASES:
            return _ALIASES[text]
        stripped = _SUFFIX_RE.sub("", text)
        if stripped == text:
            return text
        text = stripped
