<script setup lang="ts">
import { DataAnalysis, VideoCamera } from '@element-plus/icons-vue'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import {
  createFallRiskAssessment,
  createFallRiskVideoAssessment,
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
const subjectName = ref('')
const subjectSex = ref<'male' | 'female'>('male')
const subjectAge = ref(70)
const heightCm = ref(170)
const durationSeconds = ref(15)
const loading = ref(true)
const submitting = ref(false)
const uploading = ref(false)
const selectedVideo = ref<File | null>(null)
const uploadedDurationSeconds = ref<number | null>(null)
const runningRiskModel = ref(false)
const historyPage = ref(1)
const showAllParameters = ref(false)
const error = ref<string | null>(null)
// The primary assessment view keeps the captured scene and replaces the
// person's covered pixels with the camera-aligned SMPL-X mesh. The global
// view remains available as a research diagnostic without becoming the
// default presentation.
const smplView = ref<'overlay' | 'world'>('overlay')
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
const subjectReady = computed(() => subjectName.value.trim().length > 0)

const primaryParameterNames = [
  'cadence_spm',
  'step_time_s',
  'step_length_m',
  'gait_speed_m_s',
  'step_width_m',
  'trunk_lean_deg',
  'xcom_lateral_rms_m',
  'emos_min_m',
]
const primaryParameters = computed(() => {
  const byName = new Map((active.value?.gait_parameters ?? []).map((item) => [item.name, item]))
  return primaryParameterNames.flatMap((name) => {
    const parameter = byName.get(name)
    return parameter ? [parameter] : []
  })
})

const historyPageSize = 5
const historyPageCount = computed(() => Math.max(1, Math.ceil(assessments.value.length / historyPageSize)))
const paginatedAssessments = computed(() => {
  const start = (historyPage.value - 1) * historyPageSize
  return assessments.value.slice(start, start + historyPageSize)
})

const riskLevel = computed(() => active.value?.risk_result?.risk_level ?? null)
const riskLevelLabel = computed(() => {
  const level = riskLevel.value
  return level ? { low: '低风险', medium: '中风险', high: '高风险' }[level] : '待评估'
})
const riskLevelTone = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  const level = riskLevel.value
  return level ? { low: 'success' as const, medium: 'warning' as const, high: 'danger' as const }[level] : 'info'
})

const isRunning = computed(() =>
  active.value
    ? !['quality_review', 'completed', 'partial', 'failed', 'cancelled'].includes(active.value.status)
    : false,
)

const poseQualityUsable = computed(() => {
  const quality = active.value?.quality
  const missingGapSeconds = quality?.maximum_missing_gap_seconds
    ?? (
      quality?.maximum_missing_gap_frames !== null
      && quality?.maximum_missing_gap_frames !== undefined
      && quality?.source_fps
        ? quality.maximum_missing_gap_frames / quality.source_fps
        : null
    )
  return Boolean(
    quality
      && quality.pose_valid_ratio !== null
      && quality.pose_valid_ratio >= 0.8
      && quality.full_body_visible_ratio !== null
      && quality.full_body_visible_ratio >= 0.8
      && quality.interpolated_frame_ratio !== null
      && quality.interpolated_frame_ratio <= 0.2
      && missingGapSeconds !== null
      && missingGapSeconds <= 1,
  )
})

const sourceArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'source_video' && item.available) ?? null,
)

const smplIncameraArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'gvhmr_incamera' && item.available) ?? null,
)

const smplGlobalArtifact = computed(() =>
  active.value?.artifacts.find((item) => item.kind === 'gvhmr_global' && item.available) ?? null,
)

const smplArtifact = computed(() => (
  smplView.value === 'overlay' ? smplIncameraArtifact.value : smplGlobalArtifact.value
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

const progressStage = computed(() => {
  const status = active.value?.status
  if (!status) return '等待开始评估'
  return {
    queued: '正在准备评估',
    capturing: active.value?.input_source === 'uploaded_video' ? '正在导入视频' : '正在采集视频',
    processing_gait: '正在分析行走特征',
    processing_gvhmr: '正在生成人体运动分析视频',
    processing_risk: '正在计算风险评估结果',
    quality_review: '采集质量需要复核',
    completed: '评估完成',
    partial: '部分评估结果已生成',
    failed: '评估失败',
    cancelled: '评估已取消',
  }[status] ?? '正在处理评估'
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

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(value))
}

function inputSourceLabel(assessment: FallRiskAssessment): string {
  return assessment.input_source === 'uploaded_video' ? '上传视频' : '摄像机采集'
}

function subjectSexLabel(value: FallRiskAssessment['sex']): string {
  return value === 'male' ? '男' : value === 'female' ? '女' : '未填写'
}

function assessmentStatusLabel(value: string): string {
  return {
    queued: '等待中', capturing: '采集中', processing_gait: '分析中',
    processing_gvhmr: '分析中', processing_risk: '生成结果中', quality_review: '需要复核',
    completed: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消',
  }[value] ?? value
}

function assessmentRiskLabel(value: FallRiskAssessment['risk_result']): string {
  if (!value?.risk_level) return '暂无风险等级'
  return `${{ low: '低', medium: '中', high: '高' }[value.risk_level]}风险`
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
  if (!subjectReady.value) {
    error.value = '请填写受试者姓名'
    return
  }
  submitting.value = true
  try {
    active.value = await createFallRiskAssessment(
      subjectName.value.trim(), subjectSex.value, subjectAge.value,
      heightCm.value, durationSeconds.value,
    )
    error.value = null
  } catch {
    error.value = '评估无法启动，请检查 Worker、模型资产和摄像机状态'
  } finally {
    submitting.value = false
  }
}

function inspectVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video')
    const objectUrl = URL.createObjectURL(file)
    const cleanup = () => URL.revokeObjectURL(objectUrl)
    video.preload = 'metadata'
    video.onloadedmetadata = () => {
      const duration = video.duration
      cleanup()
      if (!Number.isFinite(duration)) reject(new Error('invalid duration'))
      else resolve(duration)
    }
    video.onerror = () => {
      cleanup()
      reject(new Error('invalid video'))
    }
    video.src = objectUrl
  })
}

async function selectVideo(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  selectedVideo.value = null
  uploadedDurationSeconds.value = null
  if (!file) return
  if (file.type !== 'video/mp4' && !file.name.toLowerCase().endsWith('.mp4')) {
    error.value = '仅支持 MP4 视频文件'
    input.value = ''
    return
  }
  if (file.size > 512 * 1024 * 1024) {
    error.value = '视频文件不能超过 512 MB'
    input.value = ''
    return
  }
  try {
    const duration = await inspectVideoDuration(file)
    const rounded = Math.ceil(duration)
    if (rounded < 8 || rounded > 60) {
      throw new Error('duration out of range')
    }
    selectedVideo.value = file
    uploadedDurationSeconds.value = rounded
    error.value = null
  } catch {
    error.value = '请选择时长为 8–60 秒且可正常解码的 MP4 视频'
    input.value = ''
  }
}

async function uploadAssessment(): Promise<void> {
  if (!selectedVideo.value || uploadedDurationSeconds.value === null) return
  if (!subjectReady.value) {
    error.value = '请填写受试者姓名'
    return
  }
  uploading.value = true
  try {
    active.value = await createFallRiskVideoAssessment(
      selectedVideo.value,
      subjectName.value.trim(),
      subjectSex.value,
      subjectAge.value,
      heightCm.value,
      uploadedDurationSeconds.value,
    )
    error.value = null
  } catch {
    error.value = '视频评估无法启动，请检查文件、Worker 状态或是否已有任务运行'
  } finally {
    uploading.value = false
  }
}

async function selectAssessment(assessment: FallRiskAssessment): Promise<void> {
  active.value = assessment
  error.value = null
  window.scrollTo({ top: 0, behavior: 'smooth' })
  try {
    // The list is a summary snapshot. Reload the selected task so its media
    // artifacts and completion state always belong to the selected record.
    active.value = await fetchFallRiskAssessment(assessment.assessment_id)
  } catch {
    error.value = '无法加载该评估记录的完整结果'
  }
}

async function analyzeExistingGvhmr(): Promise<void> {
  if (!active.value) return
  runningRiskModel.value = true
  try {
    active.value = await runFallRiskModel(active.value.assessment_id)
    error.value = null
  } catch {
    error.value = '当前人体运动数据暂时无法生成风险评估结果'
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
      description="通过摄像机采集或导入视频，分析三维人体运动与核心步态参数，并生成跌倒风险等级和评估说明。"
    />

    <p v-if="error" class="risk-error">{{ error }}</p>

    <section class="risk-layout">
      <article class="panel-card capture-panel">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">ASSESSMENT SESSION</span><h2>新建步态评估</h2></div>
          <el-tag :type="worker?.ready ? 'success' : 'warning'" effect="plain">
            {{ worker?.ready ? '评估服务正常' : '评估服务未就绪' }}
          </el-tag>
        </div>

        <div class="subject-form">
          <label class="subject-field subject-field--name">
            <span>姓名</span>
            <el-input v-model="subjectName" maxlength="80" placeholder="请输入姓名" />
          </label>
          <div class="subject-field subject-field--sex">
            <span>性别</span>
            <el-radio-group v-model="subjectSex" aria-label="性别">
              <el-radio value="male">男</el-radio>
              <el-radio value="female">女</el-radio>
            </el-radio-group>
          </div>
          <label class="subject-field subject-field--number">
            <span>年龄（岁）</span>
            <el-input-number v-model="subjectAge" :min="1" :max="120" :controls="false" />
          </label>
          <label class="subject-field subject-field--number">
            <span>身高（cm）</span>
            <el-input-number v-model="heightCm" :min="80" :max="230" :controls="false" />
          </label>
        </div>

        <div class="input-options">
          <section>
            <div><strong>摄像机采集</strong></div>
            <label>采集时长（秒）<el-input-number v-model="durationSeconds" :min="8" :max="60" /></label>
            <el-button
              type="primary"
              :disabled="!worker?.ready || isRunning || !subjectReady"
              :loading="submitting"
              @click="startAssessment"
            >开始摄像机评估</el-button>
          </section>
          <section>
            <div>
              <strong>导入视频</strong>
              <span v-if="uploading">上传视频 · 上传中</span>
              <span v-else-if="active?.input_source === 'uploaded_video'">上传视频 · 100%</span>
            </div>
            <label class="file-picker">
              <span>{{ selectedVideo?.name ?? '选择 8–60 秒 MP4' }}</span>
              <input type="file" accept="video/mp4,.mp4" @change="selectVideo">
            </label>
            <el-button
              type="primary"
              plain
              :disabled="!worker?.ready || isRunning || !selectedVideo || !subjectReady"
              :loading="uploading"
              @click="uploadAssessment"
            >导入并开始评估</el-button>
            <small v-if="selectedVideo && !uploading">
              {{ (selectedVideo.size / 1024 / 1024).toFixed(1) }} MB · {{ uploadedDurationSeconds }} 秒
            </small>
          </section>
        </div>

        <div class="capture-guidance">
          <strong>评估采集注意事项</strong>
          <ul>
            <li>固定摄像机，确保全身和双脚持续可见。</li>
            <li>沿相机光轴自然直线行走，建议至少包含 6 个完整步骤。</li>
          </ul>
        </div>

        <div v-if="worker && !worker.ready" class="missing-box">
          <strong>运行环境尚未完成</strong>
          <span v-for="item in worker.missing_requirements" :key="item">{{ item }}</span>
        </div>

        <div v-if="active" class="job-progress">
          <div>
            <strong>{{ progressStage }}</strong>
            <span>整体进度 · {{ Math.round(active.progress * 100) }}%</span>
          </div>
          <el-progress
            class="assessment-progress"
            :percentage="Math.round(active.progress * 100)"
            :stroke-width="10"
            :show-text="false"
            :status="active.status === 'failed' ? 'exception' : active.status === 'completed' ? 'success' : undefined"
          />
          <div class="capture-clock">
            <span>触发 {{ formatTime(active.created_at) }}</span>
            <span v-if="captureRemaining !== null">采集窗口剩余 {{ captureRemaining }} 秒</span>
            <span v-else>采集耗时 {{ elapsedSeconds(active.capture_started_at, active.capture_completed_at) }}</span>
            <span v-if="active.processing_started_at">
              处理耗时 {{ elapsedSeconds(active.processing_started_at, active.completed_at) }}
            </span>
            <span v-if="active.started_at">
              总耗时 {{ elapsedSeconds(active.started_at, active.completed_at) }}
            </span>
          </div>
          <p v-if="active.error" class="job-error">{{ active.error }}</p>
          <div v-if="active.quality.source_fps !== null" class="quality-summary">
            <strong>采集质量</strong>
            <span>有效姿态 {{ formatPercent(active.quality.pose_valid_ratio) }}</span>
            <span>全身可见 {{ formatPercent(active.quality.full_body_visible_ratio) }}</span>
            <span>插值帧 {{ formatPercent(active.quality.interpolated_frame_ratio) }}</span>
            <span>完整步数 {{ active.quality.complete_step_count }}</span>
            <span v-if="active.quality.video_duration_seconds !== null">
              分析片段 {{ active.quality.video_duration_seconds.toFixed(1) }} 秒
            </span>
            <span v-if="active.quality.discarded_duration_seconds !== null">
              剔除无人片段 {{ active.quality.discarded_duration_seconds.toFixed(1) }} 秒
            </span>
            <span v-if="active.quality.maximum_missing_gap_seconds !== null">
              最大连续缺失 {{ active.quality.maximum_missing_gap_seconds.toFixed(2) }} 秒
            </span>
            <small v-for="reason in active.quality.reasons" :key="reason">{{ reason }}</small>
          </div>
        </div>
      </article>

      <article class="panel-card video-panel">
        <div class="panel-card__header">
          <div><span class="panel-card__kicker">ASSESSMENT VIDEO</span><h2>步态评估视频对比</h2></div>
        </div>
        <div class="artifact-grid">
          <section class="artifact-slot artifact-slot--source">
            <div class="artifact-slot__header">
              <div>
                <span>INPUT VIDEO</span>
                <strong>{{ active?.input_source === 'uploaded_video' ? '导入的原始视频' : '摄像机采集原始视频' }}</strong>
                <small>{{ active?.source_filename ?? '本次评估录制视频' }}</small>
              </div>
            </div>
            <video
              v-if="sourceArtifact"
              :key="`${active?.assessment_id}:${sourceArtifact.artifact_id}`"
              controls
              playsinline
              preload="metadata"
              :src="fallRiskArtifactUrl(active?.assessment_id ?? '', sourceArtifact.artifact_id)"
            />
            <EmptyState
              v-else
              title="暂无原始评估视频"
              description="视频成功采集或上传并通过媒体完整性检查后显示。"
              :icon="VideoCamera"
            />
          </section>
          <section class="artifact-slot artifact-slot--analysis">
            <div class="artifact-slot__header">
              <div>
                <span>MOTION ANALYSIS</span>
                <div class="artifact-title-row">
                  <strong>人体网格分析视频</strong>
                  <div class="smpl-view-switch" role="group" aria-label="SMPL-X 展示模式">
                    <button
                      type="button"
                      :class="{ active: smplView === 'overlay' }"
                      @click="smplView = 'overlay'"
                    >场景融合视图</button>
                    <button
                      type="button"
                      :class="{ active: smplView === 'world' }"
                      @click="smplView = 'world'"
                    >三维动作视图</button>
                  </div>
                </div>
                <small>{{ smplView === 'overlay' ? '原景人体网格可视化' : '世界坐标三维动作可视化' }}</small>
              </div>
            </div>
            <video
              v-if="smplArtifact && poseQualityUsable"
              :key="`${active?.assessment_id}:${smplArtifact.artifact_id}`"
              controls
              playsinline
              preload="metadata"
              :src="fallRiskArtifactUrl(active?.assessment_id ?? '', smplArtifact.artifact_id)"
            />
            <EmptyState
              v-else
              title="暂无有效 SMPL-X 视频"
              description="GVHMR 成功且输入姿态质量达标后，默认显示保留原始场景背景、以人体网格覆盖人物区域的相机视角视频。"
              :icon="VideoCamera"
            />
          </section>
        </div>
      </article>
    </section>

    <section class="panel-card history-panel">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">ASSESSMENT HISTORY</span><h2>评估记录</h2></div>
        <el-tag effect="plain">共 {{ assessments.length }} 条</el-tag>
      </div>
      <div v-if="assessments.length" class="history-list">
        <button
          v-for="assessment in paginatedAssessments"
          :key="assessment.assessment_id"
          type="button"
          :class="{ active: active?.assessment_id === assessment.assessment_id }"
          @click="selectAssessment(assessment)"
        >
          <span><strong>{{ formatDateTime(assessment.created_at) }}</strong><small>{{ inputSourceLabel(assessment) }}</small></span>
          <span><strong>{{ assessment.subject_name ?? '未填写姓名' }}</strong><small>{{ subjectSexLabel(assessment.sex) }} · {{ assessment.age ?? '--' }} 岁 · {{ assessment.height_cm }} cm</small></span>
          <span><strong>{{ assessment.source_filename ?? '摄像机采集' }}</strong><small>{{ assessment.capture_duration_seconds }} 秒</small></span>
          <span><strong>{{ assessmentStatusLabel(assessment.status) }}</strong><small>{{ assessmentRiskLabel(assessment.risk_result) }}</small></span>
        </button>
        <div class="history-pagination-row">
          <span>第 {{ historyPage }} / {{ historyPageCount }} 页</span>
          <el-pagination
            v-model:current-page="historyPage"
            class="history-pagination"
            background
            layout="prev, pager, next, jumper"
            :page-size="historyPageSize"
            :pager-count="5"
            :total="assessments.length"
          />
        </div>
      </div>
      <EmptyState
        v-else
        title="暂无评估记录"
        description="完成摄像机采集或上传一次真实步态视频后显示。"
        :icon="DataAnalysis"
      />
    </section>

    <section class="panel-card parameter-panel">
      <div class="panel-card__header">
        <div><span class="panel-card__kicker">GAIT PARAMETERS</span><h2>8 项核心步态参数</h2></div>
        <el-button v-if="active?.gait_parameters.length" plain @click="showAllParameters = !showAllParameters">
          {{ showAllParameters ? '收起全部信息' : '查看全部信息' }}
        </el-button>
      </div>
      <div v-if="primaryParameters.length" class="primary-parameter-grid">
        <section v-for="parameter in primaryParameters" :key="parameter.name">
          <span>{{ parameter.display_name }}</span>
          <strong :title="parameter.unavailable_reason ?? ''">{{ formatParameter(parameter) }}</strong>
        </section>
      </div>
      <div v-if="showAllParameters && active?.gait_parameters.length" class="parameter-groups">
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
        v-else-if="!primaryParameters.length"
        title="暂无真实步态参数"
        description="完成一次真实 VisionMD-Gait 处理后显示；不可计算的参数保持为空，不使用静态假值。"
        :icon="DataAnalysis"
      />
    </section>

    <section class="panel-card final-risk">
      <div>
        <span class="panel-card__kicker">FALL RISK RESULT</span>
        <h2>跌倒风险评估结果</h2>
      </div>
      <el-tag
        :type="active?.risk_result ? riskLevelTone : active?.risk_model_status === 'failed' ? 'danger' : 'info'"
        effect="plain"
      >{{ active?.risk_result ? riskLevelLabel : '等待评估' }}</el-tag>

      <el-button
        v-if="active?.gvhmr_pipeline.status === 'completed' && !active.risk_result"
        class="risk-run-button"
        type="primary"
        plain
        :loading="runningRiskModel"
        :disabled="worker?.risk_pipeline.status !== 'ready'"
        @click="analyzeExistingGvhmr"
      >生成风险评估结果</el-button>

      <template v-if="active?.risk_result">
        <div class="risk-summary">
          <section class="risk-level-card" :class="`risk-level-card--${riskLevel ?? 'pending'}`">
            <span>跌倒风险等级</span>
            <strong>{{ riskLevelLabel }}</strong>
            <small>依据健康参考偏离度的训练集分级结果</small>
          </section>
          <section>
            <span>健康参考偏离度</span>
            <strong>{{ active.risk_result.healthy_distance.toFixed(6) }}</strong>
            <small>连续偏离指标，不表示跌倒概率</small>
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
          <strong>评估说明</strong>
          <p>{{ active.risk_result.explanation }}</p>
        </div>
      </template>
      <EmptyState
        v-else
        title="暂无风险评估结果"
        description="完成符合采集要求的步态视频分析后生成评估结果。"
        :icon="DataAnalysis"
      />
      <p class="research-notice">评估结果可作为健康管理与医疗建议的辅助参考，最终结论需结合临床诊断及专业人员意见。</p>
    </section>
  </div>
</template>

<style scoped>
.risk-error { padding: 12px 16px; border: 1px solid var(--color-danger-border); border-radius: 10px; color: var(--color-danger-text); background: var(--color-danger-soft); }
.risk-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; margin-bottom: 20px; }
.subject-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); align-items: stretch; gap: 18px; margin-top: 20px; }
.subject-form label, .input-options label { display: grid; gap: 8px; color: var(--color-text-secondary); font-size: 12px; }
.subject-form .subject-field { display: flex; align-items: center; min-width: 0; min-height: 62px; gap: 10px; margin: 0; padding: 12px 14px; border: 1px solid var(--color-border-light); border-radius: 9px; color: var(--color-text-secondary); background: var(--color-surface-soft); font-size: 13px; white-space: nowrap; }
.subject-field > span { flex: 0 0 auto; color: var(--color-text-secondary); }
.subject-field :deep(.el-input__wrapper) { min-height: 36px; background: var(--color-control-bg); box-shadow: 0 0 0 1px var(--color-border) inset !important; }
.subject-field--name :deep(.el-input) { width: min(160px, 100%); }
.subject-field--sex :deep(.el-radio-group) { display: inline-flex !important; flex: 0 0 auto; flex-flow: row nowrap !important; align-items: center !important; min-height: 36px; gap: 14px; margin-left: 8px; padding: 0; border: 0; background: transparent; }
.subject-field--sex :deep(.el-radio) { display: inline-flex !important; flex-flow: row nowrap !important; align-items: center !important; gap: 5px; height: 36px; margin: 0 !important; color: var(--color-heading); }
.subject-field--sex :deep(.el-radio__input), .subject-field--sex :deep(.el-radio__label) { display: inline-flex !important; align-items: center !important; margin: 0; padding: 0; line-height: 1; }
.subject-field--number :deep(.el-input-number) { width: 96px; }
.subject-field--number :deep(.el-input__inner) { text-align: left; }
.input-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
.input-options section { display: grid; align-content: start; gap: 12px; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.input-options section > div { display: grid; gap: 4px; }
.input-options section > div span, .input-options small { color: var(--color-text-secondary); font-size: 11px; }
.file-picker { display: flex !important; align-items: center; min-width: 0; height: 30px; padding: 0 10px; overflow: hidden; border: 1px solid var(--color-border); border-radius: 6px; background: var(--color-control-bg); cursor: pointer; }
.file-picker span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-picker input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.capture-guidance { margin: 20px 0; padding: 13px 15px; border: 1px solid var(--color-primary-border); border-radius: 9px; color: var(--color-text-secondary); background: var(--color-info-soft); }
.capture-guidance > strong { color: var(--color-heading); font-size: 13px; }
.capture-guidance ul { margin: 7px 0 0; padding-left: 20px; line-height: 1.8; }
.missing-box { display: grid; gap: 6px; padding: 14px; border-radius: 10px; color: var(--color-warning-text); background: var(--color-warning-soft); }
.missing-box span { font-size: 12px; }
.job-progress { margin-top: 18px; }
.job-progress > div { display: flex; justify-content: space-between; margin-bottom: 10px; }
.assessment-progress { margin: 4px 0 12px; }
.assessment-progress :deep(.el-progress-bar__outer) { background: var(--color-neutral-soft); }
.capture-clock { display: flex !important; flex-wrap: wrap; justify-content: flex-start !important; gap: 8px; margin: 12px 0 0 !important; }
.capture-clock span { padding: 5px 9px; border-radius: 6px; color: var(--color-text-secondary); background: var(--color-neutral-soft); font-size: 12px; }
.job-error { margin: 14px 0 0; padding: 10px 12px; border-radius: 8px; color: var(--color-danger-text); background: var(--color-danger-soft); }
.quality-summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 14px; padding: 12px; border-radius: 8px; background: var(--color-surface-soft); }
.quality-summary strong, .quality-summary small { grid-column: 1 / -1; }
.quality-summary span, .quality-summary small { color: var(--color-text-secondary); font-size: 12px; }
.quality-summary small { color: var(--color-warning); }
.artifact-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 20px; }
.artifact-slot { display: grid; grid-template-rows: auto auto; align-content: start; min-width: 0; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.artifact-slot__header { display: flex; align-items: flex-start; gap: 10px; min-height: 62px; }
.artifact-slot__header div { display: grid; gap: 4px; }
.artifact-slot__header > div { width: 100%; }
.artifact-slot__header span { color: var(--color-text-secondary); font-size: 10px; font-weight: 700; letter-spacing: .12em; }
.artifact-slot__header strong { color: var(--color-heading); font-size: 14px; }
.artifact-slot__header small { overflow: hidden; max-width: 360px; color: var(--color-text-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-slot video { display: block; width: 100%; aspect-ratio: 16 / 9; margin-top: 8px; border-radius: 8px; background: #0d1210; object-fit: contain; }
.artifact-title-row { display: flex !important; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px !important; }
.smpl-view-switch { display: flex !important; width: auto !important; gap: 6px !important; }
.smpl-view-switch button { padding: 5px 10px; border: 1px solid var(--color-border); border-radius: 6px; color: var(--color-text-secondary); background: var(--color-control-bg); cursor: pointer; font: inherit; font-size: 12px; }
.smpl-view-switch button.active { border-color: var(--color-primary); color: var(--color-primary); background: var(--color-primary-soft); }
.artifact-slot :deep(.empty-state) { min-height: 210px; margin-top: 12px; padding: 20px 14px; background: var(--color-control-bg); }
.history-panel, .parameter-panel { margin-bottom: 20px; }
.history-list { display: grid; gap: 8px; margin-top: 18px; }
.history-list button { display: grid; grid-template-columns: .75fr 1.4fr 1.2fr .75fr; gap: 16px; width: 100%; padding: 12px 14px; border: 1px solid var(--color-border-light); border-radius: 9px; color: inherit; background: var(--color-surface-soft); cursor: pointer; text-align: left; }
.history-list button:hover, .history-list button.active { border-color: #8eb9e6; background: var(--color-primary-soft); }
.history-list span { display: grid; min-width: 0; gap: 3px; }
.history-list strong { overflow: hidden; color: var(--color-heading); text-overflow: ellipsis; white-space: nowrap; }
.history-list small { overflow: hidden; color: var(--color-text-secondary); text-overflow: ellipsis; white-space: nowrap; }
.history-pagination-row { display: flex; align-items: center; justify-content: space-between; min-height: 36px; margin-top: 10px; color: var(--color-text-secondary); font-size: 12px; }
.history-pagination { justify-content: flex-end; }
.history-pagination :deep(.btn-prev), .history-pagination :deep(.btn-next), .history-pagination :deep(.el-pager li) { border: 1px solid var(--color-border); background: var(--color-control-bg) !important; }
.history-pagination :deep(.el-pager li.is-active) { border-color: var(--color-primary); color: #fff; background: var(--color-primary) !important; }
.primary-parameter-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 20px; }
.primary-parameter-grid section { display: grid; gap: 8px; min-height: 82px; padding: 15px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.primary-parameter-grid span { color: var(--color-text-secondary); font-size: 12px; }
.primary-parameter-grid strong { color: var(--color-heading); font-size: 21px; }
.parameter-groups { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; margin-top: 20px; }
.parameter-groups section { padding: 16px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.parameter-groups h3 { margin: 0 0 10px; color: var(--color-heading); font-size: 15px; }
.parameter-groups dl { margin: 0; }
.parameter-groups dl div { display: flex; justify-content: space-between; gap: 15px; padding: 8px 0; border-bottom: 1px solid var(--color-border-light); }
.parameter-groups dl div:last-child { border: 0; }
.parameter-groups dt { color: var(--color-text-secondary); }
.parameter-groups dd { margin: 0; color: var(--color-heading); font-weight: 650; }
.final-risk { display: grid; grid-template-columns: 1fr auto; align-items: start; gap: 16px; }
.risk-run-button, .risk-summary, .concept-grid, .model-explanation, .final-risk :deep(.empty-state), .research-notice { grid-column: 1 / -1; }
.risk-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.risk-summary section { display: grid; gap: 6px; padding: 16px; border: 1px solid var(--color-border-light); border-radius: 10px; background: var(--color-surface-soft); }
.risk-summary span, .risk-summary small { color: var(--color-text-secondary); }
.risk-summary strong { color: var(--color-heading); font-size: 24px; }
.risk-level-card--low { border-color: color-mix(in srgb, var(--color-success) 36%, var(--color-border-light)) !important; background: var(--color-success-soft) !important; }
.risk-level-card--medium { border-color: var(--color-warning-border) !important; background: var(--color-warning-soft) !important; }
.risk-level-card--high { border-color: var(--color-danger-border) !important; background: var(--color-danger-soft) !important; }
.risk-level-card--low strong { color: var(--color-success); }
.risk-level-card--medium strong { color: var(--color-warning-text); }
.risk-level-card--high strong { color: var(--color-danger-text); }
.concept-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.concept-grid section { display: grid; gap: 9px; padding: 14px; border: 1px solid var(--color-border-light); border-radius: 10px; }
.concept-grid section > div { display: flex; justify-content: space-between; gap: 8px; }
.concept-grid span { color: var(--color-teal); font-weight: 650; }
.concept-grid small, .model-explanation small { color: var(--color-text-secondary); }
.model-explanation { width: 100%; padding: 18px 20px; border: 1px solid var(--color-primary-border); border-left: 3px solid var(--color-primary); border-radius: 9px; background: var(--color-primary-soft); }
.model-explanation p { margin: 12px 0 0; color: var(--color-text-secondary); white-space: pre-line; line-height: 1.85; }
.research-notice { margin: 0; color: var(--color-warning); font-size: 12px; }
@media (max-width: 1100px) { .concept-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 1150px) { .subject-form { gap: 12px; } .subject-form .subject-field { padding-inline: 11px; } .primary-parameter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 1050px) { .artifact-grid { grid-template-columns: 1fr; } }
@media (max-width: 900px) { .subject-form { grid-template-columns: repeat(2, minmax(0, 1fr)); } .risk-summary, .input-options { grid-template-columns: 1fr; } .history-list button { grid-template-columns: repeat(2, 1fr); } }
</style>
