# BullWarden prop workflow

Velez analyzes TradingView signals and prepares an order proposal. It does not own canonical prop rules.

The Pine v2 payload supplies signal identity, timestamp, selected profile/version, and point value. Velez adds the analyzed quantity, entry, stop, target, setup type, and a fresh broker account observation. BullWarden then evaluates the exact setup.

When BullWarden is enabled:

- approval mode is mandatory and cannot be disabled by the dashboard;
- both the former automatic path and the final approval path call `POST /v1/prop/evaluate`;
- the final path commits the intent identifier, so replaying it is rejected;
- a missing or unavailable response fails closed;
- the broker receives no `_bullwarden` control metadata;
- only an eligible, explicitly approved paper order can report `Submitted through user-controlled workflow`.

The local `prop_profiles.json` catalogue is migration/display data. Every loaded entry is marked `review_required`, and its old risk/broker calibration methods are no-ops. Configure the canonical selection with `BULLWARDEN_PROFILE_KEY` and `BULLWARDEN_RULES_VERSION`; values embedded in a Pine v2 alert must match the bound BullWarden policy.

Required private runtime settings are documented in `bot/deploy/env.example`. Never commit API keys, broker credentials, account identifiers, or environment files.
