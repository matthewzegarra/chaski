/** axe-core check for Vitest/jsdom. Colour contrast is validated separately on the design
 * tokens (jsdom does not compute styles), so that rule is disabled here. */
import axe from 'axe-core'

export async function axeViolations(container: Element): Promise<string[]> {
  const results = await axe.run(container, {
    rules: { 'color-contrast': { enabled: false }, region: { enabled: false } },
  })
  return results.violations.map(
    (v) =>
      `${v.id} (${v.impact}): ${v.help} -> ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`,
  )
}
