"""按换行把一条回复拆成多条消息依次发出。"""

import asyncio
import random
import re

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import BaseMessageComponent, Plain
from astrbot.api.star import Context, Star, register

_SPLIT_PATTERNS = {
    "any_newline": re.compile(r"\n+"),
    "blank_line": re.compile(r"\n[ \t]*\n\s*"),
}

# 排在最后：让其它插件先改完消息，本插件拿到的是最终文本
_PRIORITY = -100000


@register(
    "astrbot_plugin_newline_split",
    "APHu19",
    "按换行把一条回复拆成多条消息依次发出",
    "1.0.0",
)
class NewlineSplitPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    def _split_chain(
        self, chain: list[BaseMessageComponent], pattern: re.Pattern[str]
    ) -> list[list[BaseMessageComponent]]:
        segments: list[list[BaseMessageComponent]] = []
        current: list[BaseMessageComponent] = []
        for comp in chain:
            if not isinstance(comp, Plain):
                current.append(comp)
                continue
            for index, piece in enumerate(pattern.split(comp.text)):
                if index:
                    segments.append(current)
                    current = []
                text = piece.strip()
                if text:
                    current.append(Plain(text))
        segments.append(current)
        return [seg for seg in segments if seg]

    @filter.on_decorating_result(priority=_PRIORITY)
    async def on_decorating_result(self, event: AstrMessageEvent):
        if not self.config.get("enable", True):
            return
        result = event.get_result()
        if result is None or not result.chain:
            return
        if self.config.get("only_llm", True) and not result.is_llm_result():
            return

        mode = self.config.get("split_mode", "any_newline")
        pattern = _SPLIT_PATTERNS.get(str(mode), _SPLIT_PATTERNS["any_newline"])
        segments = self._split_chain(result.chain, pattern)
        if len(segments) < 2:
            return

        limit = int(self.config.get("max_segments", 10))
        if limit < 1:
            limit = 1
        if len(segments) > limit:
            tail = [comp for seg in segments[limit - 1 :] for comp in seg]
            segments = [*segments[: limit - 1], tail]

        low = float(self.config.get("interval_min", 1.5))
        high = float(self.config.get("interval_max", 3.5))
        if high < low:
            low, high = high, low

        logger.debug(f"[newline_split] 拆成 {len(segments)} 段依次发送")
        event.clear_result()
        for index, segment in enumerate(segments):
            if index:
                await asyncio.sleep(random.uniform(low, high))
            await event.send(result.derive(segment))
        event.stop_event()
