from temporalio import activity

from common.schemas import VioParseInput, VioParseOutput


@activity.defn(name="parse_vio_warm_start")
async def parse_vio_warm_start(payload: VioParseInput) -> VioParseOutput:
    activity.logger.warning(
        "STUB parse_vio_warm_start invoked — real implementation lands day 14",
        extra={"mission_id": payload.mission_id},
    )
    return VioParseOutput(
        mission_id=payload.mission_id, attempt_id="stub", priors_manifest_uri=""
    )
