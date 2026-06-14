/**
 * P4 SSE 事件信封类型与 EventSource 封装。
 *
 * 使用原生 EventSource 连接后端 SSE 接口，支持自动重连、事件去重和页面卸载清理。
 */

import type { AgentRunStatus } from './agent'

// ===== 事件信封类型 =====

export type AgentRunEventType =
  | 'run.started'
  | 'node.started'
  | 'message.delta'
  | 'node.completed'
  | 'run.completed'
  | 'run.failed'
  | 'run.cancelled'

export interface RuntimeEventPayload {
  node_name?: string | null
  delta?: string | null
  output?: string | null
  error_message?: string | null
  reason?: string | null
}

export interface RuntimeEventEnvelope {
  event_id: string
  event_type: AgentRunEventType
  run_id: string
  sequence: number
  timestamp: string
  status: AgentRunStatus
  payload: RuntimeEventPayload
}

// ===== 连接状态 =====

export type SSEConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'

// ===== 终止事件类型 =====

const TERMINAL_EVENT_TYPES: ReadonlySet<string> = new Set([
  'run.completed',
  'run.failed',
  'run.cancelled',
])

// ===== 事件回调 =====

export type RuntimeEventHandler = (event: RuntimeEventEnvelope) => void

// ===== EventSource 封装 =====

export class AgentEventSource {
  private source: EventSource | null = null
  private connectionId = 0
  private _status: SSEConnectionStatus = 'idle'
  private _onStatusChange: ((status: SSEConnectionStatus) => void) | null = null
  private _onEvent: RuntimeEventHandler | null = null
  private _onError: ((message: string) => void) | null = null

  get status(): SSEConnectionStatus {
    return this._status
  }

  set onStatusChange(handler: ((status: SSEConnectionStatus) => void) | null) {
    this._onStatusChange = handler
  }

  set onEvent(handler: RuntimeEventHandler | null) {
    this._onEvent = handler
  }

  set onError(handler: ((message: string) => void) | null) {
    this._onError = handler
  }

  /**
   * 连接到指定 events_url，为每个 P4 事件类型注册监听器。
   */
  connect(eventsUrl: string): void {
    this.close()

    const id = ++this.connectionId
    this._status = 'connecting'
    this._onStatusChange?.(this._status)

    const source = new EventSource(eventsUrl)
    this.source = source

    source.onopen = () => {
      if (id !== this.connectionId) { return }
      this._status = 'open'
      this._onStatusChange?.(this._status)
    }

    source.onerror = () => {
      if (id !== this.connectionId) { return }
      // 原生 EventSource 会在 readyState 为 CONNECTING 时自动重连
      if (source.readyState === EventSource.CONNECTING) {
        this._status = 'reconnecting'
        this._onStatusChange?.(this._status)
      } else if (source.readyState === EventSource.CLOSED) {
        this._status = 'closed'
        this._onStatusChange?.(this._status)
      }
    }

    // 为每个 P4 事件类型注册监听器
    const eventTypes: AgentRunEventType[] = [
      'run.started',
      'node.started',
      'message.delta',
      'node.completed',
      'run.completed',
      'run.failed',
      'run.cancelled',
    ]

    for (const eventType of eventTypes) {
      source.addEventListener(eventType, (messageEvent) => {
        if (id !== this.connectionId) { return }

        const rawEvent = messageEvent as MessageEvent
        try {
          const envelope: RuntimeEventEnvelope = JSON.parse(rawEvent.data)
          this._onEvent?.(envelope)

          // 终止事件后主动关闭连接
          if (TERMINAL_EVENT_TYPES.has(eventType)) {
            this.close()
          }
        } catch {
          this._onError?.('SSE 事件解析失败，已忽略该事件。')
        }
      })
    }
  }

  /**
   * 主动关闭 EventSource，不再重连。
   */
  close(): void {
    if (this.source) {
      this.source.close()
      this.source = null
    }
    if (this._status !== 'closed' && this._status !== 'idle') {
      this._status = 'closed'
      this._onStatusChange?.(this._status)
    }
  }
}
