from temporalio import activity

from common.schemas import CurationInput, CurationOutput


@activity.defn(name="curate_keyframes")
async def curate_keyframes(payload: CurationInput) -> CurationOutput:
    activity.logger.warning(
        "STUB curate_keyframes invoked — real implementation lands day 12",
        extra={"mission_id": payload.mission_id},
    )
    return CurationOutput(
        mission_id=payload.mission_id, set_id="stub", manifest_uri="", num_kept=0, num_dropped=0
    )
