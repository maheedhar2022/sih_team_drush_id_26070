/**
 * CycloneAI — Centralized Color Palette
 *
 * Single source of truth for all colors used across the application.
 * Import from here — never hard-code hex values in components.
 */

export const colors = {
  // ---- Primary ----
  deepNavy:    '#0B1220',
  primaryBlue: '#2563EB',
  cyan:        '#06B6D4',
  tealGreen:   '#10B981',

  // ---- Secondary ----
  darkSlate:   '#1E293B',
  slate:       '#334155',
  mutedGray:   '#64748B',
  lightSurface:'#E2E8F0',

  // ---- Text ----
  textPrimary:   '#FFFFFF',
  textSecondary: '#CBD5E1',
  textMuted:     '#94A3B8',
  textDisabled:  '#64748B',

  // ---- Status ----
  success: '#22C55E',
  warning: '#F59E0B',
  danger:  '#EF4444',
  info:    '#8B5CF6',

  // ---- Map / Data Viz ----
  ocean:       '#0EA5E9',
  land:        '#84CC16',
  coastline:   '#FDE68A',
  cycloneTrack:'#F87171',
  aiTrack:     '#8B5CF6',

  // ---- Cyclone Intensity Scale ----
  intensityDepression:     '#38BDF8',
  intensityDeepDepression: '#3B82F6',
  intensityCyclonicStorm:  '#FBBF24',
  intensitySevere:         '#F97316',
  intensityExtreme:        '#EF4444',

  // ---- UI Elements ----
  sidebar:    '#0F172A',
  navbar:     '#1E293B',
  btnIdle:    '#2D3B55',
  btnHover:   '#3B82F6',
  inputField: '#E2E8F0',
  divider:    '#475569',
} as const;

export type ColorKey = keyof typeof colors;

/** Map cyclone intensity category to a color */
export function intensityColor(category: string | null | undefined): string {
  switch (category) {
    case 'Depression':                    return colors.intensityDepression;
    case 'Deep Depression':               return colors.intensityDeepDepression;
    case 'Cyclonic Storm':                return colors.intensityCyclonicStorm;
    case 'Severe Cyclonic Storm':         return colors.intensitySevere;
    case 'Very Severe Cyclonic Storm':    return colors.intensitySevere;
    case 'Extremely Severe Cyclonic Storm': return colors.intensityExtreme;
    case 'Super Cyclonic Storm':          return colors.intensityExtreme;
    default:                              return colors.mutedGray;
  }
}

/** Map DataMode to a UI status color */
export function dataModeColor(mode: string): string {
  switch (mode) {
    case 'LIVE':    return colors.success;
    case 'DEMO':    return colors.warning;
    case 'DELAYED': return colors.warning;
    case 'OFFLINE': return colors.danger;
    default:        return colors.mutedGray;
  }
}
