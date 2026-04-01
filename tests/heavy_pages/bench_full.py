"""
Full benchmark: timing breakdown, interaction tests, and extreme scaling.

Tests:
1. Timing breakdown per page (navigate, DOM capture, serialize)
2. Can it click? Can it type? Can it read state?
3. Scaling: 1k → 10k → 50k → 100k → 500k → 1M elements
"""

import asyncio
import logging
import os
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Load env before imports
from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))
os.environ['TIMEOUT_BrowserStateRequestEvent'] = '300'

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
logger = logging.getLogger('bench')
logger.setLevel(logging.INFO)


# ─── Page generators ───────────────────────────────────────────────────────────

def gen_scaling_page(n: int) -> str:
    """Generate a page with N interactive elements via JS (fast generation)."""
    return f'''<html><head><title>Scale Test ({n:,} elements)</title></head>
<body>
<h1 id="title">Scale Test: {n:,} elements</h1>
<div id="click-target" onclick="this.textContent='CLICKED'" style="padding:10px;background:#eef;cursor:pointer;margin:10px 0;">Click me to verify interaction</div>
<input id="type-target" type="text" placeholder="Type here to verify" style="padding:8px;width:300px;margin:10px 0;" />
<div id="counter" style="margin:10px 0;">Elements loaded: 0</div>
<div id="bulk"></div>
<script>
const c = document.getElementById('bulk');
const frag = document.createDocumentFragment();
for (let i = 0; i < {n}; i++) {{
    const div = document.createElement('div');
    div.className = 'item';
    div.innerHTML = '<span>Item ' + i + '</span><input value="v' + i + '" /><button onclick="this.textContent=\\'ok\\'">btn-' + i + '</button>';
    frag.appendChild(div);
}}
c.appendChild(frag);
document.getElementById('counter').textContent = 'Elements loaded: ' + document.querySelectorAll('*').length;
</script>
</body></html>'''


def gen_interaction_page() -> str:
    """Page with specific elements to test click, type, read."""
    return '''<html><head><title>Interaction Test</title></head>
<body>
<h1>Interaction Test Page</h1>
<button id="btn1" onclick="document.getElementById('result').textContent='Button1 clicked'">Click Me</button>
<button id="btn2" onclick="document.getElementById('result').textContent='Button2 clicked'">Another Button</button>
<input id="search" type="text" placeholder="Search..." />
<input id="email" type="email" placeholder="Email..." />
<select id="dropdown">
  <option value="a">Option A</option>
  <option value="b">Option B</option>
  <option value="c">Option C</option>
</select>
<textarea id="notes" rows="4" cols="50" placeholder="Notes..."></textarea>
<div id="result" style="padding:10px;background:#ffe;margin:10px 0;">No action yet</div>
<div id="items"></div>
<script>
// Add 5000 items to make it moderately heavy
const c = document.getElementById('items');
const frag = document.createDocumentFragment();
for (let i = 0; i < 5000; i++) {
    const div = document.createElement('div');
    div.innerHTML = '<span>Row ' + i + '</span><input value="data-' + i + '" /><button>Edit</button>';
    div.addEventListener('click', () => {});
    frag.appendChild(div);
}
c.appendChild(frag);
</script>
</body></html>'''


# ─── Server ────────────────────────────────────────────────────────────────────

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_server(directory: str, port: int = 8766) -> HTTPServer:
    os.chdir(directory)
    server = HTTPServer(('127.0.0.1', port), QuietHandler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


# ─── Benchmarks ────────────────────────────────────────────────────────────────

async def bench_timing_breakdown(browser_session: BrowserSession, url: str, name: str) -> dict:
    """Detailed timing breakdown for a single page."""
    result = {'name': name, 'navigate_ms': 0, 'dom_capture_ms': 0,
              'total_ms': 0, 'element_count': 0, 'selector_map_size': 0,
              'error': None}

    try:
        t0 = time.time()

        # Navigate
        t_nav_start = time.time()
        page = await browser_session.get_current_page()
        cdp = await browser_session.get_or_create_cdp_session(focus=True)
        await cdp.cdp_client.send.Page.navigate(
            params={'url': url}, session_id=cdp.session_id
        )
        await asyncio.sleep(2.0)  # Wait for JS to execute
        t_nav_end = time.time()
        result['navigate_ms'] = (t_nav_end - t_nav_start) * 1000

        # Get element count
        try:
            count_r = await cdp.cdp_client.send.Runtime.evaluate(
                params={'expression': 'document.querySelectorAll("*").length', 'returnByValue': True},
                session_id=cdp.session_id,
            )
            result['element_count'] = count_r.get('result', {}).get('value', 0)
        except Exception:
            pass

        # DOM capture
        t_dom_start = time.time()
        state = await browser_session.get_browser_state_summary(cached=False)
        t_dom_end = time.time()
        result['dom_capture_ms'] = (t_dom_end - t_dom_start) * 1000

        if state and state.dom_state:
            result['selector_map_size'] = len(state.dom_state.selector_map)

        result['total_ms'] = (time.time() - t0) * 1000
    except Exception as e:
        result['error'] = str(e)[:120]
        result['total_ms'] = (time.time() - t0) * 1000

    return result


async def bench_interaction(browser_session: BrowserSession, url: str) -> dict:
    """Test click, type, and state reading on a page."""
    results = {'navigate': False, 'dom_capture': False, 'click': False,
               'type': False, 'read_state': False, 'errors': []}

    try:
        # Navigate
        cdp = await browser_session.get_or_create_cdp_session(focus=True)
        await cdp.cdp_client.send.Page.navigate(
            params={'url': url}, session_id=cdp.session_id
        )
        await asyncio.sleep(2.0)
        results['navigate'] = True

        # DOM capture
        state = await browser_session.get_browser_state_summary(cached=False)
        if state and state.dom_state and len(state.dom_state.selector_map) > 0:
            results['dom_capture'] = True
        else:
            results['errors'].append('DOM capture returned empty selector_map')

        # Find and click btn1
        btn_index = None
        for idx, node in (state.dom_state.selector_map if state and state.dom_state else {}).items():
            if node.attributes and node.attributes.get('id') == 'btn1':
                btn_index = idx
                break

        if btn_index is not None:
            try:
                from browser_use.browser.events import ClickElementEvent
                node = await browser_session.get_dom_element_by_index(btn_index)
                if node:
                    event = browser_session.event_bus.dispatch(ClickElementEvent(node=node))
                    await asyncio.wait_for(event, timeout=10.0)
                    results['click'] = True
            except Exception as e:
                results['errors'].append(f'Click failed: {e}')
        else:
            results['errors'].append('btn1 not found in selector_map')

        # Type into search input
        search_index = None
        for idx, node in (state.dom_state.selector_map if state and state.dom_state else {}).items():
            if node.attributes and node.attributes.get('id') == 'search':
                search_index = idx
                break

        if search_index is not None:
            try:
                # Click first, then type
                node = await browser_session.get_dom_element_by_index(search_index)
                if node:
                    click_event = browser_session.event_bus.dispatch(ClickElementEvent(node=node))
                    await asyncio.wait_for(click_event, timeout=10.0)

                    from browser_use.browser.events import TypeTextEvent
                    type_event = browser_session.event_bus.dispatch(TypeTextEvent(text='hello world'))
                    await asyncio.wait_for(type_event, timeout=10.0)
                    results['type'] = True
            except Exception as e:
                results['errors'].append(f'Type failed: {e}')
        else:
            results['errors'].append('search input not found in selector_map')

        # Read state after interactions
        try:
            read_result = await cdp.cdp_client.send.Runtime.evaluate(
                params={'expression': 'document.getElementById("result").textContent', 'returnByValue': True},
                session_id=cdp.session_id,
            )
            text = read_result.get('result', {}).get('value', '')
            if 'clicked' in text.lower():
                results['read_state'] = True
            else:
                results['errors'].append(f'Expected "clicked" in result div, got: {text}')
        except Exception as e:
            results['errors'].append(f'Read state failed: {e}')

    except Exception as e:
        results['errors'].append(f'Top-level error: {e}')

    return results


async def run_scaling_benchmark():
    """Test DOM capture at various scales: 1k → 1M elements."""
    scales = [1_000, 5_000, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]

    pages_dir = Path(__file__).parent / 'generated'
    pages_dir.mkdir(exist_ok=True)

    # Generate all pages
    for n in scales:
        html = gen_scaling_page(n)
        (pages_dir / f'scale_{n}.html').write_text(html)

    # Interaction page
    (pages_dir / 'interaction.html').write_text(gen_interaction_page())

    server = start_server(str(pages_dir))
    base = 'http://127.0.0.1:8766'

    # ── Part 1: Interaction test ──────────────────────────────────────────
    print('\n' + '=' * 80)
    print('PART 1: INTERACTION TEST (5k elements background)')
    print('=' * 80)

    session = BrowserSession(browser_profile=BrowserProfile(headless=True))
    await session.start()

    interaction_results = await bench_interaction(session, f'{base}/interaction.html')
    for test, passed in interaction_results.items():
        if test == 'errors':
            continue
        status = 'PASS' if passed else 'FAIL'
        print(f'  {test:<20} [{status}]')
    if interaction_results['errors']:
        for e in interaction_results['errors']:
            print(f'  ERROR: {e}')

    await session.kill()

    # ── Part 2: Scaling benchmark ─────────────────────────────────────────
    print('\n' + '=' * 80)
    print('PART 2: SCALING BENCHMARK')
    print('=' * 80)
    print(f'{"Scale":<12} {"Status":<8} {"Navigate":>10} {"DOM Capture":>13} {"Total":>10} {"Elements":>10} {"Selector":>10}')
    print('-' * 80)

    all_results = []
    for n in scales:
        url = f'{base}/scale_{n}.html'
        label = f'{n:,}'

        # Fresh browser for each extreme test to avoid state leaks
        session = BrowserSession(
            browser_profile=BrowserProfile(
                headless=True,
                cross_origin_iframes=False,
            ),
        )
        await session.start()

        result = await bench_timing_breakdown(session, url, label)
        all_results.append(result)

        status = 'PASS' if not result['error'] else 'FAIL'
        print(
            f'{label:<12} {status:<8} '
            f'{result["navigate_ms"]:>9.0f}ms '
            f'{result["dom_capture_ms"]:>12.0f}ms '
            f'{result["total_ms"]:>9.0f}ms '
            f'{result["element_count"]:>10,} '
            f'{result["selector_map_size"]:>10,}'
        )
        if result['error']:
            print(f'  ERROR: {result["error"]}')

        await session.kill()

    # Summary
    print('\n' + '=' * 80)
    print('SCALING ANALYSIS')
    print('=' * 80)
    for r in all_results:
        if r['element_count'] > 0 and r['dom_capture_ms'] > 0:
            per_element_us = (r['dom_capture_ms'] / r['element_count']) * 1000
            print(f'  {r["name"]:<12} → {per_element_us:.1f}µs/element, '
                  f'{r["dom_capture_ms"]:.0f}ms total DOM capture')
        elif r['error']:
            print(f'  {r["name"]:<12} → FAILED: {r["error"][:80]}')

    server.shutdown()


async def main():
    await run_scaling_benchmark()


if __name__ == '__main__':
    asyncio.run(main())
