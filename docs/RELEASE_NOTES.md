# v0.1.0-beta

Initial beta publication of a local Playwright helper for Close Friends CSV tracking and
limited, user-approved additions. No automatic reloads, theme overrides or API-login code.

The helper keeps account data outside the source repository by default. New checkmarks
remain pending until a separate manual-refresh audit; old logs retain their evidence
categories. Unknown state, uncertain clicks and detected page/request errors do not
trigger automatic re-clicks.

Includes documentation, synthetic offline tests, local mocked DOM integration tests,
GitHub Actions configuration, a public-file manifest and a limited publication checker.

**Validation:** see docs/TESTING.md for the actual local build tests. This release has not
been validated against a live Instagram session by the packager. Earlier development-run
successes do not prove this exact release will work on every account/interface. Do not
advertise it as rate-limit-free or production-ready.

**Limits:** observed English-language controls, user-declared account identity and stale
username snapshots. No Windows locking implementation, automatic follower synchronization,
CAPTCHA solving, direct API login or unrestricted bulk mode. Instagram may reject automation.
