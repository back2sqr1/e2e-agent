"""Skills for the locator agent: inspect live pages and validate locators."""

from typing import Optional

from playwright.async_api import async_playwright

from ..config import ACTION_TIMEOUT_MS, HEADLESS

_EXTRACT_JS = """
() => {
  const seen = new Set();
  const out = [];
  const nodes = document.querySelectorAll(
    'a, button, input, select, textarea, [role], [onclick], [data-testid], [contenteditable="true"], summary, label'
  );
  const implicitRole = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a' && el.hasAttribute('href')) return 'link';
    if (tag === 'button') return 'button';
    if (tag === 'select') return 'combobox';
    if (tag === 'textarea') return 'textbox';
    if (tag === 'summary') return 'button';
    if (tag === 'input') {
      const t = (el.getAttribute('type') || 'text').toLowerCase();
      return {checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton',
              search: 'searchbox', button: 'button', submit: 'button', reset: 'button',
              email: 'textbox', password: 'textbox', tel: 'textbox', url: 'textbox',
              text: 'textbox'}[t] || t;
    }
    return null;
  };
  const accName = (el) => {
    const aria = el.getAttribute('aria-label');
    if (aria) return aria;
    const labelledBy = el.getAttribute('aria-labelledby');
    if (labelledBy) {
      const t = labelledBy.split(/\\s+/).map(id => document.getElementById(id)?.textContent || '').join(' ').trim();
      if (t) return t;
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) return lab.textContent.trim();
    }
    const closestLabel = el.closest('label');
    if (closestLabel) return closestLabel.textContent.trim();
    if (el.tagName === 'INPUT' && (el.type === 'submit' || el.type === 'button')) return el.value;
    return (el.textContent || '').trim().replace(/\\s+/g, ' ');
  };
  for (const el of nodes) {
    if (seen.has(el)) continue;
    seen.add(el);
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    const visible = rect.width > 0 && rect.height > 0 &&
                    style.visibility !== 'hidden' && style.display !== 'none';
    out.push({
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || implicitRole(el),
      name: accName(el).slice(0, 80),
      id: el.id || null,
      test_id: el.getAttribute('data-testid') || el.getAttribute('data-test-id') || el.getAttribute('data-test') || null,
      placeholder: el.getAttribute('placeholder') || null,
      type: el.getAttribute('type') || null,
      href: el.tagName === 'A' ? (el.getAttribute('href') || '').slice(0, 100) : null,
      classes: (el.className && typeof el.className === 'string') ? el.className.slice(0, 80) : null,
      visible,
    });
    if (out.length >= 150) break;
  }
  return out;
}
"""


def _suggest_locator(el: dict) -> str:
    """Best-practice Playwright locator for an extracted element, as code."""
    name = (el.get("name") or "").replace('"', '\\"')
    if el.get("test_id"):
        return f'page.get_by_test_id("{el["test_id"]}")'
    if el.get("role") and name and len(name) <= 60:
        return f'page.get_by_role("{el["role"]}", name="{name}")'
    if el.get("placeholder"):
        ph = el["placeholder"].replace('"', '\\"')
        return f'page.get_by_placeholder("{ph}")'
    if el.get("id"):
        return f'page.locator("#{el["id"]}")'
    if name and len(name) <= 60:
        return f'page.get_by_text("{name}", exact=True)'
    return f'page.locator("{el.get("tag", "*")}")  # WARNING: ambiguous, needs refinement'


async def _open(pw, url: str):
    browser = await pw.chromium.launch(headless=HEADLESS)
    page = await browser.new_page(viewport={"width": 1280, "height": 720})
    page.set_default_timeout(ACTION_TIMEOUT_MS)
    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass  # busy pages never go idle; proceed with what we have
    return browser, page


async def inspect_page(url: str) -> dict:
    """Open a URL in a real browser and list its interactive elements.

    Returns every visible button, link, input, select, and ARIA widget on
    the page, each with a ready-to-use suggested Playwright locator.

    Args:
        url: Full URL to inspect (http(s):// or file://).
    """
    try:
        async with async_playwright() as pw:
            browser, page = await _open(pw, url)
            title = await page.title()
            elements = await page.evaluate(_EXTRACT_JS)
            frames = [f.url for f in page.frames if f != page.main_frame][:10]
            await browser.close()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    for el in elements:
        el["suggested_locator"] = _suggest_locator(el)
    visible = [el for el in elements if el["visible"]]
    hidden_count = len(elements) - len(visible)
    return {
        "url": url,
        "title": title,
        "elements": visible,
        "hidden_elements_omitted": hidden_count,
        "iframes": frames,
        "note": "Locators are suggestions — validate the ones you plan to use with probe_locator.",
    }


async def probe_locator(url: str, strategy: str, value: str,
                        name: Optional[str] = None) -> dict:
    """Validate a candidate locator against the live page.

    Args:
        url: Page to open.
        strategy: One of 'css', 'role', 'text', 'label', 'placeholder',
            'test_id', 'alt_text', 'title'.
        value: The selector / role / text for the strategy.
        name: Accessible-name filter, only used with strategy='role'.
    """
    try:
        async with async_playwright() as pw:
            browser, page = await _open(pw, url)
            builders = {
                "css": lambda: page.locator(value),
                "role": lambda: page.get_by_role(value, name=name) if name else page.get_by_role(value),
                "text": lambda: page.get_by_text(value),
                "label": lambda: page.get_by_label(value),
                "placeholder": lambda: page.get_by_placeholder(value),
                "test_id": lambda: page.get_by_test_id(value),
                "alt_text": lambda: page.get_by_alt_text(value),
                "title": lambda: page.get_by_title(value),
            }
            if strategy not in builders:
                await browser.close()
                return {"error": f"unknown strategy '{strategy}', use one of {sorted(builders)}"}
            loc = builders[strategy]()
            count = await loc.count()
            result = {"strategy": strategy, "value": value, "name": name, "count": count}
            if count > 0:
                first = loc.first
                result["first_match"] = {
                    "tag": await first.evaluate("el => el.tagName.toLowerCase()"),
                    "text": ((await first.text_content()) or "")[:120].strip(),
                    "visible": await first.is_visible(),
                    "enabled": await first.is_enabled(),
                }
            result["verdict"] = ("unique and usable" if count == 1
                                 else "NOT FOUND — wrong locator" if count == 0
                                 else f"AMBIGUOUS — matches {count} elements, needs narrowing")
            await browser.close()
            return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
