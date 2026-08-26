declare module 'ezuikit-js' {
  export interface EZUIKitError {
    type?: string
    data?: { nErrorCode?: number }
  }

  export interface EZUIKitPlayerOptions {
    id: string
    accessToken: string
    url: string
    width: number
    height: number
    template?: 'pcLive' | 'simple' | 'standard' | 'security'
    audio?: boolean
    autoPlay?: boolean
    decoderType?: 'auto' | 'v1' | 'v3'
    staticPath?: string
    quality?: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 'pp' | 'qp'
    language?: 'zh' | 'en'
    disableRenderPrivateData?: boolean
    streamInfoCBType?: 0 | 1
    loggerOptions?: {
      name?: string
      level?: 'INFO' | 'LOG' | 'WARN' | 'ERROR'
      showTime?: boolean
    }
    handleSuccess?: () => void
    handleError?: (error: EZUIKitError) => void
  }

  export class EZUIKitPlayer {
    static EVENTS: {
      firstFrameDisplay: string
      streamInfoCB: string
      audioInfo: string
      videoInfo: string
    }

    constructor(options: EZUIKitPlayerOptions)

    eventEmitter: {
      on(event: string, handler: (data?: unknown) => void): void
      off(event: string, handler: (data?: unknown) => void): void
    }

    play(): Promise<void>
    stop(): Promise<void>
    destroy(): void
    resize(width: number, height: number): void
  }
}
