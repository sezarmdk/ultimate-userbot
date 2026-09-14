class UI:
    DIVIDER = "━━━━━━━━━━━━"

    @classmethod
    def success(cls, title: str, body: str = "") -> str:
        return f"🟢 **{title}**\n\n{cls.DIVIDER}\n\n{body}".strip()

    @classmethod
    def info(cls, title: str, body: str = "") -> str:
        return f"ℹ️ **{title}**\n\n{cls.DIVIDER}\n\n{body}".strip()

    @classmethod
    def warning(cls, title: str, body: str = "") -> str:
        return f"⚠️ **{title}**\n\n{cls.DIVIDER}\n\n{body}".strip()

    @classmethod
    def error(cls, title: str, body: str = "") -> str:
        return f"🔴 **{title}**\n\n{cls.DIVIDER}\n\n{body}".strip()

    @classmethod
    def ready(cls, owner: str) -> str:
        return f"\n\n{cls.DIVIDER}\n\nEverything is ready, {owner}."
