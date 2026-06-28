export type NodePingStatus = 'green' | 'yellow' | 'red' | 'testing'

export interface NodePing {
  latency: number | null
  status: NodePingStatus
  mineru?: { ok: boolean; status?: number; error?: string }
  server?: { ok: boolean; status?: number; error?: string }
}

export function classifyNodeLatency(latencyMs: number): Exclude<NodePingStatus, 'red' | 'testing'> {
  return latencyMs < 150 ? 'green' : 'yellow'
}

export function isNodeAvailable(ping?: NodePing): boolean {
  return !ping || ping.status !== 'red'
}
