import { describe, expect, it } from 'vitest'

import { parseRealtimeMessage } from './types'

describe('parseRealtimeMessage', () => {
  it('parses an explicitly simulated pipeline result', () => {
    const message = parseRealtimeMessage(
      JSON.stringify({
        type: 'algorithm_result',
        timestamp: '2026-08-16T12:00:00Z',
        data: {
          result_id: '1e043426-c106-4ef9-a589-5f58654eb981',
          task: 'pipeline_test',
          model_id: 'pipeline-tester',
          model_version: '1.0',
          device_id: null,
          source_timestamp: null,
          result_timestamp: '2026-08-16T12:00:00Z',
          label: 'pipeline_ok',
          score: null,
          level: null,
          latency_ms: null,
          metadata: {},
          simulated: true,
        },
      }),
    )

    expect(message?.type).toBe('algorithm_result')
    expect(message?.type === 'algorithm_result' ? message.data.simulated : null).toBe(true)
  })

  it('rejects malformed or unsupported messages', () => {
    expect(parseRealtimeMessage('not json')).toBeNull()
    expect(parseRealtimeMessage('{"type":"fall_event"}')).toBeNull()
  })

  it('parses a real fall result and a running worker heartbeat', () => {
    const fall = parseRealtimeMessage(
      JSON.stringify({
        type: 'algorithm_result',
        timestamp: '2026-08-17T12:00:00Z',
        data: {
          result_id: '1e043426-c106-4ef9-a589-5f58654eb982',
          task: 'fall_detection',
          model_id: 'pose-fall-baseline',
          model_version: 'm5-v1',
          device_id: 'ezviz_safe_id',
          source_timestamp: '2026-08-17T12:00:00Z',
          result_timestamp: '2026-08-17T12:00:00Z',
          label: 'normal',
          score: 0.1,
          level: 'normal',
          latency_ms: 12,
          metadata: { score_type: 'heuristic' },
          simulated: false,
        },
      }),
    )
    const worker = parseRealtimeMessage(
      JSON.stringify({
        type: 'worker_status',
        timestamp: '2026-08-17T12:00:00Z',
        data: {
          worker_id: 'worker-1',
          online: true,
          timestamp: '2026-08-17T12:00:00Z',
          version: '0.5.0',
          capabilities: {
            fall_detection: 'running',
            fall_risk: 'not_installed',
            fraud_detection: 'not_installed',
          },
          runtime: { fall_detection: { device: 'cuda:0' } },
        },
      }),
    )

    expect(fall?.type).toBe('algorithm_result')
    expect(worker?.type).toBe('worker_status')
  })
})
