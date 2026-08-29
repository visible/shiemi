```bash
> shiemi?

  a chromium browser.
  you're someone, not a datapoint.

> what's different?

  duckduckgo by default.
  no telemetry, no sign-in.
  content blockers still work.

  a cold profile, sitting idle, opens
  one connection: the update check for
  certificate revocation data, and
  downloads 5 mb of security data.
  before the trim it was 346 mb.

> verify?

  don't take any of that on faith.

  python3 utils/audit_network.py --baseline
  python3 utils/audit_components.py --baseline
  python3 utils/check_defaults.py

  the first fails if the browser reaches
  a host it has no business reaching.
  the second fails if it downloads
  anything that isn't security data.
  the third reads every shipped default
  back out of a fresh profile, because a
  misspelled pref is silent.

> status?

  just for fun, for me and a few friends.

> stack?

  chromium · c++ · gn · ninja
  next.js · typescript          the site

> build?

  the browser needs depot_tools and a
  chromium checkout — point
  SHIEMI_CHROMIUM_SRC at it

  python3 utils/patches.py apply
  python3 utils/build.py

  the site lives in apps/web

  bun install
  bun run web

> license?

  gpl-3.0

> links?

  https://shiemi.com
```
