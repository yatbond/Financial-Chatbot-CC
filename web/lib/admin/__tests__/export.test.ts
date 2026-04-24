import { describe, it, expect } from 'vitest'
import { buildExportMarkdown, type ExportData } from '../export'

const BASE: ExportData = {
  projectCode: 'PROJ-001',
  projectName: 'Northshore',
  generatedAt: '2026-04-24T09:00:00.000Z',
  queryLogIssues: [],
  mappingIssues: [],
  discrepancyNotes: [],
}

describe('buildExportMarkdown', () => {
  it('includes header with project info', () => {
    const md = buildExportMarkdown(BASE)
    expect(md).toContain('PROJ-001 Northshore')
    expect(md).toContain('2026-04-24T09:00:00.000Z')
    expect(md).toContain('paste this file into Claude Code')
  })

  it('omits empty sections', () => {
    const md = buildExportMarkdown(BASE)
    expect(md).not.toContain('## Query Log Issues')
    expect(md).not.toContain('## Mapping Issues')
    expect(md).not.toContain('## Discrepancy Notes')
  })

  it('renders a query log issue', () => {
    const data: ExportData = {
      ...BASE,
      queryLogIssues: [{
        index: 1,
        rawQuery: 'labour cost',
        responseType: 'ambiguity',
        mode: 'standard',
        executionMs: 67,
        loggedAt: '2026-04-22T08:55:00.000Z',
        adminNote: 'alias missing from heading_map',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Query Log Issues (1)')
    expect(md).toContain('[QL-1] ambiguity — "labour cost"')
    expect(md).toContain('alias missing from heading_map')
    expect(md).toContain('web/lib/chat/resolver.ts')
  })

  it('renders a mapping issue', () => {
    const data: ExportData = {
      ...BASE,
      mappingIssues: [{
        index: 1,
        mappingType: 'financial_type_map',
        filename: 'ftm_2026.csv',
        uploadedAt: '2026-04-20T14:00:00.000Z',
        adminNote: 'Prelims not matching',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Mapping Issues (1)')
    expect(md).toContain('[MAP-1] financial_type_map — ftm_2026.csv')
    expect(md).toContain('Prelims not matching')
  })

  it('renders a discrepancy note', () => {
    const data: ExportData = {
      ...BASE,
      discrepancyNotes: [{
        index: 1,
        sheetName: 'P&L',
        period: '2026-02',
        dataType: 'Labour Cost',
        itemCode: 'LC-001',
        oldValue: 12400,
        newValue: 13100,
        reviewStatus: 'pending',
        reviewerNote: 'genuine data change',
      }],
    }
    const md = buildExportMarkdown(data)
    expect(md).toContain('## Discrepancy Notes (1)')
    expect(md).toContain('[DISC-1] P&L — 2026-02 — Labour Cost')
    expect(md).toContain('genuine data change')
  })
})
