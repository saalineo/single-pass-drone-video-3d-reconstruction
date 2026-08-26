from temporalio import activity

from common.schemas import MaskingInput, MaskingOutput


@activity.defn(name="mask_dynamic_objects")
async def mask_dynamic_objects(payload: MaskingInput) -> MaskingOutput:
    activity.logger.warning(
        "STUB mask_dynamic_objects invoked — real implementation lands day 17",
        extra={"mission_id": payload.mission_id},
    )
    return MaskingOutput(
        mission_id=payload.mission_id, set_id="stub", mask_manifest_uri=""
    )
