"""Request and cost budgets for governed provider verification.

Two separate ceilings guard every provider-backed run, and both are supplied
explicitly by David rather than defaulted here.

**Requests.** Every provider request counts: planned calls, retries, pagination
follow-ups, and any fallback. Nothing is hidden outside the counter. The budget
refuses a request *before* it is issued rather than reporting an overrun after
the fact, so an exceeded ceiling can never produce an extra real call.

**Cost.** GA4 and Google Search Console metadata endpoints carry no published
per-request charge, so the *known direct* cost of the exact supported
operations is modelled as zero. That is deliberately not the same as claiming
the calls are free:

- Quota consumption is a real operational cost and is recorded as Unknown.
- An operation whose cost model is not known is refused outright rather than
  assumed to be zero.
- **A zero expected direct charge never implies permission.** The approved cost
  ceiling is mandatory regardless, because approval is a governance act and not
  an arithmetic consequence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BUDGET_CONTRACT = "musimack_provider_verification_budget.v1"

# Operations whose direct monetary charge is known to be zero under the
# standard Google quota model. Anything absent from this set has an unknown
# cost model and is refused.
KNOWN_ZERO_DIRECT_COST_OPERATIONS = frozenset(
    {
        "ga4.properties.getMetadata",
        "gsc.sites.get",
    }
)

UNKNOWN_INDIRECT_COST_NOTE = (
    "Quota consumption, rate limiting, and any downstream billing interaction "
    "are not bounded by repository evidence and are recorded as Unknown."
)


class ProviderBudgetError(RuntimeError):
    """A ceiling was missing, exceeded, or could not be applied."""


class UnknownCostOperationError(ProviderBudgetError):
    """An operation whose cost model is unknown was proposed."""


@dataclass
class RequestBudget:
    """A hard, pre-issue request ceiling for one profile's run."""

    max_requests: int
    executed: int = 0
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.max_requests, int) or isinstance(self.max_requests, bool):
            raise ProviderBudgetError("request ceiling must be an integer")
        if self.max_requests < 0:
            raise ProviderBudgetError("request ceiling cannot be negative")

    @property
    def remaining(self) -> int:
        return self.max_requests - self.executed

    def check_plan(self, planned_requests: int) -> None:
        """Refuse before credentials if the plan cannot fit the ceiling."""
        if planned_requests > self.max_requests:
            raise ProviderBudgetError(
                f"planned {planned_requests} provider requests exceed the approved "
                f"ceiling of {self.max_requests}. No credential was read and no "
                "provider client was constructed."
            )
        if planned_requests > 0 and self.max_requests == 0:
            raise ProviderBudgetError(
                "the approved request ceiling is zero while provider requests are "
                "planned. No credential was read and no provider client was constructed."
            )

    def consume(self, operation: str) -> None:
        """Account for exactly one provider request, refusing before issue."""
        if self.remaining <= 0:
            raise ProviderBudgetError(
                f"request ceiling of {self.max_requests} reached; {operation} was not issued"
            )
        self.executed += 1
        self.log.append(operation)

    def evidence(self) -> dict[str, object]:
        return {
            "request_ceiling": self.max_requests,
            "provider_requests_executed": self.executed,
            "provider_requests_remaining": self.remaining,
            "provider_operations_executed": list(self.log),
        }


@dataclass
class CostBudget:
    """A hard cost ceiling, mandatory even where expected direct cost is zero."""

    max_cost: float
    known_direct_cost: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.max_cost, bool) or not isinstance(self.max_cost, (int, float)):
            raise ProviderBudgetError("cost ceiling must be numeric")
        if self.max_cost < 0:
            raise ProviderBudgetError("cost ceiling cannot be negative")

    def check_operations(self, operations: list[str]) -> None:
        """Refuse any operation whose cost model is not known."""
        unknown = sorted({op for op in operations if op not in KNOWN_ZERO_DIRECT_COST_OPERATIONS})
        if unknown:
            raise UnknownCostOperationError(
                f"cost cannot be bounded for {', '.join(unknown)}: the operation is not in "
                "the known-cost set and is refused rather than assumed free."
            )

    def check_plan(self, expected_direct_cost: float) -> None:
        if expected_direct_cost > self.max_cost:
            raise ProviderBudgetError(
                f"expected direct cost {expected_direct_cost} exceeds the approved "
                f"ceiling of {self.max_cost}."
            )

    def evidence(self) -> dict[str, object]:
        return {
            "cost_ceiling": self.max_cost,
            "expected_known_direct_cost": self.known_direct_cost,
            "known_accumulated_direct_cost": self.known_direct_cost,
            "unknown_indirect_effects": UNKNOWN_INDIRECT_COST_NOTE,
        }


def expected_direct_cost(operations: list[str]) -> float:
    """Known direct monetary cost of a planned operation set.

    Zero for the supported metadata operations. Callers must still supply an
    approved ceiling: this function reports arithmetic, not permission.
    """
    unknown = sorted({op for op in operations if op not in KNOWN_ZERO_DIRECT_COST_OPERATIONS})
    if unknown:
        raise UnknownCostOperationError(
            f"no known direct cost model for {', '.join(unknown)}"
        )
    return 0.0
