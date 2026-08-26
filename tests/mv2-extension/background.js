// A blocking webRequest listener is the capability Manifest V3 removes and
// that content blockers rely on. Registering it throws unless the MV2-only
// webRequestBlocking permission was actually granted, so a background page
// that stays alive with this registered proves the path works end to end.
chrome.webRequest.onBeforeRequest.addListener(
  () => ({ cancel: false }),
  { urls: ['<all_urls>'] },
  ['blocking'],
)
