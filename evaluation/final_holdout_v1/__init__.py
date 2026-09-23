"""Final holdout evaluation contract V1.

This package is deliberately outside ``src/renewables_permitting``.  It scores
immutable extraction snapshots produced by the frozen production commit and
never executes extraction or imports model-provider clients.
"""

from evaluation.final_holdout_v1.contract import (
    CONTRACT_VERSION,
    FROZEN_EXTRACTION_CONFIG_ID,
    FROZEN_PRODUCTION_COMMIT,
)

__all__ = [
    "CONTRACT_VERSION",
    "FROZEN_EXTRACTION_CONFIG_ID",
    "FROZEN_PRODUCTION_COMMIT",
]
