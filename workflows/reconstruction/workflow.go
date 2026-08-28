package reconstruction

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

type ReconstructionWorkflowInput struct {
	MissionID string
	RunID     string
	Preset    string   // "standard" | "fast-preview" | "high-fidelity"
	InputURIs []string // committed raw video segment object URIs from ingest, doc 04 §2
}

type ReconstructionWorkflowResult struct {
	ProductURIs []string
	Status      string
}

// stageSpec pairs an activity name with the timeout/retry profile appropriate
// to its resource class. GPU-heavy stages get long StartToCloseTimeout and a
// HeartbeatTimeout so a hung/OOM'd worker is detected well before the
// timeout, per doc 02 §7.
type stageSpec struct {
	name             string
	startToClose     time.Duration
	heartbeatTimeout time.Duration
	maxAttempts      int32
	memoryHint       string // passed through in Params, read by the scheduler
}

var pipelineStages = []stageSpec{
	{ActivityCuration, 1 * time.Hour, 10 * time.Minute, 5, "cpu-standard"},
	{ActivitySfM, 2 * time.Hour, 10 * time.Minute, 5, "gpu-standard"},
	{ActivityMasking, 90 * time.Minute, 10 * time.Minute, 5, "gpu-standard"},
	{ActivityDepth, 3 * time.Hour, 10 * time.Minute, 5, "gpu-standard"},
	{ActivityDense3DGS, 6 * time.Hour, 10 * time.Minute, 3, "gpu-high-vram"},
	{ActivityMeshing, 2 * time.Hour, 10 * time.Minute, 5, "gpu-standard"},
	{ActivityGeoref, 30 * time.Minute, 5 * time.Minute, 5, "cpu-standard"},
	{ActivityProductGen, 90 * time.Minute, 10 * time.Minute, 5, "gpu-standard"},
}

// stageDeps records, per activity, which prior activities' artifacts it needs as
// InputURIs. The pipeline is not a strict chain: e.g. Masking needs Curation's
// keyframe manifest directly (not SfM's pose file), and Depth needs the keyframe
// set, the SfM sparse model, and the masks all at once. Curation has no entry — it
// consumes ReconstructionWorkflowInput.InputManifestURI instead.
var stageDeps = map[string][]string{
	ActivitySfM:        {ActivityCuration},
	ActivityMasking:    {ActivityCuration},
	ActivityDepth:      {ActivityCuration, ActivitySfM, ActivityMasking},
	ActivityDense3DGS:  {ActivityCuration, ActivitySfM, ActivityDepth, ActivityMasking},
	ActivityMeshing:    {ActivityDense3DGS},
	ActivityGeoref:     {ActivityMeshing},
	ActivityProductGen: {ActivityMeshing, ActivityGeoref},
}

func ReconstructionWorkflow(ctx workflow.Context, in ReconstructionWorkflowInput) (*ReconstructionWorkflowResult, error) {
	logger := workflow.GetLogger(ctx)

	outputs := map[string]StageOutput{}
	// Content-hash IDs (set_id, attempt_id, ...) that later stages resolve their
	// mission-scoped artifacts by, keyed by the producing stage's activity name and
	// threaded forward via Params rather than re-derived from manifest content.
	sharedParams := map[string]string{}
	var lastOutput StageOutput

	for _, spec := range pipelineStages {
		ao := workflow.ActivityOptions{
			TaskQueue:           CVTaskQueue,
			StartToCloseTimeout: spec.startToClose,
			HeartbeatTimeout:    spec.heartbeatTimeout,
			RetryPolicy: &temporal.RetryPolicy{
				InitialInterval:    10 * time.Second,
				BackoffCoefficient: 2.0,
				MaximumInterval:    10 * time.Minute,
				MaximumAttempts:    spec.maxAttempts,
				// Non-retryable errors: the Python activity raises this
				// application error type when a stage fails a hard quality
				// gate (e.g. BA residual threshold, doc 02 §7) rather than a
				// transient fault — retrying would just waste GPU-hours.
				NonRetryableErrorTypes: []string{"QualityGateFailure"},
			},
		}
		actx := workflow.WithActivityOptions(ctx, ao)

		inputURIs := in.InputURIs
		if deps, ok := stageDeps[spec.name]; ok {
			inputURIs = make([]string, 0, len(deps))
			for _, dep := range deps {
				inputURIs = append(inputURIs, outputs[dep].OutputURI)
			}
		}

		params := map[string]string{
			"preset":      in.Preset,
			"memory_hint": spec.memoryHint,
		}
		for k, v := range sharedParams {
			params[k] = v
		}

		stageIn := StageInput{
			MissionID: in.MissionID,
			RunID:     in.RunID,
			Stage:     spec.name,
			InputHash: ComputeInputHash(inputURIs, params),
			InputURIs: inputURIs,
			Params:    params,
		}

		var out StageOutput
		if err := workflow.ExecuteActivity(actx, spec.name, stageIn).Get(actx, &out); err != nil {
			logger.Error("stage failed", "stage", spec.name, "error", err)
			return &ReconstructionWorkflowResult{Status: fmt.Sprintf("failed:%s", spec.name)}, err
		}

		outputs[spec.name] = out
		lastOutput = out

		// Every stage's OutputHash is that stage's content-addressed id (set_id,
		// attempt_id, ...); expose Curation's and SfM's under the conventional
		// param names downstream Python activities key their mission-scoped
		// artifacts by (doc 04 §2-6).
		switch spec.name {
		case ActivityCuration:
			sharedParams["set_id"] = out.OutputHash
		case ActivitySfM:
			sharedParams["attempt_id"] = out.OutputHash
		}
	}

	return &ReconstructionWorkflowResult{
		ProductURIs: []string{lastOutput.OutputURI},
		Status:      "completed",
	}, nil
}
