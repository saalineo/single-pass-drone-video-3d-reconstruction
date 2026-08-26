from temporalio import activity

from common.schemas import SfmFeaturesInput, SfmFeaturesOutput, BundleAdjustmentInput, BundleAdjustmentOutput


@activity.defn(name="extract_and_match_features")
async def extract_and_match_features(payload: SfmFeaturesInput) -> SfmFeaturesOutput:
    activity.logger.warning(
        "STUB extract_and_match_features invoked — real implementation lands day 15/16",
        extra={"mission_id": payload.mission_id},
    )
    return SfmFeaturesOutput(
        mission_id=payload.mission_id, attempt_id="stub", database_uri=""
    )


@activity.defn(name="run_bundle_adjustment")
async def run_bundle_adjustment(payload: BundleAdjustmentInput) -> BundleAdjustmentOutput:
    activity.logger.warning(
        "STUB run_bundle_adjustment invoked — real implementation lands day 15/16",
        extra={"mission_id": payload.mission_id},
    )
    return BundleAdjustmentOutput(
        mission_id=payload.mission_id, attempt_id="stub", sfm_result_uri=""
    )
