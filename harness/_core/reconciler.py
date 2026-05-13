from __future__ import annotations
from typing import TYPE_CHECKING

from harness._core.logger import StructuredLogger

if TYPE_CHECKING:
    from harness._core.airtable import AirtableClient
    from harness._core.notifier import Notifier

_log = StructuredLogger("reconciler")


class Reconciler:
    """Daily audit-vs-Airtable diff and monthly cross-week sum reconciler.

    Full implementation requires the `harness_writes_audit` Airtable table
    (open question Q9 in the master plan). Both methods are functional stubs
    that log intent without making live API calls until the audit table is
    confirmed created and its table ID is known.
    """

    def __init__(
        self,
        client: "AirtableClient",
        audit_table_id: str,
        notifier: "Notifier",
    ) -> None:
        self._client = client
        self._audit_table_id = audit_table_id
        self._notifier = notifier

    def run_daily(self, domain: str, week: str) -> None:
        """Compare harness_writes_audit entries against current Airtable values.

        On mismatch (post-PATCH manual edit detected), fires DRIFT_FOUND_POST_COMMIT
        notification via the notifier.

        TODO: Implement once audit_table_id is confirmed (master plan Q9).
        """
        _log.info(
            "reconciler.run_daily stub — audit table not yet provisioned",
            domain=domain,
            week=week,
            audit_table_id=self._audit_table_id,
        )
        # Implementation outline when audit table exists:
        # 1. GET all audit records for (domain, week) from harness_writes_audit
        # 2. For each record_id in audit, GET current value from Airtable
        # 3. Diff audit.fare vs live.fare; diff audit.unload vs live.unload
        # 4. On mismatch: self._notifier.notify(severity="CRITICAL", ...)
        # 5. Return list of drift tuples for caller to log/escalate

    def run_monthly_sum(self, driver_ids: list[str]) -> None:
        """Sum all settlement weeks in the rolling month per driver.

        Compare against ops-provided bank transfer CSV totals (₩0 tolerance).

        TODO: Implement once audit_table_id is confirmed (master plan Q9).
        """
        _log.info(
            "reconciler.run_monthly_sum stub — audit table not yet provisioned",
            driver_count=len(driver_ids),
            audit_table_id=self._audit_table_id,
        )
        # Implementation outline:
        # 1. GET all audit records for rolling 4-week window
        # 2. Sum net (post-withholding) per driver_id
        # 3. Accept ops CSV path as param; parse and diff
        # 4. If any driver delta != 0: notify CRITICAL + dump diff table
