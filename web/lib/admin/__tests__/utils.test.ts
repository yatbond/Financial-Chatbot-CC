import { describe, it, expect } from 'vitest'
import { formatPeriod, calcPaginationMeta } from '../utils'

describe('formatPeriod', () => {
  it('formats Jan 2026', () => expect(formatPeriod(1, 2026)).toBe('Jan 2026'))
  it('formats Dec 2025', () => expect(formatPeriod(12, 2025)).toBe('Dec 2025'))
  it('formats Feb 2026', () => expect(formatPeriod(2, 2026)).toBe('Feb 2026'))
})

describe('calcPaginationMeta', () => {
  it('calculates first page of 143 items at page size 20', () => {
    expect(calcPaginationMeta(143, 1, 20)).toEqual({
      totalPages: 8,
      from: 1,
      to: 20,
      hasPrev: false,
      hasNext: true,
    })
  })
  it('calculates last page', () => {
    expect(calcPaginationMeta(143, 8, 20)).toEqual({
      totalPages: 8,
      from: 141,
      to: 143,
      hasPrev: true,
      hasNext: false,
    })
  })
  it('single page of 5', () => {
    expect(calcPaginationMeta(5, 1, 20)).toEqual({
      totalPages: 1,
      from: 1,
      to: 5,
      hasPrev: false,
      hasNext: false,
    })
  })
  it('zero items', () => {
    expect(calcPaginationMeta(0, 1, 20)).toEqual({
      totalPages: 0,
      from: 0,
      to: 0,
      hasPrev: false,
      hasNext: false,
    })
  })
})
