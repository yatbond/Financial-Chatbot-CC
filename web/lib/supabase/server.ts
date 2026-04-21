import { createClient } from '@supabase/supabase-js'

// Uses the untyped client to avoid supabase-js v2.104 GenericSchema
// compatibility issues with manually-authored Database types. Replace with
// createClient<Database>(url, key) once Supabase CLI generates official types.
export function createServerSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) {
    throw new Error('Missing Supabase environment variables. Set NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.')
  }
  return createClient(url, key)
}
