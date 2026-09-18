from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CanonicalCustomer:
    customer_ref: str
    legal_name: str
    sector_code: str
    segment_code: str


@dataclass(frozen=True, slots=True)
class CanonicalAccount:
    account_ref: str
    customer_ref: str
    account_type: str
    currency: str


@dataclass(frozen=True, slots=True)
class CanonicalTransaction:
    transaction_ref: str
    account_ref: str
    value_date: date
    direction: str
    amount: Decimal
    currency: str
    category: str
    international: bool


class CoreBankingPort(Protocol):
    def fetch_customers(self) -> Sequence[CanonicalCustomer]: ...
    def fetch_accounts(self) -> Sequence[CanonicalAccount]: ...


class PaymentPort(Protocol):
    def fetch_transactions(
        self, from_date: date, to_date: date
    ) -> Sequence[CanonicalTransaction]: ...


class ProductPort(Protocol):
    def product_status(self, customer_ref: str, product_code: str) -> str: ...
