<script setup lang="ts">
import { DataAnalysis, VideoCamera } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  createFallRiskAssessment,
  fallRiskArtifactUrl,
  fetchFallRiskAssessment,
  fetchFallRiskAssessments,
  fetchFallRiskStatus,
  runFallRiskModel,
  type FallRiskAssessment,
  type FallRiskWorkerStatus,
  type GaitParameterValue,
} from '../api/fallRisk'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'

const worker = ref<FallRiskWorkerStatus | null>(null)
const assessments = ref<FallRiskAssessment[]>([])
const active = ref<FallRiskAssessment | null>(null)
const heightCm = ref(170)
const durationSeconds = ref(15)
const loading = ref(true)
const submitting = ref(false)
const runningRiskModel = ref(false)
const error = ref<string | null>(null)
const smplView = ref<'privacy' | 'overlay'>('privacy')
let poll: ReturnType<typeof setInterval> | null = null

const categories = [
  ['temporal', '时间参数'],
  ['spatial', '空间与运动表现'],
  ['variability', '变异性与对称性'],
  ['posture', '姿态与关节'],
  ['stability', '平衡稳定性'],
] as const

const conceptLabels: Record<string, string> = {
  step_length: '步幅',
  walking_speed: '行走速度',
  foot_lift: '足部抬升',
  arm_swing: '摆臂幅度',
  cadence: '步频',
  step_width: '步宽',
  lateral_stability: '横向稳定性',
  stoop_posture: '弯腰姿势',
}

const levelLabels: Record<string, string> = {
  normal: '正常', mild: '轻度异常', moderate: '中度异常', marked: '显著异常', abnormal: '异常',
}

const conceptEntries = computed(() => Object.entries(active.value?.risk_result?.concepts ?? {}))

const isRunning = computed(() =>
  active.value
    ? !['quality_review', 'completed', 'partial', 'failed', 'cancelled'].includes(active.value.status)
    : false,
)

const poseQualityUsable = computed(() => {
  const quality = active.value?.quality
  return Boolean(
    quality
      && quality.pose_valid_ratio !== null
      && quality.pose_valid_ratio >= 0.8
      && quality.full_body_visible_ratio !== null
      && quality.full_body_visible_ratio >= 0.8
      && quality.interpolated_frame_ratio !== null
      && quality.interpolated_frame_ratio <= 0.2
      && quality.maximum_missing_gap_frames !== null
      && quality.maximum_missing_gap_frames <= 15,
  )
})

const gaitArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'gait_overlay') ?? null,
)

const smplIncameraArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'gvhmr_incamera') ?? null,
)

const smplGlobalArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'gvhmr_global') ?? null,
)

const smplArtifact = computed(() => (
  smplView.value === 'privacy' ? smplGlobalArtifact.value : smplIncameraArtifact.value
))

const captureWindowEnd = computed(() => {
  if (!active.value?.capture_started_at) return null
  return new Date(active.value.capture_started_at).getTime()
    + active.value.capture_duration_seconds * 1_000
})

const captureRemaining = computed(() => {
  if (active.value?.status !== 'capturing' || captureWindowEnd.value === null) return null
  return Math.max(0, Math.ceil((captureWindowEnd.value - Date.now()) / 1_000))
})

function parameters(category: string): GaitParameterValue[] {
  return active.value?.gait_parameters.filter((item) => item.category === category) ?? []
}

function formatParameter(parameter: GaitParameterValue): string {
  if (!parameter.available || parameter.value === null) return '--'
  return `${Number(parameter.value.toFixed(3))} ${parameter.unit}`
}

function formatPercent(value: number | null): string {
  return value === null ? '--' : `${Math.round(value * 100)}%`
}

function formatTime(value: string | null): string {
  if (!value) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(new Date(value))
}

function elapsedSeconds(start: string | null, end: string | null): string {
  if (!start) return '--'
  const milliseconds = (end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime()
  return `${Math.max(0, Math.round(milliseconds / 1_000))} 秒`
}

async function load(): Promise<void> {
  try {
    worker.value = await fetchFallRiskStatus()
    assessments.value = await fetchFallRiskAssessments()
    const latest = assessments.value[0]
    if (latest && (!active.value || active.value.assessment_id === latest.assessment_id)) {
      // Refresh terminal tasks too: GVHMR artifacts can arrive after the gait
      // overlay, and a terminal snapshot must not leave the UI stale.
      active.value = latest
    }
    if (active.value && isRunning.value) {
      active.value = await fetchFallRiskAssessment(active.value.assessment_id)
    }
    error.value = null
  } catch {
    error.value = '跌倒风险 Worker 当前不可访问'
  } finally {
    loading.value = false
  }
}

async function startAssessment(): Promise<void> {
  submitting.value = true
  try {
    active.value = await createFallRiskAssessment(heightCm.value, durationSeconds.value)
    error.value = null
  } catch {
    error.value = '评估无法启动，请检查 Worker、模型资产和摄像机状态'
  } finally {
    submitting.value = false
  }
}

async function analyzeExistingGvhmr(): Promise<void> {
  if (!active.value) return
  runningRiskModel.value = true
  try {
    active.value = await runFallRiskModel(active.value.assessment_id)
    error.value = null
  } catch {
    error.value = 'MotionCLIP 无法分析当前 GVHMR 结果'
  } finally {
    runningRiskModel.value = false
  }
}

onMounted(() => {
  void load()
  poll = setInterval(load, 2_000)
})

onBeforeUnmount(() => {
  if (poll) clearInterval(poll)
})
</script>

<template>
  <div>
    <PageHeader
      eyebrow="GAIT FEATURE ASSESSMENT"
      title="跌倒风险评估"
      description="从真实 H6c 步态片段提取 3D 人体运动和步态参数，并由 CARE-PD MotionCLIP 输出连续健康参考偏离度与可解释步态概念。"
    />

    <p v-if="error" class="risk-error">{{ error }}</p>

    <section class="risk-layout">
      <article class="panel-card capture-panel">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">ASSESSMENT SESSION</span><h2>步态采集任务</h2></div>
          <el-tag :type="worker?.ready ? 'success' : 'warning'" effect="plain">
            {{ worker?.ready ? 'Worker Ready' : 'Setup Required' }}
          </el-tag>
        </div>

        <div class="capture-form">
          <label>受试者身高（cm）<el-input-number v-model="heightCm" :min="80" :max="230" /></label>
          <label>采集时长（秒）<el-input-number v-model="durationSeconds" :min="8" :max="60" /></label>
          <el-button
            type="primary"
            :disabled="!worker?.ready || isRunning"
            :loading="submitting"
            @click="startAssessment"
          >开始真实评估</el-button>
        </div>

        <ul class="capture-guidance">
          <li>固定摄像机，确保全身和双脚持续可见。</li>
          <li>沿相机光轴自然直线行走，建议至少包含 6 个完整步骤。</li>
          <li>空间与稳定性参数是单目研究估计量，不作为临床诊断。</li>
        </ul>

        <div v-if="worker && !worker.ready" class="missing-box">
          <strong>运行环境尚未完成</strong>
          <span v-for="item in worker.missing_requirements" :key="item">{{ item }}</span>
        </div>

        <div v-if="active" class="job-progress">
          <div><strong>{{ active.stage }}</strong><span>{{ Math.round(active.progress * 100) }}%</span></div>
          <el-progress :percentage="Math.round(active.progress * 100)" :stroke-width="8" />
          <div class="capture-clock">
            <span>触发 {{ formatTime(active.created_at) }}</span>
            <span v-if="captureRemaining !== null">采集窗口剩余 {{ captureRemaining }} 秒</span>
            <span v-else>采集耗时 {{ elapsedSeconds(active.capture_started_at, active.capture_completed_at) }}</span>
            <span v-if="active.processing_started_at">
              处理耗时 {{ elapsedSeconds(active.processing_started_at, active.completed_at) }}
            </span>
          </div>
          <dl>
            <div><dt>VisionMD-Gait</dt><dd>{{ active.gait_pipeline.status }}</dd></div>
            <div><dt>GVHMR / SMPL-X</dt><dd>{{ active.gvhmr_pipeline.status }}</dd></div>
            <div><dt>MotionCLIP</dt><dd>{{ active.risk_pipeline.status }}</dd></div>
            <div><dt>质量检查</dt><dd>{{ poseQualityUsable ? 'Usable' : 'Insufficient / Review' }}</dd></div>
          </dl>
          <p v-if="active.error" class="job-error">{{ active.error }}</p>
          <div v-if="active.quality.source_fps !== null" class="quality-summary">
            <strong>采集质量</strong>
            <span>有效姿态 {{ formatPercent(active.quality.pose_valid_ratio) }}</span>
            <span>全身可见 {{ formatPercent(active.quality.full_body_visible_ratio) }}</span>
            <span>插值帧 {{ formatPercent(active.quality.interpolated_frame_ratio) }}</span>
            <span>完整步数 {{ active.quality.complete_step_count }}</span>
            <small v-for="reason in active.quality.reasons" :key="reason">{{ reason }}</small>
          </div>
        </div>
      </article>

      <article class="panel-card video-panel">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">PROCESSED VIDEO</span><h2>骨骼与 SMPL-X</h2></div>
        </div>
        <div class="artifact-grid">
          <section class="artifact-slot">
            <div class="artifact-slot__header">
              <div><span>POSE & GAIT EVENTS</span><strong>MeTRAbs 骨骼点视频</strong></div>
              <el-tag effect="plain" :type="gaitArtifact && poseQualityUsable ? 'success' : 'info'">
                {{ gaitArtifact && poseQualityUsable ? 'Available' : 'Unavailable' }}
              </el-tag>
            </div>
            <video
              v-if="gaitArtifact && poseQualityUsable"
              controls
              playsinline
              preload="metadata"
              :src="fallRiskArtifactUrl(active?.assessment_id ?? '', gaitArtifact.artifact_id)"
            />
            <EmptyState
              v-else
              title="暂无有效骨骼视频"
              description="采集视频通过媒体与姿态质量检查后显示；损坏或插值占比过高的视频不会展示。"
              :icon="VideoCamera"
            />
          </section>

          <section class="artifact-slot">
            <div class="artifact-slot__header">
              <div>
                <span>{{ smplView === 'privacy' ? 'GVHMR GLOBAL' : 'GVHMR INCAMERA' }}</span>
                <strong>{{ smplView === 'privacy' ? 'SMPL-X 隐私替身视频' : 'SMPL-X 相机叠加视频' }}</strong>
              </div>
              <el-tag effect="plain" :type="smplArtifact && poseQualityUsable ? 'success' : 'info'">
                {{ smplArtifact && poseQualityUsable ? 'Available' : 'Unavailable' }}
              </el-tag>
            </div>
            <div class="smpl-view-switch" role="group" aria-label="SMPL-X 展示模式">
              <button
                type="button"
                :class="{ active: smplView === 'privacy' }"
                @click="smplView = 'privacy'"
              >隐私替身</button>
              <button
                type="button"
                :class="{ active: smplView === 'overlay' }"
                @click="smplView = 'overlay'"
              >相机叠加</button>
            </div>
            <video
              v-if="smplArtifact && poseQualityUsable"
              controls
              playsinline
              preload="metadata"
              :src="fallRiskArtifactUrl(active?.assessment_id ?? '', smplArtifact.artifact_id)"
            />
            <EmptyState
              v-else
              title="暂无有效 SMPL-X 视频"
              description="GVHMR 成功且输入姿态质量达标后显示人体网格；隐私替身模式不包含原始 RGB 画面。"
              :icon="VideoCamera"
            />
          </section>
        </div>
      </article>
    </section>

    <section class="panel-card parameter-panel">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">GAIT PARAMETERS</span><h2>28 项步态参数</h2></div>
        <el-tag effect="plain">Research Estimates</el-tag>
      </div>
      <div v-if="active?.gait_parameters.length && poseQualityUsable" class="parameter-groups">
        <section v-for="([key, title]) in categories" :key="key">
          <h3>{{ title }}</h3>
          <dl>
            <div v-for="parameter in parameters(key)" :key="parameter.name">
              <dt>{{ parameter.display_name }}</dt>
              <dd :title="parameter.unavailable_reason ?? ''">{{ formatParameter(parameter) }}</dd>
            </div>
          </dl>
        </section>
      </div>
      <EmptyState
        v-else
        title="暂无真实步态参数"
        description="完成一次媒体完整、人体姿态可用的真实采集后显示；低质量任务不展示不可信参数。"
        :icon="DataAnalysis"
      />
    </section>

    <section class="panel-card final-risk">
      <div>
        <span class="panel-card__kicker">EXPLAINABLE FALL-RISK MODEL</span>
        <h2>MotionCLIP 核心模型</h2>
      </div>
      <el-tag
        :type="active?.risk_model_status === 'completed' ? 'success' : active?.risk_model_status === 'failed' ? 'danger' : 'info'"
        effect="plain"
      >{{ active?.risk_model_status ?? 'not_configured' }}</el-tag>

      <el-button
        v-if="active?.gvhmr_pipeline.status === 'completed' && !active.risk_result"
        class="risk-run-button"
        type="primary"
        plain
        :loading="runningRiskModel"
        :disabled="worker?.risk_pipeline.status !== 'ready'"
        @click="analyzeExistingGvhmr"
      >分析现有 SMPL-X 结果</el-button>

      <template v-if="active?.risk_result">
        <div class="risk-summary">
          <section>
            <span>健康参考偏离度</span>
            <strong>{{ active.risk_result.healthy_distance.toFixed(6) }}</strong>
            <small>1 − cosine distance；数值不是跌倒概率</small>
          </section>
          <section>
            <span>临床风险等级</span>
            <strong>未标定</strong>
            <small>当前 checkpoint 未经过独立临床阈值校准</small>
          </section>
          <section>
            <span>有效窗口</span>
            <strong>{{ active.risk_result.metadata.window_count ?? '--' }}</strong>
            <small>每窗 2 秒 / 30 FPS</small>
          </section>
        </div>

        <div class="concept-grid">
          <section v-for="([name, concept]) in conceptEntries" :key="name">
            <div><strong>{{ conceptLabels[name] ?? name }}</strong><span>{{ levelLabels[concept.predicted_level] }}</span></div>
            <el-progress
              :percentage="Math.round(concept.top1_probability * 100)"
              :stroke-width="7"
              :show-text="false"
            />
            <small>模型置信度 {{ Math.round(concept.top1_probability * 100) }}% · 区分度 {{ concept.margin.toFixed(3) }}</small>
          </section>
        </div>

        <div class="model-explanation">
          <strong>模型解释</strong>
          <p>{{ active.risk_result.explanation }}</p>
          <small>
            {{ active.risk_result.model.display_name }} · epoch {{ active.risk_result.model.checkpoint_epoch }} ·
            训练范围 {{ active.risk_result.model.training_scope }}
          </small>
        </div>
      </template>
      <EmptyState
        v-else
        title="暂无核心模型结果"
        description="完成姿态质量合格的真实采集及 GVHMR 处理后，独立 MotionCLIP Worker 才会生成研究结果。"
        :icon="DataAnalysis"
      />
      <p class="research-notice">仅供科研探索，不构成临床诊断、医疗建议或独立跌倒风险结论。</p>
    </section>
  </div>
</template>

<style scoped>
.risk-error { padding: 12px 16px; border: 1px solid #e9b7b7; border-radius: 10px; color: #a82d2d; background: #fff5f5; }
.risk-layout { display: grid; grid-template-columns: minmax(460px, .9fr) minmax(500px, 1.1fr); gap: 20px; margin-bottom: 20px; }
.capture-form { display: grid; grid-template-columns: 1fr 1fr auto; align-items: end; gap: 14px; margin-top: 20px; }
.capture-form label { display: grid; gap: 8px; color: var(--color-text-secondary); font-size: 12px; }
.capture-guidance { margin: 20px 0; padding-left: 20px; color: var(--color-text-secondary); line-height: 1.9; }
.missing-box { display: grid; gap: 6px; padding: 14px; border-radius: 10px; color: #8a621d; background: #fff8e8; }
.missing-box span { font-size: 12px; }
.job-progress { margin-top: 18px; }
.job-progress > div { display: flex; justify-content: space-between; margin-bottom: 10px; }
.job-progress dl { margin: 16px 0 0; }
.job-progress dl div { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--color-border-light); }
.job-progress dd { margin: 0; font-weight: 650; }
.capture-clock { display: flex !important; flex-wrap: wrap; justify-content: flex-start !important; gap: 8px; margin: 12px 0 0 !important; }
.capture-clock span { padding: 5px 9px; border-radius: 6px; color: var(--color-text-secondary); background: #f2f6f4; font-size: 12px; }
.job-error { margin: 14px 0 0; padding: 10px 12px; border-radius: 8px; color: #a82d2d; background: #fff1f1; }
.quality-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 14px; padding: 12px; border-radius: 8px; background: #f4f8f6; }
.quality-summary strong, .quality-summary small { grid-column: 1 / -1; }
.quality-summary span, .quality-summary small { color: var(--color-text-secondary); font-size: 12px; }
.quality-summary small { color: #8a621d; }
.artifact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 20px; }
.artifact-slot { min-width: 0; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 10px; background: #f8faf9; }
.artifact-slot__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; min-height: 46px; }
.artifact-slot__header div { display: grid; gap: 4px; }
.artifact-slot__header span { color: var(--color-text-secondary); font-size: 10px; font-weight: 700; letter-spacing: .12em; }
.artifact-slot__header strong { color: var(--color-heading); font-size: 14px; }
.artifact-slot video { display: block; width: 100%; aspect-ratio: 16 / 9; margin-top: 12px; border-radius: 8px; background: #0d1210; object-fit: contain; }
.smpl-view-switch { display: flex; gap: 6px; margin-top: 10px; }
.smpl-view-switch button { padding: 5px 10px; border: 1px solid var(--color-border-light); border-radius: 6px; color: var(--color-text-secondary); background: #fff; cursor: pointer; font: inherit; font-size: 12px; }
.smpl-view-switch button.active { border-color: #2a8169; color: #17634f; background: #eaf5f1; }
.artifact-slot :deep(.empty-state) { min-height: 210px; margin-top: 12px; padding: 20px 14px; background: #fff; }
.parameter-panel { margin-bottom: 20px; }
.parameter-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 20px; }
.parameter-groups section { padding: 16px; border: 1px solid var(--color-border-light); border-radius: 10px; background: #f8faf9; }
.parameter-groups h3 { margin: 0 0 10px; color: var(--color-heading); font-size: 15px; }
.parameter-groups dl { margin: 0; }
.parameter-groups dl div { display: flex; justify-content: space-between; gap: 15px; padding: 8px 0; border-bottom: 1px solid var(--color-border-light); }
.parameter-groups dl div:last-child { border: 0; }
.parameter-groups dt { color: var(--color-text-secondary); }
.parameter-groups dd { margin: 0; color: var(--color-heading); font-weight: 650; }
.final-risk { display: grid; grid-template-columns: 1fr auto; align-items: start; gap: 16px; }
.risk-run-button, .risk-summary, .concept-grid, .model-explanation, .final-risk :deep(.empty-state), .research-notice { grid-column: 1 / -1; justify-self: start; }
.risk-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.risk-summary section { display: grid; gap: 6px; padding: 16px; border: 1px solid var(--color-border-light); border-radius: 10px; background: #f8faf9; }
.risk-summary span, .risk-summary small { color: var(--color-text-secondary); }
.risk-summary strong { color: var(--color-heading); font-size: 24px; }
.concept-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.concept-grid section { display: grid; gap: 9px; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 10px; }
.concept-grid section > div { display: flex; justify-content: space-between; gap: 8px; }
.concept-grid span { color: #216c58; font-weight: 650; }
.concept-grid small, .model-explanation small { color: var(--color-text-secondary); }
.model-explanation { padding: 16px; border-left: 3px solid #2a8169; background: #f4f8f6; }
.model-explanation p { margin: 10px 0; color: var(--color-text-secondary); white-space: pre-line; line-height: 1.7; }
.research-notice { margin: 0; color: #8a621d; font-size: 12px; }
@media (max-width: 1360px) { .risk-layout { grid-template-columns: 1fr; } .capture-form { grid-template-columns: 1fr 1fr; } }
@media (max-width: 1100px) { .concept-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 900px) { .artifact-grid, .risk-summary { grid-template-columns: 1fr; } }
</style>
