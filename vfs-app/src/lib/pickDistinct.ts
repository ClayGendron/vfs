/**
 * Uniform random sampling for the brand fields.
 *
 * `pickDistinct` samples without replacement — the shared core of the three
 * hand-rolled Set-dedupe loops (grep matches, glob leaves, graph groups).
 * `randInt` supplies the random pick-count those sites layer on top.
 */

// k distinct ints in [0, n), sampled uniformly without replacement.
// Caps at n when k > n, so callers need no separate bound check.
export function pickDistinct(k: number, n: number): number[] {
  const limit = Math.min(k, n)
  const chosen = new Set<number>()
  while (chosen.size < limit) {
    chosen.add(Math.floor(Math.random() * n))
  }
  return [...chosen]
}

// Random integer in [min, max], inclusive at both ends.
export function randInt(min: number, max: number): number {
  return min + Math.floor(Math.random() * (max - min + 1))
}
