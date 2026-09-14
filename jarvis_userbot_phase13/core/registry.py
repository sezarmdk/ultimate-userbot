from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable

Handler = Callable[..., Awaitable[None]]

@dataclass
class Command:
    name: str
    description: str
    category: str
    handler: Handler
    aliases: tuple[str, ...] = field(default_factory=tuple)
    examples: tuple[str, ...] = field(default_factory=tuple)

class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._lookup: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        key = command.name.lower()
        if key in self._lookup:
            raise ValueError(f"Duplicate command: {command.name}")
        for alias in command.aliases:
            if alias.lower() in self._lookup:
                raise ValueError(f"Duplicate alias: {alias}")
        self._commands[key] = command
        self._lookup[key] = command
        for alias in command.aliases:
            self._lookup[alias.lower()] = command

    def get(self, name: str) -> Command | None:
        return self._lookup.get(name.lower())

    def names(self) -> list[str]:
        return sorted(self._commands)

    def validate(self) -> None:
        for command in self._commands.values():
            if not callable(command.handler):
                raise ValueError(f"Missing handler: {command.name}")
            if not command.description.strip():
                raise ValueError(f"Missing description: {command.name}")
