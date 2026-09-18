from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

from .ports import CanonicalAccount, CanonicalCustomer, CanonicalTransaction


class InMemoryCoreBankingAdapter:
    def __init__(
        self,
        customers: Sequence[CanonicalCustomer],
        accounts: Sequence[CanonicalAccount],
    ) -> None:
        self._customers = tuple(customers)
        self._accounts = tuple(accounts)

    def fetch_customers(self) -> tuple[CanonicalCustomer, ...]:
        return self._customers

    def fetch_accounts(self) -> tuple[CanonicalAccount, ...]:
        return self._accounts


class InMemoryPaymentAdapter:
    def __init__(self, transactions: Sequence[CanonicalTransaction]) -> None:
        self._transactions = tuple(transactions)

    def fetch_transactions(
        self, from_date: date, to_date: date
    ) -> tuple[CanonicalTransaction, ...]:
        return tuple(item for item in self._transactions if from_date <= item.value_date <= to_date)


class InMemoryProductAdapter:
    def __init__(self, statuses: Mapping[tuple[str, str], str]) -> None:
        self._statuses = dict(statuses)

    def product_status(self, customer_ref: str, product_code: str) -> str:
        return self._statuses.get((customer_ref, product_code), "ABSENT")
