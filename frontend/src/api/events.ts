import { requestJson } from './devices'
import type { AlgorithmResult } from '../realtime/types'

export function fetchRiskEvents(
  limit = 50,
  signal?: AbortSignal,
): Promise<AlgorithmResult[]> {
  return requestJson(`/api/events?limit=${limit}`, signal)
}
