import { requestJson } from './devices'

export interface StreamPlayback {
  device_id: string
  channel_no: number
  protocol: 'hls'
  playback_url: string
  expires_at: string | null
  quality: 'high' | 'fluent'
}

export interface VideoMediaInfo {
  codec_name: string | null
  codec_long_name: string | null
  width: number | null
  height: number | null
  pixel_format: string | null
  fps: number | null
  frame_rate: string | null
  average_frame_rate: string | null
  bitrate: number | null
  profile: string | null
  level: number | null
}

export interface AudioMediaInfo {
  available: boolean
  codec_name: string | null
  sample_rate: number | null
  channels: number | null
  channel_layout: string | null
  bitrate: number | null
}

export interface MediaInfo {
  device_id: string
  channel_no: number
  video: VideoMediaInfo | null
  audio: AudioMediaInfo
}

export function fetchLiveStream(
  deviceSerial: string,
  channelNo: number,
  signal?: AbortSignal,
): Promise<StreamPlayback> {
  const query = new URLSearchParams({ channel_no: String(channelNo), quality: 'high' })
  return requestJson(
    `/api/devices/${encodeURIComponent(deviceSerial)}/stream?${query.toString()}`,
    signal,
  )
}

export function fetchMediaInfo(
  deviceSerial: string,
  channelNo: number,
  signal?: AbortSignal,
): Promise<MediaInfo> {
  const query = new URLSearchParams({ channel_no: String(channelNo) })
  return requestJson(
    `/api/devices/${encodeURIComponent(deviceSerial)}/media-info?${query.toString()}`,
    signal,
  )
}
