// Mock query resolver for Phase 9.
// Parses raw query text and returns a ChatResponse.
// Designed to be replaced by the real resolution + shortcut engines in Phase 7/8.
// All mock data shapes match the types the real engine will produce.

import {
  type ChatRequest,
  type ChatResponse,
  type ResolvedParams,
  type AmbiguityOption,
  type ResultRow,
  type SessionContext,
  type VerboseTrace,
  type DiscrepancyWarning,
} from './types'

// ─── Keyword tables ──────────────────────────────────────────────────────────

const FINANCIAL_TYPES: Record<string, string> = {
  projection: 'Projection',
  projected: 'Projection',
  proj: 'Projection',
  wip: 'WIP',
  'business plan': 'Business Plan',
  bp: 'Business Plan',
  committed: 'Committed Cost',
  'committed cost': 'Committed Cost',
  accrual: 'Accrual',
  'cash flow': 'Cash Flow',
  cashflow: 'Cash Flow',
  'latest budget': 'Latest Budget / Revision',
  budget: 'Business Plan',
}

const DATA_TYPES: Record<string, string> = {
  gp: 'Gross Profit',
  'gross profit': 'Gross Profit',
  prelim: 'Preliminaries',
  preliminaries: 'Preliminaries',
  income: 'Income',
  cost: 'Cost',
  sub: 'Sub-contractors',
  subcontractor: 'Sub-contractors',
  materials: 'Materials',
  plant: 'Plant',
  contingency: 'Allow for Contingencies',
  contingencies: 'Allow for Contingencies',
  overhead: 'Overhead',
  claims: 'Claims',
  vo: 'VO/CE',
  'vo/ce': 'VO/CE',
}

const SHEET_MAP: Record<string, string> = {
  projection: 'Projection',
  projected: 'Projection',
  proj: 'Projection',
  committed: 'Committed Cost',
  'committed cost': 'Committed Cost',
  accrual: 'Accrual',
  'cash flow': 'Cash Flow',
  cashflow: 'Cash Flow',
  'financial status': 'Financial Status',
  snapshot: 'Financial Status',
}

const MONTH_NAMES: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, september: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12,
}

const SHORTCUT_KEYWORDS = [
  'shortcut', 'analyze', 'analyse', 'compare', 'trend',
  'list', 'total', 'detail', 'risk', 'type',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function lc(s: string) { return s.toLowerCase().trim() }

function detectShortcut(q: string): string | null {
  for (const kw of SHORTCUT_KEYWORDS) {
    if (q.startsWith(kw + ' ') || q === kw) return kw
  }
  if (q.startsWith('cash flow') || q === 'cash flow') return 'cash flow'
  return null
}

function detectFinancialType(q: string): string | null {
  // longest-match first
  const keys = Object.keys(FINANCIAL_TYPES).sort((a, b) => b.length - a.length)
  for (const k of keys) {
    if (q.includes(k)) return FINANCIAL_TYPES[k]
  }
  return null
}

function detectDataType(q: string): string | null {
  const keys = Object.keys(DATA_TYPES).sort((a, b) => b.length - a.length)
  for (const k of keys) {
    if (q.includes(k)) return DATA_TYPES[k]
  }
  return null
}

function detectMonth(q: string): { name: string; num: number } | null {
  for (const [name, num] of Object.entries(MONTH_NAMES)) {
    if (q.includes(name)) return { name, num }
  }
  return null
}

function detectTrendMonths(q: string, hasShortcut: string | null): number | null {
  if (hasShortcut !== 'trend') return null
  const m = q.match(/\b(\d+)\b/)
  if (m) return parseInt(m[1], 10)
  return 6  // default
}

function formatPeriod(month: number, year = 2026): string {
  const d = new Date(year, month - 1, 1)
  return d.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

// ─── Mock data generators ─────────────────────────────────────────────────────

function mockValueRows(
  financialType: string,
  dataType: string,
  period: string,
): { columns: string[]; rows: ResultRow[] } {
  return {
    columns: ['Financial Type', 'Data Type', 'Period', 'Value (HK$)'],
    rows: [
      {
        'Financial Type': financialType,
        'Data Type': dataType,
        'Period': period,
        'Value (HK$)': 12_450_000,
      },
    ],
  }
}

function mockTrendRows(
  dataType: string,
  financialType: string,
  months: number,
): { columns: string[]; rows: ResultRow[] } {
  const cols = ['Month', `${financialType} — ${dataType} (HK$)`]
  const base = 11_000_000
  const rows: ResultRow[] = Array.from({ length: months }, (_, i) => {
    const m = 2 - (months - 1 - i)  // counting back from Feb 2026
    const month = ((m - 1 + 12) % 12) + 1
    const year = m <= 0 ? 2025 : 2026
    return {
      'Month': formatPeriod(month, year),
      [`${financialType} — ${dataType} (HK$)`]: base + (i - Math.floor(months / 2)) * 320_000,
    }
  })
  return { columns: cols, rows }
}

function mockCompareRows(
  dataType: string,
  typeA: string,
  typeB: string,
  period: string,
): { columns: string[]; rows: ResultRow[] } {
  return {
    columns: ['Data Type', typeA, typeB, 'Difference'],
    rows: [
      {
        'Data Type': dataType,
        [typeA]: 12_450_000,
        [typeB]: 13_100_000,
        'Difference': -650_000,
      },
    ],
  }
}

function mockTotalRows(dataType: string, financialType: string): { columns: string[]; rows: ResultRow[] } {
  return {
    columns: ['Item', 'Data Type', `${financialType} Value (HK$)`],
    rows: [
      { 'Item': '2.2.1', 'Data Type': `${dataType} — Labour`, [`${financialType} Value (HK$)`]: 1_800_000 },
      { 'Item': '2.2.2', 'Data Type': `${dataType} — Materials`, [`${financialType} Value (HK$)`]: 3_200_000 },
      { 'Item': '2.2.3', 'Data Type': `${dataType} — Plant`, [`${financialType} Value (HK$)`]: 900_000 },
      { 'Item': '2.2', 'Data Type': `${dataType} — Total`, [`${financialType} Value (HK$)`]: 5_900_000 },
    ],
  }
}

function mockRiskRows(): { columns: string[]; rows: ResultRow[] } {
  const items = [
    { code: '1.2.1', name: 'VO/CE' },
    { code: '1.7', name: 'Claims' },
    { code: '1.8', name: 'CPF' },
    { code: '2.2.15', name: 'Potential Savings (Materials)' },
    { code: '2.4.4', name: 'Contra Charge' },
    { code: '2.7', name: 'Allow for Contingencies' },
    { code: '2.8', name: 'Allow for Rectifications Works' },
  ]
  return {
    columns: ['Code', 'Item', 'WIP (HK$)', 'Committed Cost (HK$)', 'Cash Flow (HK$)'],
    rows: items.map((item, i) => ({
      'Code': item.code,
      'Item': item.name,
      'WIP (HK$)': 500_000 + i * 120_000,
      'Committed Cost (HK$)': 480_000 + i * 115_000,
      'Cash Flow (HK$)': 510_000 + i * 125_000,
    })),
  }
}

function mockListRows(): { columns: string[]; rows: ResultRow[] } {
  const items = [
    { tier: 1, code: '1', name: 'Income' },
    { tier: 2, code: '1.1', name: 'Contract Sum' },
    { tier: 2, code: '1.2', name: 'Variation / CE' },
    { tier: 2, code: '1.7', name: 'Claims' },
    { tier: 1, code: '2', name: 'Cost' },
    { tier: 2, code: '2.1', name: 'Preliminaries' },
    { tier: 2, code: '2.2', name: 'Sub-contractors' },
    { tier: 2, code: '2.3', name: 'Materials' },
    { tier: 2, code: '2.4', name: 'DSC' },
    { tier: 1, code: '3', name: 'Gross Profit' },
    { tier: 1, code: '5', name: 'Gross Profit (after recon & overhead)' },
  ]
  return {
    columns: ['Tier', 'Item Code', 'Data Type'],
    rows: items.map(i => ({ 'Tier': i.tier, 'Item Code': i.code, 'Data Type': i.name })),
  }
}

function mockCashFlowRows(): { columns: string[]; rows: ResultRow[] } {
  const months = Array.from({ length: 12 }, (_, i) => {
    const m = ((1 + i) % 12) + 1
    return formatPeriod(m, m <= 2 ? 2026 : 2025)
  })
  return {
    columns: ['Month', 'Gross Profit (HK$)', 'GP after Recon (HK$)'],
    rows: months.map((mo, i) => ({
      'Month': mo,
      'Gross Profit (HK$)': 800_000 + i * 50_000,
      'GP after Recon (HK$)': 740_000 + i * 45_000,
    })),
  }
}

// ─── Verbose mock helpers ─────────────────────────────────────────────────────

function mockVerboseTrace(): VerboseTrace {
  return {
    row_number: 42,
    cell_reference: 'C15',
    upload_timestamp: '2026-02-05T09:30:00.000Z',
    source_workbook: 'Feb-2026-Financial-Report.xlsx',
  }
}

function mockDiscrepancyWarnings(): DiscrepancyWarning[] {
  return [
    {
      item: 'VO/CE',
      old_value: 500_000,
      new_value: 620_000,
      superseded_by_upload_id: 'mock-upload-789',
    },
  ]
}

function withVerbose(
  res: Extract<ChatResponse, { type: 'result' }>,
  mode: string,
  withDiscrepancies = false,
): Extract<ChatResponse, { type: 'result' }> {
  if (mode !== 'verbose') return res
  return {
    ...res,
    verbose_trace: mockVerboseTrace(),
    ...(withDiscrepancies ? { discrepancy_warnings: mockDiscrepancyWarnings() } : {}),
  }
}

// ─── Shortcut handler ─────────────────────────────────────────────────────────

function handleShortcut(shortcut: string, q: string, ctx: SessionContext, mode: string): ChatResponse {
  switch (shortcut) {
    case 'shortcut':
      return {
        type: 'info',
        title: 'Supported Shortcuts',
        content: [
          'shortcut — list all shortcuts',
          'type — list all financial types and sheets',
          'list — list tier 1 & 2 items (list 2.2 for sub-items)',
          'risk — compare risk items across WIP, Committed Cost, and Cash Flow',
          'cash flow — GP trend from Cash Flow sheet (last 12 months)',
          'analyze — show exceptions across financial types in Financial Status',
          'compare A vs B — compare two data types side by side',
          'trend A [N] — last 6 (or N) months of monthly data',
          'total A [financial type] — sum and breakdown of children',
          'detail [financial type] [data type] — full item breakdown',
        ].join('\n'),
      }

    case 'type':
      return {
        type: 'info',
        title: 'Available Financial Types & Sheets',
        content: [
          'Snapshot (Financial Status sheet):',
          '  Budget Tender, Business Plan, WIP, Projection,',
          '  Committed Cost, Accrual, Cash Flow, Latest Budget / Revision',
          '',
          'Time-series sheets (monthly movement data):',
          '  Projection, Committed Cost, Accrual, Cash Flow',
        ].join('\n'),
      }

    case 'list': {
      const { columns, rows } = mockListRows()
      return withVerbose({
        type: 'result',
        interpretation: { shortcut: 'list' },
        columns,
        rows,
        summary: 'Showing tier 1 and tier 2 items. Type "list 2.2" for sub-items.',
        context_update: { last_shortcut: 'list' },
      }, mode)
    }

    case 'risk': {
      const { columns, rows } = mockRiskRows()
      return withVerbose({
        type: 'result',
        interpretation: { sheet_name: 'Financial Status', shortcut: 'risk', period: 'Feb 2026' },
        columns,
        rows,
        summary: 'Risk-sensitive items compared across WIP, Committed Cost, and Cash Flow.',
        context_update: { last_shortcut: 'risk', sheet_name: 'Financial Status' },
      }, mode, true)
    }

    case 'cash flow': {
      const { columns, rows } = mockCashFlowRows()
      return withVerbose({
        type: 'result',
        interpretation: { sheet_name: 'Cash Flow', shortcut: 'cash flow' },
        columns,
        rows,
        summary: 'Last 12 months of Gross Profit from Cash Flow sheet.',
        context_update: { last_shortcut: 'cash flow', sheet_name: 'Cash Flow' },
      }, mode)
    }

    case 'analyze':
    case 'analyse': {
      return withVerbose({
        type: 'result',
        interpretation: { sheet_name: 'Financial Status', shortcut: 'analyze', period: 'Feb 2026' },
        columns: ['Code', 'Item', 'Category', 'Projection', 'Comparison', 'Exception'],
        rows: [
          { 'Code': '1.2', 'Item': 'Variation / CE', 'Category': 'Income', 'Projection': 2_100_000, 'Comparison': 2_400_000, 'Exception': 'Projection < WIP' },
          { 'Code': '2.7', 'Item': 'Allow for Contingencies', 'Category': 'Cost', 'Projection': 600_000, 'Comparison': 450_000, 'Exception': 'Projection > Accrual' },
        ],
        summary: 'Showing exceptions only. Projection vs WIP (income) and Projection vs Accrual/Committed/Cash Flow (cost).',
        context_update: { last_shortcut: 'analyze', sheet_name: 'Financial Status' },
      }, mode)
    }

    case 'trend': {
      const months = detectTrendMonths(q, 'trend') ?? 6
      const ft = detectFinancialType(q) ?? ctx.financial_type
      const dt = detectDataType(q) ?? ctx.data_type

      if (!ft && !dt) {
        return {
          type: 'ambiguity',
          interpretation: { shortcut: 'trend', months },
          prompt: 'Which financial type should I trend?',
          options: [
            { label: 'Projection', params: { financial_type: 'Projection', sheet_name: 'Projection' } },
            { label: 'Committed Cost', params: { financial_type: 'Committed Cost', sheet_name: 'Committed Cost' } },
            { label: 'Accrual', params: { financial_type: 'Accrual', sheet_name: 'Accrual' } },
            { label: 'Cash Flow', params: { financial_type: 'Cash Flow', sheet_name: 'Cash Flow' } },
          ],
        }
      }

      if (!dt) {
        return {
          type: 'ambiguity',
          interpretation: { shortcut: 'trend', financial_type: ft ?? undefined, months },
          prompt: `Which data type would you like to trend for ${ft}?`,
          options: [
            { label: 'Gross Profit', params: { data_type: 'Gross Profit' } },
            { label: 'Preliminaries', params: { data_type: 'Preliminaries' } },
            { label: 'Sub-contractors', params: { data_type: 'Sub-contractors' } },
          ],
        }
      }

      const resolvedFt = ft ?? 'Projection'
      const { columns, rows } = mockTrendRows(dt, resolvedFt, months)
      return withVerbose({
        type: 'result',
        interpretation: {
          shortcut: 'trend',
          financial_type: resolvedFt,
          data_type: dt,
          sheet_name: resolvedFt,
          months,
        },
        columns,
        rows,
        context_update: { last_shortcut: 'trend', financial_type: resolvedFt, data_type: dt },
      }, mode)
    }

    case 'compare': {
      // compare A vs B
      const vsMatch = q.match(/compare\s+(.+?)\s+vs\s+(.+?)(?:\s+\d+)?$/i)
      if (vsMatch) {
        const rawA = vsMatch[1].trim()
        const rawB = vsMatch[2].trim()
        const typeA = FINANCIAL_TYPES[rawA] ?? rawA
        const typeB = FINANCIAL_TYPES[rawB] ?? rawB
        const dt = detectDataType(q) ?? ctx.data_type ?? 'Gross Profit'
        const { columns, rows } = mockCompareRows(dt, typeA, typeB, ctx.period ?? 'Feb 2026')
        return withVerbose({
          type: 'result',
          interpretation: { shortcut: 'compare', data_type: dt, period: ctx.period ?? 'Feb 2026' },
          columns,
          rows,
          context_update: { last_shortcut: 'compare' },
        }, mode)
      }
      return {
        type: 'ambiguity',
        interpretation: { shortcut: 'compare' },
        prompt: 'Which two financial types should I compare?',
        options: [
          { label: 'Projection vs WIP', params: { financial_type: 'Projection' } },
          { label: 'Projection vs Business Plan', params: { financial_type: 'Projection' } },
          { label: 'WIP vs Committed Cost', params: { financial_type: 'WIP' } },
        ],
      }
    }

    case 'total': {
      const dt = detectDataType(q) ?? ctx.data_type
      const ft = detectFinancialType(q) ?? ctx.financial_type ?? 'Projection'
      if (!dt) {
        return {
          type: 'ambiguity',
          interpretation: { shortcut: 'total', financial_type: ft },
          prompt: 'Which item should I total?',
          options: [
            { label: 'Total Cost', params: { data_type: 'Cost' } },
            { label: 'Total Preliminaries', params: { data_type: 'Preliminaries' } },
            { label: 'Total Sub-contractors', params: { data_type: 'Sub-contractors' } },
          ],
        }
      }
      const { columns, rows } = mockTotalRows(dt, ft)
      return withVerbose({
        type: 'result',
        interpretation: { shortcut: 'total', data_type: dt, financial_type: ft },
        columns,
        rows,
        context_update: { last_shortcut: 'total', data_type: dt, financial_type: ft },
      }, mode)
    }

    case 'detail': {
      const ft = detectFinancialType(q) ?? ctx.financial_type ?? 'Cash Flow'
      const dt = detectDataType(q) ?? ctx.data_type ?? 'Preliminaries'
      return withVerbose({
        type: 'result',
        interpretation: { shortcut: 'detail', financial_type: ft, data_type: dt, sheet_name: 'Financial Status' },
        columns: ['Item Code', 'Sub-item', `${ft} (HK$)`],
        rows: [
          { 'Item Code': '2.1.1', 'Sub-item': `${dt} — Site Management`, [`${ft} (HK$)`]: 320_000 },
          { 'Item Code': '2.1.2', 'Sub-item': `${dt} — Temp Works`, [`${ft} (HK$)`]: 180_000 },
          { 'Item Code': '2.1.3', 'Sub-item': `${dt} — Equipment`, [`${ft} (HK$)`]: 95_000 },
        ],
        context_update: { last_shortcut: 'detail', financial_type: ft, data_type: dt },
      }, mode)
    }

    default:
      return { type: 'error', message: `Unknown shortcut: ${shortcut}` }
  }
}

// ─── Main resolver ────────────────────────────────────────────────────────────

export function resolveQuery(req: ChatRequest): ChatResponse {
  const mode = req.mode ?? 'standard'

  // Handle ambiguity selection from prior turn
  if (req.selected_option_index !== undefined && req.prior_options) {
    const picked = req.prior_options[req.selected_option_index]
    if (!picked) return { type: 'error', message: 'Invalid option selected.' }

    const ft = picked.params.financial_type ?? req.context.financial_type
    const dt = picked.params.data_type ?? req.context.data_type
    const sheet = picked.params.sheet_name ?? picked.params.financial_type ?? req.context.sheet_name ?? 'Financial Status'
    const period = req.context.period ?? 'Feb 2026'

    if (!dt) {
      return {
        type: 'ambiguity',
        interpretation: { financial_type: ft ?? undefined, sheet_name: sheet },
        prompt: `Which data type for ${ft}?`,
        options: [
          { label: 'Gross Profit', params: { data_type: 'Gross Profit' } },
          { label: 'Preliminaries', params: { data_type: 'Preliminaries' } },
          { label: 'Sub-contractors', params: { data_type: 'Sub-contractors' } },
        ],
      }
    }

    const { columns, rows } = mockValueRows(ft ?? 'Projection', dt, period)
    return withVerbose({
      type: 'result',
      interpretation: { financial_type: ft ?? undefined, data_type: dt, sheet_name: sheet, period },
      columns,
      rows,
      context_update: { financial_type: ft ?? undefined, data_type: dt, sheet_name: sheet },
    }, mode)
  }

  const q = lc(req.query)
  const ctx = req.context

  // ── Shortcuts ────────────────────────────────────────────────────────────
  const shortcut = detectShortcut(q)
  if (shortcut) {
    return handleShortcut(shortcut, q, ctx, mode)
  }

  // ── General query resolution ─────────────────────────────────────────────
  const ft = detectFinancialType(q) ?? ctx.financial_type
  const dt = detectDataType(q) ?? ctx.data_type
  const month = detectMonth(q)
  const period = month
    ? formatPeriod(month.num, 2026)
    : ctx.period ?? 'Feb 2026'

  // No financial type and no data type — can't resolve
  if (!ft && !dt) {
    return {
      type: 'ambiguity',
      interpretation: {},
      prompt: 'I couldn\'t resolve that query. What are you looking for?',
      options: [
        { label: 'Gross Profit (Projection)', params: { financial_type: 'Projection', data_type: 'Gross Profit' } },
        { label: 'Gross Profit (WIP)', params: { financial_type: 'WIP', data_type: 'Gross Profit' } },
        { label: 'Preliminaries (Projection)', params: { financial_type: 'Projection', data_type: 'Preliminaries' } },
        { label: 'Show shortcuts (type "shortcut")', params: {} },
      ],
    }
  }

  // Financial type but no data type
  if (ft && !dt) {
    return {
      type: 'ambiguity',
      interpretation: { financial_type: ft, period },
      prompt: `What data type within ${ft}?`,
      options: [
        { label: 'Gross Profit', params: { data_type: 'Gross Profit' } },
        { label: 'Preliminaries', params: { data_type: 'Preliminaries' } },
        { label: 'Sub-contractors', params: { data_type: 'Sub-contractors' } },
        { label: 'Income', params: { data_type: 'Income' } },
        { label: 'Cost', params: { data_type: 'Cost' } },
      ],
    }
  }

  // Data type but no financial type — need to pick sheet
  if (!ft && dt) {
    // Month present → time-series sheets
    if (month) {
      return {
        type: 'ambiguity',
        interpretation: { data_type: dt, period },
        prompt: `Which financial type for ${dt} in ${period}?`,
        options: [
          { label: 'Projection', params: { financial_type: 'Projection', sheet_name: 'Projection' } },
          { label: 'Committed Cost', params: { financial_type: 'Committed Cost', sheet_name: 'Committed Cost' } },
          { label: 'Accrual', params: { financial_type: 'Accrual', sheet_name: 'Accrual' } },
          { label: 'Cash Flow', params: { financial_type: 'Cash Flow', sheet_name: 'Cash Flow' } },
        ],
      }
    }
    // No month → show snapshot vs monthly choice
    return {
      type: 'ambiguity',
      interpretation: { data_type: dt },
      prompt: `Do you want ${dt} from a snapshot or a monthly sheet?`,
      options: [
        {
          label: `Financial Status snapshot (${period})`,
          params: { sheet_name: 'Financial Status', financial_type: 'Projection' },
        },
        {
          label: 'From Projection monthly sheet (pick month)',
          params: { sheet_name: 'Projection', financial_type: 'Projection' },
        },
        {
          label: 'From Committed Cost monthly sheet',
          params: { sheet_name: 'Committed Cost', financial_type: 'Committed Cost' },
        },
      ],
    }
  }

  // Both resolved
  const TIME_SERIES_TYPES = new Set(['Projection', 'Committed Cost', 'Accrual', 'Cash Flow'])
  const isTimeSeries = TIME_SERIES_TYPES.has(ft!)

  // No month + time-series type → ambiguous: snapshot or monthly sheet?
  if (isTimeSeries && !month) {
    return {
      type: 'ambiguity',
      interpretation: { financial_type: ft!, data_type: dt! },
      prompt: `Do you want ${dt} — ${ft} from Financial Status (snapshot) or the ${ft} monthly sheet?`,
      options: [
        {
          label: `Financial Status snapshot (${period})`,
          params: { sheet_name: 'Financial Status', financial_type: ft! },
        },
        {
          label: `${ft} monthly sheet — choose month`,
          params: { sheet_name: ft!, financial_type: ft! },
        },
      ],
    }
  }

  const resolvedSheet = month ? ft! : 'Financial Status'
  const { columns, rows } = mockValueRows(ft!, dt!, period)
  return withVerbose({
    type: 'result',
    interpretation: {
      financial_type: ft!,
      data_type: dt!,
      sheet_name: resolvedSheet,
      period,
    },
    columns,
    rows,
    context_update: {
      financial_type: ft!,
      data_type: dt!,
      sheet_name: resolvedSheet,
    },
  }, mode)
}
