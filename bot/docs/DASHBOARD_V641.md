# Trading Bull Desk v6.40.1 glass restoration

## Scope

v6.40.1 is a visual-only correction that restores the approved transparent glass system after v6.40.0 made major dashboard surfaces effectively opaque. It does not change trading behavior, calculations, APIs, entitlements, authentication, broker configuration, or execution safeguards.

The stylesheet and application asset references are cache-busted at `6.40.1`; the dashboard-reported build is `v6.40.1`.

## Transparency hierarchy

| Surface | v6.40.0 | v6.40.1 |
|---|---:|---:|
| Night `--glass` | `0.50` | `0.42` |
| Night `--glass-strong` | `0.68` | `0.56` |
| Day `--glass` | `0.58` | `0.40` |
| Day `--glass-strong` | `0.76` | `0.56` |
| `.glass-surface` gradient | `0.74 / 0.54` | `0.48 / 0.34` |
| Day `.glass-surface` gradient | `0.76 / 0.56` | `0.46 / 0.32` |
| `.panel-heading` gradient | `0.98 / 0.82` | `0.24 / 0.10` |
| `.decision-surface` gradient | `0.78 / 0.64` | `0.18 / 0.08` |
| `.pro-card` gradient | `0.98 / 0.98` | `0.42 / 0.30` |
| Mobile `.detail-panel` | `0.96` | `0.58` |
| Mobile `.mobile-glass` gradient | `0.88 / 0.72` | `0.54 / 0.38` |
| Mobile `.topbar` | `0.88` | `0.58` |
| Mobile workflow navigation | `0.94` | `0.62` |

Pro Console no longer terminates its atmospheric gradient in solid `#080b0d`. Its full-screen overlay is `rgba(5, 9, 11, 0.48)` with a localized gold radial glow, and its header and cards now use blurred translucent glass. The TradingView chart surfaces remain solid for chart readability.

Nested metrics, planner output, planner messages, rolling/missed-trade cards, breakdowns, formulas, playbook cards, locked surfaces, warnings, and blocked states retain faint `0.03–0.24` tints instead of adding heavy black layers. The strongest tested ordinary nesting remains below `0.78` effective opacity.

## Responsive and theme treatment

- Desktop Desk and Risk cards inherit the repaired `.glass-surface` treatment.
- Review, Coach, and Lab use the stronger transparent detail workspace with faint decision tiles.
- Mobile keeps safe-area navigation, scrolling, touch targets, and layout rules while removing the opaque detail workspace and bottom-navigation wall.
- Day mode has explicit light-glass treatments and dark typography for decision and mobile surfaces; Pro Console intentionally keeps a focused, translucent dark atmosphere over the day room.
- The room image remains present beneath desktop, mobile, and Pro Console surfaces.

## Regression protection

`test_dashboard_roadmap_frontend.py` validates semantic opacity bands instead of exact cosmetic values. It guards against:

- opaque panel headings, Pro cards, mobile detail panels, top bars, and navigation;
- a solid Pro Console overlay;
- ordinary and nested surfaces leaving their approved opacity ranges;
- nested effective opacity exceeding `0.78` for representative surface pairs;
- missing `14–24px` backdrop blur on principal glass surfaces;
- safety, warning, locked, stale/disclosure, and entitlement treatments becoming opaque.

## Validation

- Complete network-disabled production-image suite: **233 passed**, 0 failed.
- Targeted frontend, responsive, authentication, entitlement, decision-intelligence, and dashboard API suite: **81 passed**, 0 failed.
- JavaScript syntax, HTML ID uniqueness (111 IDs), CSS declaration structure, delimiter balance, and Git whitespace checks: passed.
- No browser engine, Playwright, or Puppeteer is installed on the VPS, so automated screenshots are unavailable. No system-wide browser dependency was installed for this surgical release.
