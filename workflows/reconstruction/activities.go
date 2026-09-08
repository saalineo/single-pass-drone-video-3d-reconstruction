package reconstruction

const (
	ControlTaskQueue = "CONTROL_TASK_QUEUE" // hosts ReconstructionWorkflow itself
	CVTaskQueue      = "CV_TASK_QUEUE"      // hosts all Python activity implementations (default/local)
	CVTaskQueueColab = "CV_TASK_QUEUE_COLAB" // dedicated queue for Colab GPU workers
)

// Activity names are strings, not Go function references, because the
// implementations live in a different SDK/language (Python, Phase 3). Temporal
// dispatches activities by registered name across languages; the Go workflow
// only needs to agree on the string and the (de)serialized payload shape.
const (
	ActivityCuration   = "ActivityCuration"
	ActivitySfM        = "ActivitySfM"
	ActivityMasking    = "ActivityMasking"
	ActivityDepth      = "ActivityDepth"
	ActivityDense3DGS  = "ActivityDense3DGS"
	ActivityMeshing    = "ActivityMeshing"
	ActivityGeoref     = "ActivityGeoref"
	ActivityProductGen = "ActivityProductGen"
)

const SignalROIReprocess = "roi_reprocess"

// StageInput / StageOutput are the shared envelope for every activity. Keeping
// one shape (rather than a bespoke struct per stage) means the workflow's DAG
// code is uniform and the idempotency bookkeeping lives in one place.
type StageInput struct {
	MissionID string            `json:"mission_id"`
	RunID     string            `json:"run_id"`
	Stage     string            `json:"stage"`
	InputHash string            `json:"input_hash"` // see hash.go
	InputURIs []string          `json:"input_uris"`  // upstream artifact(s)
	Params    map[string]string `json:"params"`
}

type StageOutput struct {
	OutputURI  string             `json:"output_uri"`
	OutputHash string             `json:"output_hash"`
	Metrics    map[string]float64 `json:"metrics"`
}
