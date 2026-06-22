import tiktoken

_encoding: tiktoken.Encoding | None = None


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding("cl100k_base")
    return _encoding


def count_tokens(text: str) -> int:
    enc = _get_encoding()
    return len(enc.encode(text))


def count_messages_tokens(messages: list[dict]) -> int:
    enc = _get_encoding()
    total = 0
    for msg in messages:
        total += 4
        for key, value in msg.items():
            if isinstance(value, str):
                total += len(enc.encode(value))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "text" in item:
                        total += len(enc.encode(item["text"]))
        total += 2
    return total
