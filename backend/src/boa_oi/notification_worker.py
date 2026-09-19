from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

from sqlalchemy.orm import Session, sessionmaker

from boa_oi.notification_api import dispatch_due, materialize_daily_digests, materialize_outbox
from boa_oi.platform import database_url, engine_for

logger = logging.getLogger("boa.notification.worker")
running = True


def _stop(_signum, _frame) -> None:
    global running
    running = False


def run() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    factory = sessionmaker(bind=engine_for(database_url()), expire_on_commit=False)
    interval = max(1.0, float(os.getenv("NOTIFICATION_POLL_INTERVAL_SECONDS", "5")))
    while running:
        session: Session = factory()
        try:
            materialized = materialize_outbox(session, limit=100)
            digests = asyncio.run(materialize_daily_digests(session))
            delivered = dispatch_due(session, limit=50)
            if materialized or digests["created"] or delivered["claimed"] or delivered["uncertain"]:
                logger.info(
                    "notification cycle materialized=%s digests=%s claimed=%s "
                    "sent=%s failed=%s uncertain=%s",
                    materialized,
                    digests["created"],
                    delivered["claimed"],
                    delivered["sent"],
                    delivered["failed"],
                    delivered["uncertain"],
                )
        except Exception:
            session.rollback()
            logger.exception("notification worker cycle failed")
        finally:
            session.close()
        if running:
            time.sleep(interval)


if __name__ == "__main__":
    run()
