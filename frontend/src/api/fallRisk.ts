import { requestJson } from './devices'

export type PipelineStatus =
  | 'not_configured'
  | 'ready'
  | 'waiting'
  | 'running'
  | 'completed'
  | 'failed'
  | 'skipped'

export interface PipelineState {
  status: PipelineStatus
  progress: number
  message: string | null
}

export interface GaitParameterValue {
  name: string
  display_name: string
  category: 'temporal' | 'spatial' | 'variability' | 'posture' | 'stability'
  value: number | null
  unit: string
  available: boolean
  unavailable_reason: string | null
}

export interface AssessmentQuality {
  passed: boolean
  video_duration_seconds: number | null
  source_fps: number | null
  full_body_visible_ratio: number | null
  pose_valid_ratio: number | null
  interpolated_frame_ratio: number | null
  maximum_missing_gap_frames: number | null
  heel_strike_count: number | null
  toe_off_count: number | null
  complete_step_count: number | null
  reasons: string[]
}

export interface FallRiskAssessment {
  assessment_id: string
  status: string
  stage: string
  progress: number
  device_id: string | null
  height_cm: number
  capture_duration_seconds: number
  created_at: string
  started_at: string | null
  capture_started_at: string | null
  capture_completed_at: string | null
  processing_started_at: string | null
  completed_at: string | null
  gait_pipeline: PipelineState
  gvhmr_pipeline: PipelineState
  risk_pipeline: PipelineState
  quality: AssessmentQuality
  gait_parameters: GaitParameterValue[]
  artifacts: Array<{
    artifact_id: string
    kind: string
    label: string
    media_type: string
    available: boolean
  }>
  risk_model_status: 'not_installed' | 'not_configured' | 'waiting' | 'running' | 'completed' | 'failed'
  risk_result: FallRiskModelResult | null
  error: string | null
}

export interface FallRiskWorkerStatus {
  service: 'fall-risk-worker'
  status: 'ok'
  ready: boolean
  active_assessment_id: string | null
  gait_pipeline: PipelineState
  gvhmr_pipeline: PipelineState
  risk_pipeline: PipelineState
  missing_requirements: string[]
}

export interface FallRiskConceptResult {
  predicted_level: 'normal' | 'mild' | 'moderate' | 'marked' | 'abnormal'
  predicted_level_id: number
  probabilities: Record<string, number>
  top1_probability: number
  second_best_probability: number
  margin: number
}

export interface FallRiskModelResult {
  model: {
    profile_id: string
    display_name: string
    status: string
    architecture: string
    training_scope: string
    checkpoint_epoch: number
    web_interface_compatible: boolean
    clinical_risk_calibrated: boolean
  }
  metadata: Record<string, unknown> & {
    window_count?: number
    source_frames?: number
    source_fps?: number
    input_adapter?: string
    aggregation?: string
  }
  healthy_distance: number
  risk_level: null
  concepts: Record<string, FallRiskConceptResult>
  explanation: string
}

export function fetchFallRiskStatus(signal?: AbortSignal): Promise<FallRiskWorkerStatus> {
  return requestJson('/api/fall-risk/status', signal)
}

export function fetchFallRiskAssessments(
  signal?: AbortSignal,
): Promise<FallRiskAssessment[]> {
  return requestJson('/api/fall-risk/assessments?limit=20', signal)
}

export function fetchFallRiskAssessment(
  assessmentId: string,
  signal?: AbortSignal,
): Promise<FallRiskAssessment> {
  return requestJson(`/api/fall-risk/assessments/${encodeURIComponent(assessmentId)}`, signal)
}

export function fallRiskArtifactUrl(assessmentId: string, artifactId: string): string {
  return `/api/fall-risk/assessments/${encodeURIComponent(assessmentId)}/artifacts/${encodeURIComponent(artifactId)}`
}

export function createFallRiskAssessment(
  heightCm: number,
  durationSeconds: number,
  signal?: AbortSignal,
): Promise<FallRiskAssessment> {
  return requestJson('/api/fall-risk/assessments', signal, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      height_cm: heightCm,
      capture_duration_seconds: durationSeconds,
      device_id: null,
    }),
  })
}

export function runFallRiskModel(
  assessmentId: string,
  signal?: AbortSignal,
): Promise<FallRiskAssessment> {
  return requestJson(
    `/api/fall-risk/assessments/${encodeURIComponent(assessmentId)}/risk-model`,
    signal,
    { method: 'POST' },
  )
}
