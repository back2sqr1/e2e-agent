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


_CONTENT_JS = """
() => {
  const out = {headings: [], lists: [], text_blocks: []};
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const s = window.getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const sel = (el) => {
    if (el.id) return '#' + el.id;
    if (el.className && typeof el.className === 'string' && el.className.trim())
      return el.tagName.toLowerCase() + '.' + el.className.trim().split(/\\s+/).join('.');
    return el.tagName.toLowerCase();
  };
  const clean = (t) => t.trim().replace(/\\s+/g, ' ');
  for (const h of document.querySelectorAll('h1,h2,h3,h4')) {
    out.headings.push({selector: sel(h), text: clean(h.textContent).slice(0, 120), visible: isVisible(h)});
    if (out.headings.length >= 20) break;
  }
  for (const l of document.querySelectorAll('ul,ol')) {
    const items = [...l.querySelectorAll(':scope > li')].map(li => ({
      text: clean(li.textContent).slice(0, 120), visible: isVisible(li)
    }));
    if (items.length) out.lists.push({selector: sel(l), item_count: items.length, items: items.slice(0, 20)});
    if (out.lists.length >= 10) break;
  }
  for (const el of document.querySelectorAll('p,div,span,section,article,output,strong,td,dd')) {
    if (out.text_blocks.length >= 40) break;
    const direct = [...el.childNodes].filter(n => n.nodeType === 3)
      .map(n => n.textContent).join(' ').trim();
    if (direct.length < 3) continue;
    out.text_blocks.push({selector: sel(el), text: clean(el.textContent).slice(0, 160),
                          role: el.getAttribute('role'), visible: isVisible(el)});
  }
  return out;
}
"""


def _suggest_locator(el: dict) -> str:
    """Best-practice Playwright locator (TypeScript spelling) for an extracted element."""
    name = (el.get("name") or "").replace("'", "\\'")
    if el.get("test_id"):
        return f"page.getByTestId('{el['test_id']}')"
    if el.get("role") and name and len(name) <= 60:
        return f"page.getByRole('{el['role']}', {{ name: '{name}' }})"
    if el.get("placeholder"):
        ph = el["placeholder"].replace("'", "\\'")
        return f"page.getByPlaceholder('{ph}')"
    if el.get("id"):
        return f"page.locator('#{el['id']}')"
    if name and len(name) <= 60:
        return f"page.getByText('{name}', {{ exact: true }})"
    return f"page.locator('{el.get('tag', '*')}')  // WARNING: ambiguous, needs refinement"


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
            content = await page.evaluate(_CONTENT_JS)
            try:
                aria = await page.locator("body").aria_snapshot()
            except Exception:
                aria = None
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
        "aria_snapshot": aria[:8000] if aria else None,
        "elements": visible,
        "hidden_elements_omitted": hidden_count,
        "content": content,
        "iframes": frames,
        "note": "Locators are suggestions — validate the ones you plan to use with "
                "probe_locator. 'aria_snapshot' is the accessibility tree (role + "
                "accessible name per node) — the ground truth for get_by_role "
                "locators, exactly what the page offers to users. 'content' adds "
                "non-interactive structure (headings, lists and their items, text "
                "blocks); entries with visible: false exist in the DOM but are "
                "currently hidden (they will NOT appear in the aria snapshot).",
    }


async def probe_locator(url: str, strategy: str, value: str,
                        name: Optional[str] = None,
                        has_text: Optional[str] = None) -> dict:
    """Validate a candidate locator against the live page.

    Args:
        url: Page to open.
        strategy: One of 'css', 'role', 'text', 'label', 'placeholder',
            'test_id', 'alt_text', 'title'.
        value: The selector / role / text for the strategy.
        name: Accessible-name filter, only used with strategy='role'.
        has_text: Narrow to elements containing this text — equivalent to
            .filter(has_text=...), the idiomatic way to disambiguate
            (e.g. strategy='role', value='listitem', has_text='Backpack').
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
            if has_text:
                loc = loc.filter(has_text=has_text)
            count = await loc.count()
            result = {"strategy": strategy, "value": value, "name": name,
                      "has_text": has_text, "count": count}
            # Show what actually matched (up to 5) so an ambiguous locator
            # can be narrowed with a filter instead of guessed at.
            matches = []
            for i in range(min(count, 5)):
                nth = loc.nth(i)
                matches.append({
                    "tag": await nth.evaluate("el => el.tagName.toLowerCase()"),
                    "text": ((await nth.text_content()) or "")[:120].strip(),
                    "visible": await nth.is_visible(),
                    "enabled": await nth.is_enabled(),
                })
            if matches:
                result["matches"] = matches
            result["verdict"] = (
                "unique and usable" if count == 1
                else "NOT FOUND — this element does not exist on this page" if count == 0
                else f"AMBIGUOUS — matches {count} elements; narrow it with "
                     f"has_text or by scoping to a parent container")
            await browser.close()
            return result
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
