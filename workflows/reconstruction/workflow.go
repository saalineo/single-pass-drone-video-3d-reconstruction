package reconstruction

import (
	"fmt"
	"time"

	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/workflow"
)

type ReconstructionWorkflowInput struct {
	MissionID        string
	RunID            string
	Preset           string // "standard" | "fast-preview" | "high-fidelity"
	InputManifestURI string // curated segment manifest from ingest, doc 04 §2
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
	{ActivityCuration, 1 * time.Hour, 30 * time.Second, 5, "cpu-standard"},
	{ActivitySfM, 2 * time.Hour, 30 * time.Second, 5, "gpu-standard"},
	{ActivityMasking, 90 * time.Minute, 30 * time.Second, 5, "gpu-standard"},
	{ActivityDepth, 3 * time.Hour, 60 * time.Second, 5, "gpu-standard"},
	{ActivityDense3DGS, 6 * time.Hour, 60 * time.Second, 3, "gpu-high-vram"},
	{ActivityMeshing, 2 * time.Hour, 60 * time.Second, 5, "gpu-standard"},
	{ActivityGeoref, 30 * time.Minute, 20 * time.Second, 5, "cpu-standard"},
	{ActivityProductGen, 90 * time.Minute, 30 * time.Second, 5, "gpu-standard"},
}

func ReconstructionWorkflow(ctx workflow.Context, in ReconstructionWorkflowInput) (*ReconstructionWorkflowResult, error) {
	logger := workflow.GetLogger(ctx)

	upstream := []string{in.InputManifestURI}
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

		params := map[string]string{
			"preset":      in.Preset,
			"memory_hint": spec.memoryHint,
		}
		stageIn := StageInput{
			MissionID: in.MissionID,
			RunID:     in.RunID,
			Stage:     spec.name,
			InputHash: ComputeInputHash(upstream, params),
			InputURIs: upstream,
			Params:    params,
		}

		var out StageOutput
		if err := workflow.ExecuteActivity(actx, spec.name, stageIn).Get(actx, &out); err != nil {
			logger.Error("stage failed", "stage", spec.name, "error", err)
			return &ReconstructionWorkflowResult{Status: fmt.Sprintf("failed:%s", spec.name)}, err
		}

		lastOutput = out
		upstream = []string{out.OutputURI} // next stage's sole declared input
	}

	return &ReconstructionWorkflowResult{
		ProductURIs: []string{lastOutput.OutputURI},
		Status:      "completed",
	}, nil
}
