import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw in TOKEN_PATTERN.findall(text):
        token = raw.lower()
        tokens.append(token)
        if "-" in token or "_" in token:
            tokens.extend(part for part in re.split(r"[-_]+", token) if part)
        if token.endswith("s") and len(token) > 4:
            tokens.append(token[:-1])
        if token.endswith("ed") and len(token) > 5:
            tokens.append(token[:-2])
    return tokens


def embed_text(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dimensions
        vector[idx] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=False))
