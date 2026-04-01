"""
Stress test: browser-use DOM capture on extremely heavy pages.

Creates 10 progressively heavier test pages (from 1k to 50k+ elements)
and verifies that DOM capture completes without crashing or timing out.

Usage:
    cd /Users/magnus/Developer/browser-use
    source .venv/bin/activate
    ANTHROPIC_API_KEY=... python tests/heavy_pages/test_heavy_dom.py

Or run non-interactively (no LLM, just DOM capture):
    python tests/heavy_pages/test_heavy_dom.py --dom-only
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

logger = logging.getLogger('heavy_page_test')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')

# ─── Page generators ───────────────────────────────────────────────────────────

def gen_page_flat_divs(n: int) -> str:
    """Page 1: N flat div elements with text and click handlers."""
    items = '\n'.join(
        f'<div class="item" onclick="this.style.background=\'red\'" data-id="{i}">'
        f'Item {i} <span>detail</span> <a href="#">link-{i}</a></div>'
        for i in range(n)
    )
    return f'<html><head><title>Flat Divs ({n})</title></head><body><h1>{n} flat divs</h1>{items}</body></html>'


def gen_page_nested_tables(rows: int, cols: int) -> str:
    """Page 2: Deep nested table with inputs in every cell."""
    cells_per_row = ''.join(
        f'<td><input type="text" name="cell_{r}_{c}" value="r{r}c{c}" />'
        f'<button onclick="alert({r})">btn</button></td>'
        for c in range(cols)
        for r in [0]  # placeholder, replaced below
    )
    header = '<tr>' + ''.join(f'<th>Col {c}</th>' for c in range(cols)) + '</tr>'
    body_rows = []
    for r in range(rows):
        cells = ''.join(
            f'<td><input type="text" name="cell_{r}_{c}" value="r{r}c{c}" />'
            f'<button onclick="alert({r})">btn-{r}-{c}</button></td>'
            for c in range(cols)
        )
        body_rows.append(f'<tr>{cells}</tr>')
    table = f'<table border="1">{header}{"".join(body_rows)}</table>'
    total = rows * cols * 3  # td + input + button per cell
    return f'<html><head><title>Nested Table ({rows}x{cols})</title></head><body><h1>Table {rows}x{cols} (~{total} elements)</h1>{table}</body></html>'


def gen_page_shadow_dom(n_hosts: int, children_per: int) -> str:
    """Page 3: Shadow DOM hosts each with children."""
    script = f'''
    <script>
    document.addEventListener('DOMContentLoaded', () => {{
        for (let i = 0; i < {n_hosts}; i++) {{
            const host = document.createElement('div');
            host.id = 'shadow-host-' + i;
            host.className = 'shadow-host';
            document.getElementById('container').appendChild(host);
            const shadow = host.attachShadow({{mode: 'open'}});
            shadow.innerHTML = '<style>:host {{ border: 1px solid #ccc; padding: 4px; margin: 2px; display: block; }}</style>';
            for (let j = 0; j < {children_per}; j++) {{
                const el = document.createElement('div');
                el.className = 'shadow-child';
                el.innerHTML = '<span>Shadow ' + i + '.' + j + '</span><button onclick="this.textContent=\\'clicked\\'">Click</button><input type="text" value="val-' + i + '-' + j + '" />';
                shadow.appendChild(el);
            }}
        }}
    }});
    </script>'''
    total = n_hosts * children_per * 4  # div + span + button + input per child
    return f'<html><head><title>Shadow DOM ({n_hosts}x{children_per})</title>{script}</head><body><h1>Shadow DOM ~{total} elements</h1><div id="container"></div></body></html>'


def gen_page_iframes(n_iframes: int, elements_per: int) -> str:
    """Page 4: Same-origin iframes each with many elements."""
    iframe_content = '<br>'.join(
        f'<div class="iframe-item"><a href="#">Link-{{i}}-{j}</a> '
        f'<input type="checkbox" id="cb-{{i}}-{j}" /><label for="cb-{{i}}-{j}">Label {j}</label></div>'
        for j in range(elements_per)
    )
    iframes = '\n'.join(
        f'<iframe srcdoc=\'<html><body><h2>Frame {i}</h2>{iframe_content.replace("{i}", str(i))}</body></html>\' '
        f'style="width:300px;height:200px;border:1px solid black;"></iframe>'
        for i in range(n_iframes)
    )
    total = n_iframes * elements_per * 4
    return f'<html><head><title>Iframes ({n_iframes}x{elements_per})</title></head><body><h1>{n_iframes} iframes ~{total} elements</h1><div>{iframes}</div></body></html>'


def gen_page_deep_nesting(depth: int, breadth: int) -> str:
    """Page 5: Deeply nested DOM tree."""
    def make_tree(d: int, b: int) -> str:
        if d <= 0:
            return f'<span class="leaf">Leaf d={d}</span>'
        children = ''.join(
            f'<div class="level-{d}" data-depth="{d}" data-branch="{i}">'
            f'<span>L{d}B{i}</span>{make_tree(d - 1, b)}</div>'
            for i in range(b)
        )
        return children

    # Limit recursion to avoid explosion — depth=8, breadth=3 gives ~6k nodes
    tree = make_tree(min(depth, 10), min(breadth, 3))
    return f'<html><head><title>Deep Nesting (d={depth}, b={breadth})</title></head><body><h1>Deep nesting</h1><div id="root">{tree}</div></body></html>'


def gen_page_forms_mega(n_fields: int) -> str:
    """Page 6: Giant form with diverse input types."""
    input_types = ['text', 'email', 'password', 'number', 'tel', 'url', 'date', 'time', 'color', 'range', 'checkbox', 'radio']
    fields = []
    for i in range(n_fields):
        t = input_types[i % len(input_types)]
        fields.append(
            f'<div class="form-group">'
            f'<label for="field-{i}">Field {i} ({t})</label>'
            f'<input type="{t}" id="field-{i}" name="field_{i}" placeholder="Enter {t}" />'
            f'</div>'
        )
    total = n_fields * 3  # div + label + input
    return (
        f'<html><head><title>Mega Form ({n_fields} fields)</title></head>'
        f'<body><h1>Form with {n_fields} fields (~{total} elements)</h1>'
        f'<form>{"".join(fields)}<button type="submit">Submit</button></form></body></html>'
    )


def gen_page_svg_heavy(n_shapes: int) -> str:
    """Page 7: Heavy SVG with many shapes + interactive overlays."""
    shapes = []
    for i in range(n_shapes):
        x = (i * 20) % 2000
        y = (i * 15) % 1500
        shapes.append(
            f'<circle cx="{x}" cy="{y}" r="8" fill="hsl({i % 360}, 70%, 50%)" '
            f'onclick="this.setAttribute(\'r\', 20)" />'
            f'<text x="{x+10}" y="{y}" font-size="8">{i}</text>'
        )
    svg = f'<svg width="2000" height="1500" xmlns="http://www.w3.org/2000/svg">{"".join(shapes)}</svg>'
    buttons = ''.join(f'<button id="btn-{i}" onclick="alert({i})">Action {i}</button>' for i in range(200))
    total = n_shapes * 2 + 200
    return (
        f'<html><head><title>SVG Heavy ({n_shapes} shapes)</title></head>'
        f'<body><h1>SVG + {n_shapes} shapes (~{total} elements)</h1>{svg}<div>{buttons}</div></body></html>'
    )


def gen_page_event_listeners(n: int) -> str:
    """Page 8: Elements with tons of JS event listeners."""
    script = f'''
    <script>
    document.addEventListener('DOMContentLoaded', () => {{
        const container = document.getElementById('listener-container');
        for (let i = 0; i < {n}; i++) {{
            const div = document.createElement('div');
            div.className = 'listener-item';
            div.innerHTML = '<span>Item ' + i + '</span><button>Btn ' + i + '</button>';
            div.addEventListener('click', () => {{}});
            div.addEventListener('mousedown', () => {{}});
            div.addEventListener('pointerdown', () => {{}});
            div.querySelector('button').addEventListener('click', (e) => {{ e.stopPropagation(); }});
            container.appendChild(div);
        }}
    }});
    </script>'''
    total = n * 3  # div + span + button, each with listeners
    return (
        f'<html><head><title>Event Listeners ({n})</title>{script}</head>'
        f'<body><h1>{n} elements with event listeners (~{total} DOM nodes)</h1>'
        f'<div id="listener-container"></div></body></html>'
    )


def gen_page_cross_origin_iframes(n: int) -> str:
    """Page 9: Cross-origin iframes (using real external sites) + heavy local content."""
    external_urls = [
        'https://example.com',
        'https://www.wikipedia.org',
        'https://httpbin.org/html',
    ]
    iframes = '\n'.join(
        f'<iframe src="{external_urls[i % len(external_urls)]}" '
        f'style="width:400px;height:300px;border:2px solid red;" '
        f'sandbox="allow-scripts"></iframe>'
        for i in range(min(n, 20))  # cap at 20 external iframes
    )
    # Add heavy local content around the iframes
    local_divs = '\n'.join(
        f'<div class="local" data-idx="{i}"><input type="text" value="local-{i}" />'
        f'<select><option>A</option><option>B</option><option>C</option></select></div>'
        for i in range(2000)
    )
    return (
        f'<html><head><title>Cross-Origin Iframes ({n})</title></head>'
        f'<body><h1>Cross-origin iframes + heavy local content</h1>'
        f'<div>{iframes}</div><div>{local_divs}</div></body></html>'
    )


def gen_page_ultimate_stress() -> str:
    """Page 10: The ultimate stress test — everything combined."""
    # Shadow DOM section
    shadow_script = '''
    <script>
    document.addEventListener('DOMContentLoaded', () => {
        // Shadow DOM hosts
        const shadowContainer = document.getElementById('shadow-section');
        for (let i = 0; i < 100; i++) {
            const host = document.createElement('div');
            host.className = 'shadow-host';
            shadowContainer.appendChild(host);
            const shadow = host.attachShadow({mode: 'open'});
            let html = '<style>.inner { padding: 2px; }</style>';
            for (let j = 0; j < 30; j++) {
                html += '<div class="inner"><input type="text" value="s' + i + '.' + j + '" /><button>Go</button></div>';
            }
            shadow.innerHTML = html;
        }

        // Event listener section
        const listenerContainer = document.getElementById('listener-section');
        for (let i = 0; i < 3000; i++) {
            const div = document.createElement('div');
            div.innerHTML = '<span>EL-' + i + '</span><a href="#" onclick="return false">link</a>';
            div.addEventListener('click', () => {});
            div.addEventListener('pointerdown', () => {});
            listenerContainer.appendChild(div);
        }
    });
    </script>'''

    # Table section
    table_rows = []
    for r in range(200):
        cells = ''.join(
            f'<td><input name="t_{r}_{c}" value="{r}-{c}" /><button>X</button></td>'
            for c in range(10)
        )
        table_rows.append(f'<tr>{cells}</tr>')
    table = f'<table border="1">{"".join(table_rows)}</table>'

    # Form section
    form_fields = ''.join(
        f'<div><label for="uf-{i}">Field {i}</label>'
        f'<input type="{["text","email","number","date","tel","url","color"][i%7]}" id="uf-{i}" /></div>'
        for i in range(500)
    )

    # Same-origin iframes
    iframe_content = '<br>'.join(f'<div>iframe-item-{j}<input value="{j}" /></div>' for j in range(50))
    iframes = '\n'.join(
        f'<iframe srcdoc=\'<html><body>{iframe_content}</body></html>\' '
        f'style="width:250px;height:150px;border:1px solid blue;"></iframe>'
        for i in range(15)
    )

    # SVG
    svg_shapes = ''.join(
        f'<rect x="{(i*12)%1000}" y="{(i*8)%500}" width="10" height="10" fill="hsl({i%360},50%,50%)" />'
        for i in range(500)
    )
    svg = f'<svg width="1000" height="500">{svg_shapes}</svg>'

    # Deeply nested section
    def nested(d: int) -> str:
        if d <= 0:
            return '<span class="leaf">*</span>'
        return ''.join(f'<div class="n-{d}">{nested(d-1)}</div>' for _ in range(3))
    deep = nested(7)

    return (
        f'<html><head><title>ULTIMATE STRESS TEST</title>{shadow_script}</head>'
        f'<body>'
        f'<h1>Ultimate Stress Test (~50k+ elements)</h1>'
        f'<section id="table-section"><h2>Tables</h2>{table}</section>'
        f'<section id="form-section"><h2>Forms</h2><form>{form_fields}</form></section>'
        f'<section id="shadow-section"><h2>Shadow DOM</h2></section>'
        f'<section id="listener-section"><h2>Event Listeners</h2></section>'
        f'<section id="iframe-section"><h2>Iframes</h2>{iframes}</section>'
        f'<section id="svg-section"><h2>SVG</h2>{svg}</section>'
        f'<section id="deep-section"><h2>Deep Nesting</h2>{deep}</section>'
        f'</body></html>'
    )


# ─── Test pages registry ──────────────────────────────────────────────────────

TEST_PAGES = [
    ('01_flat_divs_1k',       lambda: gen_page_flat_divs(1000)),
    ('02_table_100x10',       lambda: gen_page_nested_tables(100, 10)),
    ('03_shadow_dom_200x10',  lambda: gen_page_shadow_dom(200, 10)),
    ('04_iframes_20x50',      lambda: gen_page_iframes(20, 50)),
    ('05_deep_nesting_8x3',   lambda: gen_page_deep_nesting(8, 3)),
    ('06_mega_form_2000',     lambda: gen_page_forms_mega(2000)),
    ('07_svg_5000',           lambda: gen_page_svg_heavy(5000)),
    ('08_event_listeners_5k', lambda: gen_page_event_listeners(5000)),
    ('09_cross_origin',       lambda: gen_page_cross_origin_iframes(10)),
    ('10_ultimate_stress',    lambda: gen_page_ultimate_stress()),
]


# ─── Local HTTP server ────────────────────────────────────────────────────────

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress request logging


def start_server(directory: str, port: int = 8765) -> HTTPServer:
    os.chdir(directory)
    server = HTTPServer(('127.0.0.1', port), QuietHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


# ─── Test runner ───────────────────────────────────────────────────────────────

async def test_dom_capture(page_url: str, page_name: str, browser_session: BrowserSession) -> dict:
    """Test DOM capture on a single page. Returns timing info."""
    result = {
        'name': page_name,
        'url': page_url,
        'success': False,
        'error': None,
        'time_ms': 0,
        'element_count': 0,
        'selector_map_size': 0,
    }

    try:
        start = time.time()

        # Navigate to the page
        page = await browser_session.get_current_page()
        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
        await cdp_session.cdp_client.send.Page.navigate(
            params={'url': page_url}, session_id=cdp_session.session_id
        )
        # Wait for page load
        await asyncio.sleep(2.0)

        # Get browser state (this is the operation that times out on heavy pages)
        state = await browser_session.get_browser_state_summary(cached=False)

        elapsed_ms = (time.time() - start) * 1000
        result['time_ms'] = elapsed_ms
        result['success'] = True

        if state and state.dom_state:
            result['selector_map_size'] = len(state.dom_state.selector_map)

        # Get element count from page
        try:
            count_result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={'expression': 'document.querySelectorAll("*").length', 'returnByValue': True},
                session_id=cdp_session.session_id,
            )
            result['element_count'] = count_result.get('result', {}).get('value', 0)
        except Exception:
            pass

    except Exception as e:
        result['error'] = str(e)
        result['time_ms'] = (time.time() - start) * 1000

    return result


async def test_agent_interaction(page_url: str, page_name: str) -> dict:
    """Test full agent interaction on a page (requires LLM API key)."""
    from browser_use import Agent

    llm = None
    try:
        from browser_use.llm.anthropic.chat import ChatAnthropic
        llm = ChatAnthropic(model='claude-sonnet-4-20250514', max_tokens=1024)
    except Exception as e:
        logger.warning(f'Failed to init ChatAnthropic: {e}')
    if llm is None:
        try:
            from browser_use.llm.openai.chat import ChatOpenAI
            llm = ChatOpenAI(model='gpt-4o-mini')
        except Exception as e:
            logger.warning(f'Failed to init ChatOpenAI: {e}')
    if llm is None:
        return {'name': page_name, 'success': False, 'error': 'No LLM API key found (set ANTHROPIC_API_KEY or OPENAI_API_KEY)', 'time_ms': 0, 'steps': 0}

    result = {'name': page_name, 'success': False, 'error': None, 'time_ms': 0, 'steps': 0}

    browser_session = BrowserSession(
        browser_profile=BrowserProfile(headless=True),
    )

    start = time.time()
    try:
        await browser_session.start()

        agent = Agent(
            task=f'Navigate to {page_url} and tell me the title of the page and how many interactive elements you can see. Just report the count, do not click anything.',
            llm=llm,
            browser_session=browser_session,
            max_steps=3,
        )
        history = await agent.run()
        result['time_ms'] = (time.time() - start) * 1000
        result['success'] = True
        result['steps'] = len(history.history) if history else 0
    except Exception as e:
        result['error'] = str(e)
        result['time_ms'] = (time.time() - start) * 1000
    finally:
        await browser_session.kill()

    return result


async def run_dom_only_tests():
    """Run DOM capture tests (no LLM needed)."""
    # Generate HTML files
    pages_dir = Path(__file__).parent / 'generated'
    pages_dir.mkdir(exist_ok=True)

    logger.info('Generating test pages...')
    for name, generator in TEST_PAGES:
        html = generator()
        (pages_dir / f'{name}.html').write_text(html)
        logger.info(f'  Generated {name}.html ({len(html):,} bytes)')

    # Start local server
    server = start_server(str(pages_dir))
    logger.info(f'Local server running on http://127.0.0.1:8765')

    # Create browser session
    browser_session = BrowserSession(
        browser_profile=BrowserProfile(
            headless=True,
            cross_origin_iframes=True,
            max_iframes=100,
            max_iframe_depth=5,
        ),
    )
    await browser_session.start()

    results = []
    try:
        for name, _ in TEST_PAGES:
            url = f'http://127.0.0.1:8765/{name}.html'
            logger.info(f'\n{"="*60}')
            logger.info(f'Testing: {name}')
            logger.info(f'{"="*60}')

            result = await test_dom_capture(url, name, browser_session)
            results.append(result)

            status = 'PASS' if result['success'] else 'FAIL'
            logger.info(
                f'  [{status}] {name}: {result["time_ms"]:.0f}ms, '
                f'{result["element_count"]} elements, '
                f'{result["selector_map_size"]} in selector_map'
            )
            if result['error']:
                logger.error(f'  Error: {result["error"]}')

    finally:
        await browser_session.kill()
        server.shutdown()

    # Summary
    print('\n' + '=' * 70)
    print('RESULTS SUMMARY')
    print('=' * 70)
    print(f'{"Page":<30} {"Status":<8} {"Time":>8} {"Elements":>10} {"Selector":>10}')
    print('-' * 70)
    passed = 0
    failed = 0
    for r in results:
        status = 'PASS' if r['success'] else 'FAIL'
        if r['success']:
            passed += 1
        else:
            failed += 1
        print(
            f'{r["name"]:<30} {status:<8} {r["time_ms"]:>7.0f}ms '
            f'{r["element_count"]:>10} {r["selector_map_size"]:>10}'
        )
        if r['error']:
            print(f'  ERROR: {r["error"][:80]}')
    print('-' * 70)
    print(f'Total: {passed} passed, {failed} failed out of {len(results)}')

    return failed == 0


async def run_agent_tests():
    """Run full agent tests (requires LLM API key)."""
    # Generate HTML files
    pages_dir = Path(__file__).parent / 'generated'
    pages_dir.mkdir(exist_ok=True)

    logger.info('Generating test pages...')
    for name, generator in TEST_PAGES:
        html = generator()
        (pages_dir / f'{name}.html').write_text(html)

    # Start local server
    server = start_server(str(pages_dir))
    logger.info(f'Local server running on http://127.0.0.1:8765')

    # Only test a subset with the agent (it's slow)
    agent_test_pages = [
        TEST_PAGES[0],   # flat divs (light)
        TEST_PAGES[5],   # mega form (medium)
        TEST_PAGES[7],   # event listeners (heavy)
        TEST_PAGES[9],   # ultimate stress (extreme)
    ]

    results = []
    for name, _ in agent_test_pages:
        url = f'http://127.0.0.1:8765/{name}.html'
        logger.info(f'\nAgent test: {name}')
        result = await test_agent_interaction(url, name)
        results.append(result)
        status = 'PASS' if result['success'] else 'FAIL'
        logger.info(f'  [{status}] {result["time_ms"]:.0f}ms')
        if result['error']:
            logger.error(f'  Error: {result["error"]}')

    server.shutdown()

    print('\n' + '=' * 70)
    print('AGENT TEST RESULTS')
    print('=' * 70)
    for r in results:
        status = 'PASS' if r['success'] else 'FAIL'
        print(f'  [{status}] {r["name"]}: {r["time_ms"]:.0f}ms')
        if r['error']:
            print(f'    Error: {r["error"][:100]}')

    return all(r['success'] for r in results)


def main():
    parser = argparse.ArgumentParser(description='Heavy page DOM capture stress test')
    parser.add_argument('--dom-only', action='store_true', help='Only test DOM capture (no LLM needed)')
    parser.add_argument('--agent', action='store_true', help='Run full agent tests (needs API key)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable debug logging')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        # Also enable browser-use logging
        logging.getLogger('browser_use').setLevel(logging.DEBUG)
    else:
        # Suppress noisy loggers but keep warnings
        logging.getLogger('browser_use').setLevel(logging.WARNING)

    # Load env from cloud backend if available
    cloud_env = Path('/Users/magnus/Developer/cloud/backend/.env')
    if cloud_env.exists():
        from dotenv import load_dotenv
        load_dotenv(cloud_env)
        logger.info('Loaded API keys from cloud backend .env')

    if args.dom_only or (not args.agent):
        success = asyncio.run(run_dom_only_tests())
    else:
        success = asyncio.run(run_agent_tests())

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
