/**
 * Debounce utilities.
 */

/**
 * Returns a debounced version of `fn` that delays invocation by `delay` ms.
 * The returned function has the same signature as `fn`.
 */
export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number,
): T {
  let timer: ReturnType<typeof setTimeout> | null = null

  const debounced = (...args: Parameters<T>): void => {
    if (timer !== null) {
      clearTimeout(timer)
    }
    timer = setTimeout(() => {
      fn(...args)
      timer = null
    }, delay)
  }

  return debounced as unknown as T
}

/**
 * Composable wrapper around `debounce` for use inside `<script setup>`.
 * Returns a debounced version of `fn`.
 *
 * @example
 * const debouncedSearch = useDebounce((query: string) => search(query), 300)
 */
export function useDebounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number,
): T {
  return debounce(fn, delay)
}
