// Suggest an initial, human-readable analysis name from a Google Maps URL (S3-001).
// The name is only a suggestion: the user can always replace it with something
// meaningful. Returns '' when no usable name can be derived from the URL.

function clean(raw: string): string {
  let value: string
  try {
    value = decodeURIComponent(raw)
  } catch {
    value = raw
  }
  // Google Maps uses '+' for spaces in path/query segments.
  return value.replace(/\+/g, ' ').replace(/\s+/g, ' ').trim()
}

export function suggestNameFromMapsUrl(source: string): string {
  let url: URL
  try {
    url = new URL(source)
  } catch {
    return ''
  }

  // Preferred: the place name in /maps/place/<Name>/...
  const place = url.pathname.match(/\/maps\/place\/([^/@]+)/)
  if (place) {
    const name = clean(place[1])
    if (name) return name
  }

  // Fallback: a q=<Name> query parameter (e.g. maps.google.com/?q=...).
  const q = url.searchParams.get('q')
  if (q) {
    const name = clean(q)
    if (name) return name
  }

  return ''
}
