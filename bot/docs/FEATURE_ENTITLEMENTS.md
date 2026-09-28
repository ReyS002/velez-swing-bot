# Trading Bull Desk feature entitlements

The server-side registry is `bot/core/feature_registry.py`. It is the stable contract for a later website/billing integration; this release intentionally contains no payment processing.

## Tiers

Core includes Desk, TradingView Trade, setup and market context, essential risk state, the basic non-submitting planner, basic journal, health/authentication/approval/emergency state, playbook, private thesis notes, and verified basic annotation context.

Pro adds Pro Console, the advanced readiness breakdown, advanced planner analytics, performance attribution, Mentor/Coach intelligence, missed-trade analysis, Discipline Score, replay/Lab, advanced annotations, and deeper regime/strategy analytics.

Safety-designated features are always allowed: risk limits and warnings, endpoint disclosure, approval state, authentication/health status, emergency state, and basic verified levels. A future billing adapter must not change that invariant.

## Resolution and enforcement

- `VELEZ_DASHBOARD_TIER` accepts `core` or `pro` and defaults to `pro`, preserving current owner access.
- Usernames in `VELEZ_DASHBOARD_ADMIN_USERS` always resolve to Pro after dashboard authentication.
- Unknown tiers resolve fail-closed to Core. Unknown feature keys are denied.
- `/api/entitlements` exposes the authenticated registry result without billing data.
- Premium API groups are checked in authenticated middleware and return HTTP 403 with `feature_not_entitled` when denied.
- `/api/pro/bootstrap` must succeed before the browser opens Pro Console.
- Browser labels and `data-feature` hooks are presentation aids, never the authorization boundary.

The current Basic-auth deployment has one owner identity. When website billing exists, its authenticated identity/tier resolver can replace the environment lookup while retaining `feature_allowed()` and the registry as the policy boundary.
