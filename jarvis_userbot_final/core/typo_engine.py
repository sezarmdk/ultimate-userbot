import difflib

class TypoEngine:
    def __init__(self, commands: list[str]) -> None:
        self.commands = commands

    def suggest(self, value: str) -> str | None:
        matches = difflib.get_close_matches(value.lower(), self.commands, n=1, cutoff=0.72)
        return matches[0] if matches else None
