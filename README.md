```bash
> shiemi?

  a chromium browser.
  you're someone, not a datapoint.

> what's different?

  duckduckgo by default.
  no telemetry, no sign-in.
  content blockers still work.

  a cold profile, sitting idle, opens
  one connection: the component update
  check. it pulls 5 mb — revoked
  certificates, certificate transparency
  logs, a password-strength wordlist,
  hyphenation dictionaries.
  before the trim it was 346 mb.

> faster?

  starts in 287 ms where the upstream
  build of the same version takes 423,
  and holds eight tabs in 16% less
  memory.

  not a compiler trick — both builds
  carry the same optimisations. it is
  the work that never starts.

> verify?

  don't take any of that on faith.

  python3 utils/audit_network.py --baseline
  python3 utils/audit_components.py --baseline
  python3 utils/check_defaults.py
  python3 utils/check_search_default.py
  python3 utils/bench.py --compare <binary>

  the first fails if the browser reaches
  a host it has no business reaching.
  the second fails if it downloads a
  component that isn't on the list.
  the third reads every shipped default
  back out of a fresh profile, because a
  misspelled pref is silent. the fourth
  checks the search engine survives in
  regions whose engine list is short.
  the last re-runs the numbers above
  against any binary you point it at.

  pass --as-installed to the third and
  it reads the defaults an installer put
  on disk, instead of the build tree's.

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
