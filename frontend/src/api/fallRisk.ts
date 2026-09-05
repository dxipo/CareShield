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
  original_video_duration_seconds: number | null
  selected_start_seconds: number | null
  selected_end_seconds: number | null
  discarded_duration_seconds: number | null
  source_fps: number | null
  full_body_visible_ratio: number | null
  pose_valid_ratio: number | null
  interpolated_frame_ratio: number | null
  maximum_missing_gap_frames: number | null
  maximum_missing_gap_seconds: number | null
  heel_strike_count: number | null
  toe_off_count: number | null
  complete_step_count: number | null
  reasons: string[]
}

export interface GaitAnalysisState {
  requested_mode: 'legacy' | 'gaitkit_shadow' | 'gaitkit_primary'
  primary_source: 'visionmd_camera' | 'gaitkit_world'
  primary_algorithm_id: string
  primary_algorithm_version: string
  gaitkit_status: 'not_configured' | 'waiting' | 'running' | 'completed' | 'failed' | 'skipped'
  shadow_algorithm_id: string | null
  shadow_algorithm_version: string | null
  metric_definition_version: string | null
  analysis_fps: number | null
  fallback_used: boolean
  message: string | null
}

export interface FallRiskAssessment {
  assessment_id: string
  status: string
  stage: string
  progress: number
  device_id: string | null
  input_source: 'camera' | 'uploaded_video'
  source_filename: string | null
  subject_name: string | null
  sex: 'male' | 'female' | null
  age: number | null
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
  gait_analysis: GaitAnalysisState
  gait_parameters: GaitParameterValue[]
  artifacts: Array<{
    artifact_id: string
    kind: string
    label: string
    media_type: string
    available: boolean
  }>
  risk_model_status: 'not_installed' | 'not_configured' | 'waiting' | 'running' | 'completed' | 'failed' | 'skipped'
  risk_result: FallRiskModelResult | null
  kinecal_pipeline: PipelineState
  kinecal_model_status: 'not_installed' | 'not_configured' | 'waiting' | 'running' | 'completed' | 'failed' | 'skipped'
  fall_risk_result: KinecalFallRiskResult | null
  screening_result: FallRiskScreeningResult | null
  secondary_assessment_status: 'waiting' | 'not_triggered' | 'completed' | 'review_required' | 'unavailable'
  error: string | null
}

export interface FallRiskWorkerStatus {
  service: 'fall-risk-worker'
  status: 'ok'
  ready: boolean
  active_assessment_id: string | null
  gait_pipeline: PipelineState
  gait_parameter_mode: 'legacy' | 'gaitkit_shadow' | 'gaitkit_primary'
  gaitkit_pipeline: PipelineState
  gvhmr_pipeline: PipelineState
  risk_pipeline: PipelineState
  kinecal_pipeline: PipelineState
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
  risk_level: 'low' | 'medium' | 'high' | null
  concepts: Record<string, FallRiskConceptResult>
  explanation: string
}

export interface KinecalFallRiskResult {
  model: {
    model_id: string
    display_name: string
    architecture: 'stgcnpp_action_adapter'
    version: string
    checkpoint_sha256: string
    training_domain: string
    clinical_risk_calibrated: boolean
  }
  risk_level: 'low' | 'medium' | 'high'
  predicted_class: 0 | 1 | 2
  predicted_group: 'NF' | 'FHs' | 'FHm'
  class_probabilities: Record<'low' | 'medium' | 'high', number>
  raw_class_probabilities: Record<'low' | 'medium' | 'high', number>
  confidence: number
  action_type: '3m-walk-Front-View'
  source_frames: number
  source_fps: number
  source_duration_seconds: number
  clip_frames: 120
  input_adapter: string
  input_quality: 'usable' | 'review'
  limitations: string[]
  metadata: Record<string, unknown>
}

export interface FallRiskScreeningResult {
  outcome: 'normal' | 'at_risk' | 'review_required' | 'unavailable'
  normal_evidence: number
  risk_evidence: number
  confidence: number
  source_model_id: string
  raw_risk_level: 'low' | 'medium' | 'high'
  raw_group: 'NF' | 'FHs' | 'FHm'
  decision_version: 'kinecal-binary-gate-v1'
  discordant: boolean
  reason: string
}

export function fetchFallRiskStatus(signal?: AbortSignal): Promise<FallRiskWorkerStatus> {
  return requestJson('/api/fall-risk/status', signal)
}

export function fetchFallRiskAssessments(
  signal?: AbortSignal,
): Promise<FallRiskAssessment[]> {
  return requestJson('/api/fall-risk/assessments?limit=100', signal)
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
  subjectName: string,
  sex: 'male' | 'female',
  age: number,
  heightCm: number,
  durationSeconds: number,
  signal?: AbortSignal,
): Promise<FallRiskAssessment> {
  return requestJson('/api/fall-risk/assessments', signal, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      subject_name: subjectName,
      sex,
      age,
      height_cm: heightCm,
      capture_duration_seconds: durationSeconds,
      device_id: null,
    }),
  })
}

export function createFallRiskVideoAssessment(
  file: File,
  subjectName: string,
  sex: 'male' | 'female',
  age: number,
  heightCm: number,
  durationSeconds: number,
  signal?: AbortSignal,
): Promise<FallRiskAssessment> {
  const query = new URLSearchParams({
    subject_name: subjectName,
    sex,
    age: String(age),
    height_cm: String(heightCm),
    capture_duration_seconds: String(durationSeconds),
    source_filename: file.name,
  })
  return requestJson(`/api/fall-risk/assessments/upload?${query}`, signal, {
    method: 'POST',
    headers: { 'Content-Type': 'video/mp4' },
    body: file,
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
