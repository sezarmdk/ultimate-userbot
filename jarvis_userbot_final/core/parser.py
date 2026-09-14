from dataclasses import dataclass

@dataclass(frozen=True)
class ParsedCommand:
    name: str
    args: list[str]
    raw_args: str

def parse_command(text: str, prefix: str = ".") -> ParsedCommand | None:
    text = text.strip()
    if not text.startswith(prefix):
        return None
    payload = text[len(prefix):].strip()
    if not payload:
        return None
    parts = payload.split(maxsplit=1)
    name = parts[0].lower()
    raw_args = parts[1].strip() if len(parts) > 1 else ""
    return ParsedCommand(name=name, args=raw_args.split() if raw_args else [], raw_args=raw_args)
