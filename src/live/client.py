"""CLOB client wrapper with dry-run support."""

from __future__ import annotations

import logging
from typing import Optional

from src.config import CHAIN_ID, CLOB_API_BASE, DRY_RUN, LiveCredentials
from src.models import OrderRequest, OrderResult

logger = logging.getLogger(__name__)


class ClobClient:
    """Wraps py-clob-client SDK with dry-run mode."""

    def __init__(self, credentials: LiveCredentials, dry_run: bool = DRY_RUN) -> None:
        self.dry_run = dry_run
        self._client: Optional[object] = None

        if not dry_run:
            try:
                from py_clob_client.client import ClobClient as _SdkClient
                from py_clob_client.clob_types import ApiCreds

                creds = ApiCreds(
                    api_key=credentials.api_key,
                    api_secret=credentials.api_secret,
                    api_passphrase=credentials.api_passphrase,
                )
                self._client = _SdkClient(
                    CLOB_API_BASE,
                    key=credentials.private_key,
                    chain_id=CHAIN_ID,
                    creds=creds,
                )
                logger.info("CLOB client initialized (LIVE mode)")
            except ImportError:
                raise ImportError(
                    "py-clob-client is required for live trading.\n"
                    "Install: pip install py-clob-client"
                )
        else:
            logger.info("CLOB client initialized (DRY_RUN mode)")

    def place_order(self, request: OrderRequest) -> OrderResult:
        """Place an order. In dry-run mode, logs but does not execute."""
        logger.info(
            "Order: %s %s @ %.3f size=%.2f type=%s post_only=%s%s",
            request.side,
            request.token_id[:8],
            request.price,
            request.size,
            request.order_type,
            request.post_only,
            " [DRY_RUN]" if self.dry_run else "",
        )

        if self.dry_run:
            return OrderResult(
                order_id="dry_run",
                status="DRY_RUN",
                filled_size=request.size,
                avg_fill_price=request.price,
            )

        return self._execute_order(request)

    def _execute_order(self, request: OrderRequest) -> OrderResult:
        """Execute order via SDK."""
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        assert self._client is not None

        side = BUY if request.side == "BUY" else SELL

        order_args = OrderArgs(
            price=request.price,
            size=request.size,
            side=side,
            token_id=request.token_id,
        )

        try:
            signed_order = self._client.create_order(order_args)  # type: ignore[union-attr]
            resp = self._client.post_order(signed_order, request.order_type)  # type: ignore[union-attr]

            order_id = resp.get("orderID", "")
            status = resp.get("status", "UNKNOWN")

            logger.info("Order placed: id=%s status=%s", order_id, status)
            return OrderResult(
                order_id=order_id,
                status=status,
            )
        except Exception as exc:
            logger.error("Order failed: %s", exc)
            return OrderResult(
                order_id="",
                status="FAILED",
            )

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        if self.dry_run:
            logger.info("Cancel order %s [DRY_RUN]", order_id)
            return True

        try:
            assert self._client is not None
            self._client.cancel(order_id)  # type: ignore[union-attr]
            logger.info("Cancelled order %s", order_id)
            return True
        except Exception as exc:
            logger.error("Cancel failed for %s: %s", order_id, exc)
            return False

    def cancel_all(self) -> bool:
        """Cancel all open orders."""
        if self.dry_run:
            logger.info("Cancel all orders [DRY_RUN]")
            return True

        try:
            assert self._client is not None
            self._client.cancel_all()  # type: ignore[union-attr]
            logger.info("Cancelled all orders")
            return True
        except Exception as exc:
            logger.error("Cancel all failed: %s", exc)
            return False

    def get_open_orders(self) -> list[dict]:
        """Get all open orders."""
        if self.dry_run:
            return []

        try:
            assert self._client is not None
            return self._client.get_orders()  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("Get orders failed: %s", exc)
            return []
