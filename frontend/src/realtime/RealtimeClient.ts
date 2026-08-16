import { parseRealtimeMessage, type RealtimeEnvelope } from './types'

export type RealtimeConnectionStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'

type MessageListener = (message: RealtimeEnvelope) => void
type StatusListener = (status: RealtimeConnectionStatus) => void
type SocketFactory = (url: string) => WebSocket

export interface RealtimeClientOptions {
  url: string
  socketFactory?: SocketFactory
  reconnectBaseMs?: number
  reconnectMaxMs?: number
}

export class RealtimeClient {
  private socket: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempt = 0
  private intentionallyClosed = true
  private status: RealtimeConnectionStatus = 'disconnected'
  private readonly messageListeners = new Set<MessageListener>()
  private readonly statusListeners = new Set<StatusListener>()
  private readonly socketFactory: SocketFactory
  private readonly reconnectBaseMs: number
  private readonly reconnectMaxMs: number

  constructor(private readonly options: RealtimeClientOptions) {
    this.socketFactory = options.socketFactory ?? ((url) => new WebSocket(url))
    this.reconnectBaseMs = options.reconnectBaseMs ?? 1_000
    this.reconnectMaxMs = options.reconnectMaxMs ?? 15_000
  }

  connect(): void {
    if (this.socket?.readyState === 1 || this.socket?.readyState === 0) {
      return
    }
    this.intentionallyClosed = false
    this.clearReconnectTimer()
    this.setStatus(this.reconnectAttempt > 0 ? 'reconnecting' : 'connecting')

    const socket = this.socketFactory(this.options.url)
    this.socket = socket
    socket.onopen = () => {
      if (this.socket !== socket) return
      this.reconnectAttempt = 0
      this.setStatus('connected')
    }
    socket.onmessage = (event) => {
      const message = parseRealtimeMessage(String(event.data))
      if (message) this.messageListeners.forEach((listener) => listener(message))
    }
    socket.onerror = () => socket.close()
    socket.onclose = () => {
      if (this.socket !== socket) return
      this.socket = null
      if (this.intentionallyClosed) {
        this.setStatus('disconnected')
      } else {
        this.scheduleReconnect()
      }
    }
  }

  disconnect(): void {
    this.intentionallyClosed = true
    this.reconnectAttempt = 0
    this.clearReconnectTimer()
    const socket = this.socket
    this.socket = null
    socket?.close()
    this.setStatus('disconnected')
  }

  onMessage(listener: MessageListener): () => void {
    this.messageListeners.add(listener)
    return () => this.messageListeners.delete(listener)
  }

  onStatus(listener: StatusListener): () => void {
    this.statusListeners.add(listener)
    listener(this.status)
    return () => this.statusListeners.delete(listener)
  }

  private scheduleReconnect(): void {
    this.setStatus('reconnecting')
    const delay = Math.min(
      this.reconnectBaseMs * 2 ** this.reconnectAttempt,
      this.reconnectMaxMs,
    )
    this.reconnectAttempt += 1
    this.reconnectTimer = setTimeout(() => this.connect(), delay)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private setStatus(status: RealtimeConnectionStatus): void {
    if (this.status === status) return
    this.status = status
    this.statusListeners.forEach((listener) => listener(status))
  }
}
