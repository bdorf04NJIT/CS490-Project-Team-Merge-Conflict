// DO NOT MERGE. Deliberately untested code to prove the coverage gate fails.

export function classifyRating(rating: number): string {
  if (rating >= 4.5) return 'excellent'
  if (rating >= 3.5) return 'good'
  if (rating >= 2.5) return 'mixed'
  return 'poor'
}

export function averageLength(texts: string[]): number {
  if (texts.length === 0) return 0
  let total = 0
  for (const text of texts) {
    total += text.trim().length
  }
  return total / texts.length
}

export function bucketReviews(ratings: number[]): Record<string, number> {
  const buckets: Record<string, number> = {}
  for (const rating of ratings) {
    const label = classifyRating(rating)
    buckets[label] = (buckets[label] ?? 0) + 1
  }
  return buckets
}
