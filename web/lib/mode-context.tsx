'use client'

import { createContext, useContext, useState } from 'react'
import type { QueryMode } from './types/database'

interface ModeContextValue {
  mode: QueryMode
  setMode: (mode: QueryMode) => void
}

const ModeContext = createContext<ModeContextValue>({
  mode: 'standard',
  setMode: () => {},
})

export function ModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<QueryMode>('standard')
  return (
    <ModeContext.Provider value={{ mode, setMode }}>
      {children}
    </ModeContext.Provider>
  )
}

export function useMode() {
  return useContext(ModeContext)
}
