/**
 * CycloneAI — Animated Cyclone Marker (Phase 5)
 *
 * Creates a visually stunning animated marker with:
 * - Rotating spiral SVG icon
 * - Pulsing intensity ring (red/orange/yellow based on wind speed)
 * - Category label
 * - Smooth CSS animations
 *
 * Pure DOM — no React dependency so it works with MapLibre markers.
 */

// ---- Intensity colour mapping ------------------------------------------------

export function intensityColor(category: string | null | undefined): string {
  if (!category) return '#6B7280';
  if (category.includes('Super'))       return '#DC2626';
  if (category.includes('Extremely'))   return '#EF4444';
  if (category.includes('Very Severe')) return '#F97316';
  if (category.includes('Severe'))      return '#F59E0B';
  if (category.includes('Cyclonic'))    return '#3B82F6';
  return '#6B7280';
}

function pulseSpeed(windKmh: number | null): string {
  if (!windKmh || windKmh < 62) return '3s';
  if (windKmh < 88)  return '2s';
  if (windKmh < 118) return '1.5s';
  if (windKmh < 170) return '1s';
  return '0.7s';  // Super Cyclonic Storm — fastest pulse
}

// ---- CSS Keyframes (injected once) ----------------------------------------

let stylesInjected = false;

function injectStyles(): void {
  if (stylesInjected) return;
  stylesInjected = true;

  const style = document.createElement('style');
  style.textContent = `
    @keyframes cyclone-pulse {
      0%   { transform: scale(1);   opacity: 0.7; }
      50%  { transform: scale(1.8); opacity: 0; }
      100% { transform: scale(1);   opacity: 0; }
    }
    @keyframes cyclone-spin {
      from { transform: rotate(0deg); }
      to   { transform: rotate(360deg); }
    }
    @keyframes cyclone-pulse-ring {
      0%   { transform: scale(1);   opacity: 0.5; }
      100% { transform: scale(2.5); opacity: 0; }
    }
    @keyframes marker-bounce-in {
      0%   { transform: scale(0); opacity: 0; }
      50%  { transform: scale(1.2); }
      100% { transform: scale(1); opacity: 1; }
    }
    .cyclone-marker-root {
      animation: marker-bounce-in 0.4s ease-out;
    }
  `;
  document.head.appendChild(style);
}

// ---- Marker Creation -------------------------------------------------------

export interface AnimatedMarkerOptions {
  name: string;
  category: string | null;
  windKmh: number | null;
  pressureHpa: number | null;
  selected: boolean;
  isLive: boolean;
}

/**
 * Create an animated cyclone marker DOM element.
 * Call this for each cyclone and attach to a MapLibre Marker.
 */
export function createAnimatedCycloneMarker(opts: AnimatedMarkerOptions): HTMLDivElement {
  injectStyles();

  const color = intensityColor(opts.category);
  const pulse = pulseSpeed(opts.windKmh);

  // Root container
  const root = document.createElement('div');
  root.className = 'cyclone-marker-root';
  root.style.cssText = `
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    cursor: pointer;
    z-index: ${opts.selected ? 100 : 10};
  `;

  // Pulsing rings (behind the icon)
  if (opts.isLive) {
    for (let i = 0; i < 3; i++) {
      const ring = document.createElement('div');
      ring.style.cssText = `
        position: absolute;
        top: 50%;
        left: 50%;
        width: 40px;
        height: 40px;
        margin-top: -20px;
        margin-left: -20px;
        border-radius: 50%;
        border: 2px solid ${color};
        opacity: 0;
        animation: cyclone-pulse-ring ${pulse} ease-out infinite;
        animation-delay: ${i * 0.4}s;
        pointer-events: none;
      `;
      root.appendChild(ring);
    }
  }

  // Central icon (rotating spiral)
  const iconContainer = document.createElement('div');
  iconContainer.style.cssText = `
    width: 44px;
    height: 44px;
    border-radius: 50%;
    background: radial-gradient(circle at 40% 40%, ${color}30, ${color}10);
    border: 2.5px solid ${color};
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: ${opts.selected
      ? `0 0 0 3px ${color}40, 0 4px 12px ${color}30`
      : `0 2px 8px rgba(0,0,0,0.15)`
    };
    transition: box-shadow 0.3s ease, transform 0.3s ease;
    transform: ${opts.selected ? 'scale(1.15)' : 'scale(1)'};
    position: relative;
    z-index: 2;
  `;

  // SVG spiral icon (rotates)
  const svgContainer = document.createElement('div');
  svgContainer.style.cssText = `
    animation: cyclone-spin ${pulse} linear infinite;
    display: flex;
    align-items: center;
    justify-content: center;
  `;
  svgContainer.innerHTML = `
    <svg viewBox="0 0 32 32" width="26" height="26" fill="none">
      <circle cx="16" cy="16" r="3" fill="${color}"/>
      <path d="M16 4 C22 4, 28 10, 28 16" stroke="${color}" stroke-width="2" stroke-linecap="round" fill="none" opacity="0.9"/>
      <path d="M28 16 C28 22, 22 28, 16 28" stroke="${color}" stroke-width="2" stroke-linecap="round" fill="none" opacity="0.7"/>
      <path d="M16 28 C10 28, 4 22, 4 16" stroke="${color}" stroke-width="2" stroke-linecap="round" fill="none" opacity="0.5"/>
      <path d="M4 16 C4 10, 10 4, 16 4" stroke="${color}" stroke-width="2" stroke-linecap="round" fill="none" opacity="0.3"/>
      <path d="M16 8 C20 8, 24 12, 24 16" stroke="${color}" stroke-width="1.5" stroke-linecap="round" fill="none" opacity="0.6"/>
      <path d="M24 16 C24 20, 20 24, 16 24" stroke="${color}" stroke-width="1.5" stroke-linecap="round" fill="none" opacity="0.4"/>
    </svg>
  `;
  iconContainer.appendChild(svgContainer);
  root.appendChild(iconContainer);

  // Label pill (below the icon)
  const label = document.createElement('div');
  label.style.cssText = `
    margin-top: 4px;
    background: #FFFFFF;
    border: 1.5px solid ${opts.selected ? color : '#E5E7EB'};
    border-radius: 12px;
    padding: 2px 8px;
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 10px;
    font-weight: 700;
    color: ${opts.selected ? color : '#374151'};
    white-space: nowrap;
    box-shadow: 0 2px 4px rgba(0,0,0,0.08);
    text-align: center;
    z-index: 2;
    position: relative;
  `;
  label.innerText = opts.name;
  root.appendChild(label);

  // Wind speed badge (if available)
  if (opts.windKmh) {
    const windBadge = document.createElement('div');
    windBadge.style.cssText = `
      margin-top: 2px;
      font-family: 'Inter', system-ui, sans-serif;
      font-size: 9px;
      font-weight: 600;
      color: ${color};
      z-index: 2;
      position: relative;
    `;
    windBadge.innerText = `${opts.windKmh} km/h`;
    root.appendChild(windBadge);
  }

  return root;
}

/**
 * Create a track point marker (small dot along the animated trail).
 */
export function createTrackDot(color: string, isLatest: boolean): HTMLDivElement {
  injectStyles();
  const dot = document.createElement('div');
  dot.style.cssText = `
    width: ${isLatest ? 10 : 6}px;
    height: ${isLatest ? 10 : 6}px;
    border-radius: 50%;
    background: ${isLatest ? color : '#FFFFFF'};
    border: ${isLatest ? 'none' : `1.5px solid ${color}`};
    box-shadow: ${isLatest ? `0 0 8px ${color}60` : 'none'};
    ${isLatest ? `animation: cyclone-pulse 2s ease-in-out infinite;` : ''}
  `;
  return dot;
}
