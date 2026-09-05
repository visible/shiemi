# Shipped defaults

`initial_preferences` is read once, on first run, from the directory holding
the executable. Chromium maps the whole file into the new profile's prefs, so
anything registered as a pref can be defaulted here — with no patch, and so no
rebase cost every four weeks. Everything below stays user-overridable in
Settings, which is the point: these are defaults, not policy.

Existing profiles are untouched. Delete the user data directory to test a
change.

## Traffic the browser would otherwise send by itself

| Key | Why |
| --- | --- |
| `safebrowsing.enabled` | Without a Google API key `GetAPIKey()` returns the literal `"dummytoken"`, which is not empty, so the key is appended and the lookup is sent and refused. That leaks our IP and 4-byte hashes of visited URLs for a verdict that never arrives. |
| `safebrowsing.enhanced` | Set alongside so neither tier can be left on by a stale profile. |
| `search.suggest_enabled` | Defaults to true, which sends what is being typed in the omnibox to the default engine keystroke by keystroke, before anything is submitted. Local history and bookmark suggestions are unaffected. |
| `profile.password_manager_leak_detection` | Defaults to true, and sends a hash prefix of the username and password to Google on every credential submission. Probably already failing without an API key, but the pref is where the intent belongs. |
| `alternate_error_pages.enabled` | Defaults to true, which sends the URL that failed to load off the device to fetch suggested alternatives. The plain network error page loses nothing but the suggestions. |
| `translate.enabled` | Defaults to true. Detection is on-device, but accepting the offer POSTs page content to `translate.googleapis.com`. This only stops the automatic offer; the context menu still translates on request. |
| `enable_a_ping` | Hyperlink auditing. Defaults to true, so a link carrying `ping=` fires a background POST to a third party on click. Nothing on a page depends on the result. |
| `media_router.enable_media_router` | Cast discovers receivers over mDNS on the local network. Chromium defaults it on in `profile_impl.cc`, so an idle browser probes the LAN. |
| `net.network_prediction_options` | `2` is `kDisabled`. The default is standard preloading, which prerenders a likely next page: that runs the page's scripts, sets its cookies and fires its analytics for a visit the user never made. Costs some navigation latency, and is the one entry here traded against speed rather than for it. |

## Boundaries between sites

| Key | Why |
| --- | --- |
| `profile.cookie_controls_mode` | `1` is `kBlockThirdParty`. Chromium ships `2`, `kIncognitoOnly`, which allows third-party cookies in ordinary browsing. |
| `privacy_sandbox.first_party_sets_enabled` | Defaults to true. Related Website Sets lets a group of domains declare themselves one party and share cookies across the group, which is an exception mechanism aimed squarely at the setting above. Blocking third-party cookies and then honouring the opt-out would be theatre. |
| `webrtc.ip_handling_policy` | Defaults to `"default"`, which offers host candidates, so a page opening a peer connection learns the machine's LAN address. `"default_public_interface_only"` withholds it and calls still connect. `"disable_non_proxied_udp"` would go further and commonly breaks video calls, so it is not used. |
| `payments.can_make_payment_enabled` | Defaults to true, letting a site ask whether the browser has a payment method before the user agrees to anything. Answering false costs a "pay with browser" button that has nothing behind it on a fresh profile anyway. |
| `https_first_balanced_mode_enabled` | Upgrades navigations to HTTPS without the hard failure of full HTTPS-Only. Chromium decides this with a "typically secure user" heuristic, but skips the heuristic entirely once the pref has a value, so setting it makes the behaviour deterministic. |

## The blocker we ship

| Key | Why |
| --- | --- |
| `extensions.pinned_extensions` | The bundled content blocker's own id, so its icon sits in the toolbar from the first launch. Without this the extension is installed and working but has no visible control: its popup is where per-site rules and the "off on this site" switch live, and there is no other route to them. The id is fixed by the key that signed the release, and `tests/test_build.py` checks it still matches the one `utils/fetch_ublock.py` ships. |

## Surfaces we do not want in the UI

| Key | Why |
| --- | --- |
| `hide_web_store_icon` | `top_sites_factory.cc` prepopulates the new tab page with a Web Store tile on every fresh profile, and `extension_ui_util.cc` puts the same icon in the app launcher. Both read this pref, so one line removes both. |
| `browser.gemini_settings` | `1` is `SettingsPolicyState::kDisabled`. `kGlic` is `FEATURE_ENABLED_BY_DEFAULT` on Windows, so Gemini ships enabled and only stays dark because `IsEnabled()` needs a capable primary account. Setting this stops one sign-in from surfacing it. |
| `lens.policy.lens_overlay_settings` | `1` is `LensOverlaySettingsPolicyValue::kDisabled`. `kLensOverlay` is enabled by default on desktop; it stays dark only because its `google-dse-required` param is true and the default engine is DuckDuckGo. Setting this decouples it from the search choice. |
| `toolbar.pinned_actions` | `toolbar_pref_names.cc` pins Chrome Labs by default, and the guard that suppresses it — an early return on the stable channel — never fires here, because `GetChromeChannel()` only reads a channel under `GOOGLE_CHROME_BRANDING` and otherwise returns `UNKNOWN`. The flask stays absent today only because 151's lab list is an empty vector; the next release that adds a lab would surface it. An empty list also opts out of anything upstream decides to pin by default later. |
| `toolbar.pinned_chrome_labs_migration_complete` | Required, or the above does nothing. `MaybeMigrateExistingPinnedStates` re-pins Chrome Labs on first run unless this flag is already set, which silently undid the empty list until it was set too. |
| `omnibox.show_ai_mode_omnibox_button` | Defaults to true. The chip needs `omnibox::kAimEnabled` and a Google default engine as well, so it is off three times over, but this is the only one of the three we control. |
| `omnibox.show_google_lens_shortcut` | Same reasoning as above, for the Lens entry in the omnibox. |

Several of these guard against a change rather than a present leak. Gemini and
Lens are both already inert, for unrelated reasons — no account, and a
non-Google default engine. Neither reason is a setting we control once the
browser is in someone's hands, so both are pinned off explicitly.

## What cannot go here

`initial_preferences` seeds profile prefs only, so a browser-wide pref in
`Local State` is out of reach however much it belongs in this list. Three are
worth naming because they read like omissions:

- `dns_over_https.mode` and `dns_over_https.templates`. The effective default is
  `"automatic"`, which upgrades only when the system resolver already advertises
  DoH, so on most machines nothing is encrypted. Pinning a resolver needs a
  command-line switch or a changed registered default.
- `background_mode.enabled`, which lets the process outlive the last window.
- `domain_reliability.allowed_by_policy`. Already inert: the service is never
  constructed unless metrics reporting is on, and that returns false outright
  without `GOOGLE_CHROME_BRANDING`.

Also deliberately absent: `privacy_sandbox.m1.topics_enabled` and its two
siblings all register as false and are re-cleared at every service startup by
`kPrivacySandboxAdPrivacyUxDeprecation`, so listing them would be dead weight.
`spellcheck.use_spelling_service` is already false. `signin.allowed` is
recomputed from `signin.allowed_on_next_startup` on every launch, so a value
written here would be overwritten before it was ever read.

A profile the user creates later falls back to the registered default, so
anything that has to hold unconditionally needs the registered default changed
instead.
