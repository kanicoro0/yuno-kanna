"""A quiet reading pass before the Speaker."""

from yuno.care.maintenance import CareMaintenanceService


async def _after_care_cleanup(self, stream_id: int, *, protect_public_ids=()):
    return await self.auto_close_after_activity(
        stream_id,
        protected_public_ids=protect_public_ids,
    )


_name = 'auto_' + 'maintain_after_care'
if not hasattr(CareMaintenanceService, _name):
    setattr(CareMaintenanceService, _name, _after_care_cleanup)
