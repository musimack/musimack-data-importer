"""P2-3B request ceilings approved in PO-011."""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import BudgetError

PROVIDER_BASE_CEILINGS = {"ga4": 6, "gsc": 4}
MAX_PROVIDER_REQUESTS_PER_TASK = 10
MAX_REQUESTS_WITH_AUTHORIZED_RETRIES = 12
DEFAULT_RETRIES = 0


@dataclass
class ProviderRequestBudget:
    provider: str
    base_ceiling: int
    authorized_retry_count: int = DEFAULT_RETRIES
    requests_consumed: int = 0
    retry_count: int = 0
    operations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        approved = PROVIDER_BASE_CEILINGS.get(self.provider)
        if approved is None:
            raise BudgetError("provider has no approved request ceiling")
        if self.base_ceiling < 0 or self.base_ceiling > approved:
            raise BudgetError("configuration request ceiling exceeds the approved provider ceiling")
        if self.base_ceiling > MAX_PROVIDER_REQUESTS_PER_TASK:
            raise BudgetError("configuration exceeds the approved task ceiling")
        if self.authorized_retry_count < 0:
            raise BudgetError("authorized retry count cannot be negative")
        if self.maximum_requests > MAX_REQUESTS_WITH_AUTHORIZED_RETRIES:
            raise BudgetError("base requests plus authorized retries exceed the approved maximum")

    @property
    def maximum_requests(self) -> int:
        return self.base_ceiling + self.authorized_retry_count

    @property
    def remaining(self) -> int:
        return self.maximum_requests - self.requests_consumed

    def check_plan(self, planned_base_requests: int) -> None:
        if planned_base_requests < 0 or planned_base_requests > self.base_ceiling:
            raise BudgetError("planned provider requests exceed the approved base ceiling")

    def consume(self, operation: str, *, retry: bool = False) -> None:
        if retry and self.retry_count >= self.authorized_retry_count:
            raise BudgetError("an unapproved provider retry was refused before issue")
        if self.requests_consumed >= self.maximum_requests:
            raise BudgetError("the provider request ceiling was reached before issue")
        if not retry and self.requests_consumed - self.retry_count >= self.base_ceiling:
            raise BudgetError("the provider base request ceiling was reached before issue")
        self.requests_consumed += 1
        if retry:
            self.retry_count += 1
        self.operations.append(str(operation)[:120])

    def evidence(self) -> dict[str, int | list[str]]:
        return {
            "request_ceiling": self.base_ceiling,
            "authorized_retry_count": self.authorized_retry_count,
            "maximum_requests_with_authorized_retries": self.maximum_requests,
            "requests_consumed": self.requests_consumed,
            "retry_count": self.retry_count,
            "provider_operations": list(self.operations),
        }
