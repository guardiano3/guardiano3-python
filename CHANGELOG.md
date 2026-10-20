# Changelog

All notable changes to this SDK. Versions follow [semver](https://semver.org/);
while the version is 0.x, a minor release may contain breaking changes.

## 0.1.0 (2026-10-20)

- First release: generated models and operations for the GuardianO3 `/v1` API,
  over a hand-written transport with typed errors, retries with jitter,
  idempotency keys, cursor pagination and live sessions (`guardiano3[live]`).
- Requires Python 3.10+. Defaults to the production API,
  `https://api.guardiano3.com`.
