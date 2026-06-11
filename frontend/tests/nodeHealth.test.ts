import { describe, expect, it } from 'vitest'
import { classifyNodeLatency, isNodeAvailable } from '../src/utils/nodeHealth'

describe('node health utils', () => {
  it('keeps a slow successful node available', () => {
    const status = classifyNodeLatency(1200)

    expect(status).toBe('yellow')
    expect(isNodeAvailable({ latency: 1200, status })).toBe(true)
  })
})
