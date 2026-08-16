import { afterEach, describe, expect, it, vi } from 'vitest'

import { RealtimeClient, type RealtimeConnectionStatus } from './RealtimeClient'

class FakeSocket {
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null

  open() {
    this.readyState = 1
    this.onopen?.()
  }

  close() {
    this.readyState = 3
    this.onclose?.()
  }
}

afterEach(() => vi.useRealTimers())

describe('RealtimeClient', () => {
  it('connects once and disconnects without scheduling a reconnect', () => {
    vi.useFakeTimers()
    const sockets: FakeSocket[] = []
    const statuses: RealtimeConnectionStatus[] = []
    const client = new RealtimeClient({
      url: 'ws://test/ws/realtime',
      socketFactory: () => {
        const socket = new FakeSocket()
        sockets.push(socket)
        return socket as unknown as WebSocket
      },
    })
    client.onStatus((status) => statuses.push(status))

    client.connect()
    client.connect()
    sockets[0].open()
    client.disconnect()
    vi.runAllTimers()

    expect(sockets).toHaveLength(1)
    expect(statuses).toContain('connected')
    expect(statuses.at(-1)).toBe('disconnected')
  })

  it('reconnects with backoff after an unexpected close', () => {
    vi.useFakeTimers()
    const sockets: FakeSocket[] = []
    const statuses: RealtimeConnectionStatus[] = []
    const client = new RealtimeClient({
      url: 'ws://test/ws/realtime',
      reconnectBaseMs: 100,
      socketFactory: () => {
        const socket = new FakeSocket()
        sockets.push(socket)
        return socket as unknown as WebSocket
      },
    })
    client.onStatus((status) => statuses.push(status))

    client.connect()
    sockets[0].open()
    sockets[0].close()
    expect(statuses.at(-1)).toBe('reconnecting')
    vi.advanceTimersByTime(100)

    expect(sockets).toHaveLength(2)
    client.disconnect()
  })
})
