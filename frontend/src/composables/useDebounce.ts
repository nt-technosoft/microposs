/**
 * Debounce utilities.
 */

/**
 * Returns a debounced version of `fn` that delays invocation by `delay` ms.
 * The returned function has the same signature as `fn`.
 */
export function debounce<Args extends unknown[], Return>(
  fn: (...args: Args) => Return,
  delay: number,
): (...args: Args) => void {
  let timer: ReturnType<typeof setTimeout> | null = null

  return (...args: Args): void => {
    if (timer !== null) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      fn(...args)
      timer = null
    }, delay)
  }
}

/**
 * Composable wrapper around `debounce` for use inside `<script setup>`.
 * Returns a debounced version of `fn`.
 *
 * @example
 * const debouncedSearch = useDebounce((query: string) => search(query), 300)
 */
export function useDebounce<Args extends unknown[], Return>(
  fn: (...args: Args) => Return,
  delay: number,
): (...args: Args) => void {
  return debounce(fn, delay)
}
