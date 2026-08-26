"""FIRE supplier intelligence and procurement orchestration."""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Supplier:
    name: str
    product: str
    unit_price: float | None = None
    minimum_order: int | None = None
    delivery_terms: str = ""
    payment_terms: str = ""


@dataclass
class SupplierComparison:
    product: str
    suppliers: List[Supplier] = field(default_factory=list)

    def ranked_by_price(self) -> List[Supplier]:
        """Return suppliers with known prices from lowest to highest."""
        return sorted(
            [s for s in self.suppliers if s.unit_price is not None],
            key=lambda s: s.unit_price,
        )


@dataclass
class ProcurementAction:
    action: str
    supplier: str
    requires_owner_approval: bool = True
    status: str = "PROPOSED"
