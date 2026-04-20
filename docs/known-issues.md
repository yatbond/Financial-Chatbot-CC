# Known Issues

> Running list of issues, assumptions, and deferred decisions.

## Open

- [ ] Legacy `.xls` handling — one sample report is BIFF format; `openpyxl` cannot read it. Resolve in Phase 5: pick between `xlrd<2.0` (already installed) or LibreOffice headless conversion.
- [ ] Excel month/year extraction — exact cell/sheet location not yet confirmed. Resolve in Phase 5 by inspecting sample workbooks.
- [ ] Admin role mechanism — Clerk org role vs. `role` column on `project_members`. Resolve in Phase 2.
- [ ] RLS strategy — Supabase RLS vs. app-layer auth checks. Default to RLS in Phase 1.
