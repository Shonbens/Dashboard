import { Banknote, Cpu, Globe2, ShieldAlert, Sunrise, TrendingUp, SlidersHorizontal } from 'lucide-react'

// Professional icons for the preset scenarios (replaces emoji coming from the API)
export const SCENARIO_ICON = {
  global_crisis: Globe2,
  local_geopolitical: ShieldAlert,
  rate_hike: TrendingUp,
  shekel_strength: Banknote,
  tech_correction: Cpu,
  soft_landing: Sunrise,
  custom: SlidersHorizontal,
}
export const scenarioIcon = (id) => SCENARIO_ICON[id] ?? SlidersHorizontal
