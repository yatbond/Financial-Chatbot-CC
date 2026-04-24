const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

export function formatPeriod(month: number, year: number): string {
  return `${MONTHS[month - 1]} ${year}`
}

export interface PaginationMeta {
  totalPages: number
  from: number
  to: number
  hasPrev: boolean
  hasNext: boolean
}

export function calcPaginationMeta(total: number, page: number, pageSize: number): PaginationMeta {
  if (total === 0) return { totalPages: 0, from: 0, to: 0, hasPrev: false, hasNext: false }
  const totalPages = Math.ceil(total / pageSize)
  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, total)
  return { totalPages, from, to, hasPrev: page > 1, hasNext: page < totalPages }
}
