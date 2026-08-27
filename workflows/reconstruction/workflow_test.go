package reconstruction

import (
	"context"
	"fmt"
	"testing"

	"github.com/stretchr/testify/mock"
	"go.temporal.io/sdk/activity"
	"go.temporal.io/sdk/temporal"
	"go.temporal.io/sdk/testsuite"
)

func dummyActivity(ctx context.Context, in StageInput) (StageOutput, error) {
	return StageOutput{}, nil
}

func TestReconstructionWorkflow_Success(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	for _, stage := range pipelineStages {
		env.RegisterActivityWithOptions(dummyActivity, activity.RegisterOptions{Name: stage.name})
	}

	for _, stage := range pipelineStages {
		stageName := stage.name
		env.OnActivity(stageName, mock.Anything, mock.Anything).Return(
			func(ctx context.Context, in StageInput) (StageOutput, error) {
				return StageOutput{
					OutputURI:  fmt.Sprintf("s3://recon-artifacts/missions/%s/%s/output.json", in.MissionID, stageName),
					OutputHash: "mockedhash123",
					Metrics:    map[string]float64{"duration_sec": 12.5},
				}, nil
			},
		)
	}

	input := ReconstructionWorkflowInput{
		MissionID: "mission-test-01",
		RunID:     "run-test-01",
		Preset:    "standard",
		InputURIs: []string{"s3://recon-raw/missions/mission-test-01/raw/video/manifest.json"},
	}

	env.ExecuteWorkflow(ReconstructionWorkflow, input)

	if !env.IsWorkflowCompleted() {
		t.Fatalf("expected workflow to complete")
	}
	if err := env.GetWorkflowError(); err != nil {
		t.Fatalf("expected no workflow error, got: %v", err)
	}

	var res ReconstructionWorkflowResult
	if err := env.GetWorkflowResult(&res); err != nil {
		t.Fatalf("failed to get workflow result: %v", err)
	}

	if res.Status != "completed" {
		t.Errorf("expected status 'completed', got %q", res.Status)
	}
	if len(res.ProductURIs) == 0 {
		t.Errorf("expected non-empty product URIs")
	}
}

func TestReconstructionWorkflow_StageDependencyWiring(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	for _, stage := range pipelineStages {
		env.RegisterActivityWithOptions(dummyActivity, activity.RegisterOptions{Name: stage.name})
	}

	received := map[string]StageInput{}
	for _, stage := range pipelineStages {
		stageName := stage.name
		env.OnActivity(stageName, mock.Anything, mock.Anything).Return(
			func(ctx context.Context, in StageInput) (StageOutput, error) {
				received[stageName] = in
				return StageOutput{
					OutputURI:  fmt.Sprintf("s3://recon-artifacts/missions/%s/%s/output.json", in.MissionID, stageName),
					OutputHash: stageName + "-hash",
					Metrics:    map[string]float64{"duration_sec": 1},
				}, nil
			},
		)
	}

	input := ReconstructionWorkflowInput{
		MissionID: "mission-test-03",
		RunID:     "run-test-03",
		Preset:    "standard",
		InputURIs: []string{"s3://recon-raw/missions/mission-test-03/raw/video/manifest.json"},
	}

	env.ExecuteWorkflow(ReconstructionWorkflow, input)

	if !env.IsWorkflowCompleted() {
		t.Fatalf("expected workflow to complete")
	}
	if err := env.GetWorkflowError(); err != nil {
		t.Fatalf("expected no workflow error, got: %v", err)
	}

	curationOut := fmt.Sprintf("s3://recon-artifacts/missions/%s/%s/output.json", input.MissionID, ActivityCuration)
	sfmOut := fmt.Sprintf("s3://recon-artifacts/missions/%s/%s/output.json", input.MissionID, ActivitySfM)
	maskingOut := fmt.Sprintf("s3://recon-artifacts/missions/%s/%s/output.json", input.MissionID, ActivityMasking)

	// Masking must see Curation's manifest directly, not SfM's output.
	if got := received[ActivityMasking].InputURIs; len(got) != 1 || got[0] != curationOut {
		t.Errorf("ActivityMasking InputURIs = %v, want [%s]", got, curationOut)
	}

	// Depth needs Curation + SfM + Masking together, in that order.
	wantDepthInputs := []string{curationOut, sfmOut, maskingOut}
	if got := received[ActivityDepth].InputURIs; fmt.Sprint(got) != fmt.Sprint(wantDepthInputs) {
		t.Errorf("ActivityDepth InputURIs = %v, want %v", got, wantDepthInputs)
	}

	// set_id/attempt_id must be threaded forward via Params, not re-derived.
	if got := received[ActivityMasking].Params["set_id"]; got != ActivityCuration+"-hash" {
		t.Errorf("ActivityMasking Params[set_id] = %q, want %q", got, ActivityCuration+"-hash")
	}
	if got := received[ActivityDepth].Params["attempt_id"]; got != ActivitySfM+"-hash" {
		t.Errorf("ActivityDepth Params[attempt_id] = %q, want %q", got, ActivitySfM+"-hash")
	}
}

func TestReconstructionWorkflow_NonRetryableQualityGateFailure(t *testing.T) {
	testSuite := &testsuite.WorkflowTestSuite{}
	env := testSuite.NewTestWorkflowEnvironment()

	for _, stage := range pipelineStages {
		env.RegisterActivityWithOptions(dummyActivity, activity.RegisterOptions{Name: stage.name})
	}

	// First activity succeeds
	env.OnActivity(ActivityCuration, mock.Anything, mock.Anything).Return(
		StageOutput{OutputURI: "s3://recon-artifacts/curation.json"}, nil,
	)

	// Second activity (SfM) fails with QualityGateFailure
	env.OnActivity(ActivitySfM, mock.Anything, mock.Anything).Return(
		StageOutput{}, temporal.NewNonRetryableApplicationError("BA residual exceeds limit", "QualityGateFailure", nil),
	)

	input := ReconstructionWorkflowInput{
		MissionID: "mission-test-02",
		RunID:     "run-test-02",
		Preset:    "standard",
		InputURIs: []string{"s3://recon-raw/missions/mission-test-02/raw/video/manifest.json"},
	}

	env.ExecuteWorkflow(ReconstructionWorkflow, input)

	if !env.IsWorkflowCompleted() {
		t.Fatalf("expected workflow to complete (fail fast)")
	}
	err := env.GetWorkflowError()
	if err == nil {
		t.Fatalf("expected workflow error on QualityGateFailure, got nil")
	}
}
