// Registering a blocking listener throws unless the MV2-only
// webRequestBlocking permission was granted, so surviving this is the proof.
chrome.webRequest.onBeforeRequest.addListener(
  () => ({ cancel: false }),
  { urls: ['<all_urls>'] },
  ['blocking'],
)
