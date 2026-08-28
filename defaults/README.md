# Shipped defaults

`initial_preferences` is read once, on first run, from the directory holding
the executable. Chromium maps the whole file into the new profile's prefs, so
anything registered as a pref can be defaulted here — with no patch, and so no
rebase cost every four weeks. Everything below stays user-overridable in
Settings, which is the point: these are defaults, not policy.

Existing profiles are untouched. Delete the user data directory to test a
change.

| Key | Why |
| --- | --- |
| `safebrowsing.enabled` | Without a Google API key `GetAPIKey()` returns the literal `"dummytoken"`, which is not empty, so the key is appended and the lookup is sent and refused. That leaks our IP and 4-byte hashes of visited URLs for a verdict that never arrives. |
| `safebrowsing.enhanced` | Set alongside so neither tier can be left on by a stale profile. |
| `profile.cookie_controls_mode` | `1` is `kBlockThirdParty`. Chromium ships `2`, `kIncognitoOnly`, which allows third-party cookies in ordinary browsing. |
| `https_first_balanced_mode_enabled` | Upgrades navigations to HTTPS without the hard failure of full HTTPS-Only. Chromium decides this with a "typically secure user" heuristic, but skips the heuristic entirely once the pref has a value, so setting it makes the behaviour deterministic. |
| `hide_web_store_icon` | `top_sites_factory.cc` prepopulates the new tab page with a Web Store tile on every fresh profile, and `extension_ui_util.cc` puts the same icon in the app launcher. Both read this pref, so one line removes both. |

`initial_preferences` seeds the default profile only. A profile the user creates
later falls back to the registered default, so anything that has to hold
unconditionally needs the registered default changed instead.
