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
})
