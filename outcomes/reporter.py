"""
Reporter — generates and sends status reports.
Text report for logs. Telegram for live notifications.
"""
from __future__ import annotations
import requests
from loguru import logger
from config import CFG
from outcomes.fitness import FITNESS
from outcomes.revenue import REVENUE


class Reporter:
    def generate_report(self) -> str:
        metrics = FITNESS.get_metrics()
        total_rev = REVENUE.get_total()
        recent = REVENUE.get_recent(limit=5)

        lines = [
            "=== SDAE STATUS REPORT ===",
            metrics.summary(),
            f"Total Revenue: ${total_rev:.2f}",
        ]

        if recent:
            lines.append("\nRecent Revenue:")
            for r in recent:
                lines.append(f"  +${r['amount']:.2f} — {r['project_name']} ({r['source']})")

        return "\n".join(lines)

    def send_telegram(self, message: str) -> bool:
        if not CFG.telegram_token or not CFG.telegram_chat_id:
            logger.debug("Telegram not configured — skipping notification")
            return False

        url = f"https://api.telegram.org/bot{CFG.telegram_token}/sendMessage"
        try:
            resp = requests.post(url, json={
                "chat_id": CFG.telegram_chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }, timeout=10)
            ok = resp.status_code == 200
            if ok:
                logger.info("Telegram notification sent")
            else:
                logger.warning(f"Telegram failed: {resp.text[:200]}")
            return ok
        except Exception as e:
            logger.warning(f"Telegram error: {e}")
            return False

    def weekly_report(self):
        report = self.generate_report()
        logger.info(report)
        self.send_telegram(f"📊 Weekly Report\n```\n{report}\n```")

    def notify(self, message: str):
        logger.info(f"NOTIFY: {message}")
        self.send_telegram(message)


REPORTER = Reporter()
