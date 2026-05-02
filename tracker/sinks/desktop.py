from __future__ import annotations

from ..events import event_t, EVENT_PRETTY


class desksink:
    name = "desktop"

    def __init__(self):
        try:
            from plyer import notification
            self._available = True
        except Exception:
            self._available = False

    async def emit(self, event: event_t) -> None:
        if not self._available:
            return
        try:
            from plyer import notification
            title = f"{event.display_name or event.username or event.user_id} - {EVENT_PRETTY.get(event.kind, event.kind)}"
            notification.notify(
                title=title[:64],
                message=event.summary()[:256],
                app_name="rblx-tracker",
                timeout=10,
            )
        except Exception:
            pass
