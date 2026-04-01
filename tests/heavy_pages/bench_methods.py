"""
Benchmark: raw CDP operations + pipeline stages on extreme pages.

Tests each operation DIRECTLY via CDP (bypassing event bus timeouts)
to measure what Chrome can actually do vs what browser-use's pipeline adds.
"""

import asyncio
import json
import logging
import os
import sys
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))
os.environ['TIMEOUT_BrowserStateRequestEvent'] = '600'

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')
logger = logging.getLogger('bench')
logger.setLevel(logging.INFO)


def gen_page(n):
    return f'''<html><head><title>Bench {n:,}</title></head>
<body>
<h1 id="title">Bench: {n:,} elements</h1>
<div id="click-target" style="padding:20px;background:#eef;cursor:pointer;font-size:18px"
     onclick="this.textContent='CLICKED OK'">CLICK ME</div>
<input id="type-target" type="text" value="" style="padding:10px;width:300px" />
<div id="result">waiting</div>
<div id="bulk"></div>
<script>
const frag=document.createDocumentFragment();
for(let i=0;i<{n};i++){{const d=document.createElement('div');d.className='item';
d.innerHTML='<span>'+i+'</span><input value=v'+i+' /><button>X</button>';frag.appendChild(d)}}
document.getElementById('bulk').appendChild(frag);
document.getElementById('result').textContent='loaded '+document.querySelectorAll('*').length;
</script></body></html>'''


class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def serve(d, port=8767):
    os.chdir(d)
    s = HTTPServer(('127.0.0.1', port), Q)
    Thread(target=s.serve_forever, daemon=True).start()
    return s


async def timed(coro, timeout=120):
    t0 = time.time()
    try:
        r = await asyncio.wait_for(coro, timeout=timeout)
        return r, (time.time()-t0)*1000, None
    except Exception as e:
        return None, (time.time()-t0)*1000, type(e).__name__+': '+str(e)[:100]


async def bench_one(n, base_url):
    """Benchmark a single page scale. Fresh browser per scale."""
    session = BrowserSession(browser_profile=BrowserProfile(headless=True, cross_origin_iframes=False))
    await session.start()

    try:
        cdp = await session.get_or_create_cdp_session(focus=True)
        sid = cdp.session_id
        send = cdp.cdp_client.send

        # Navigate + wait for JS
        t0 = time.time()
        await send.Page.navigate(params={'url': f'{base_url}/bench_{n}.html'}, session_id=sid)
        await asyncio.sleep(3.0)
        nav_ms = (time.time()-t0)*1000

        # Element count
        r = await send.Runtime.evaluate(params={'expression':'document.querySelectorAll("*").length','returnByValue':True}, session_id=sid)
        elems = r.get('result',{}).get('value',0)

        rows = []
        rows.append(('Navigate + 3s wait', nav_ms, None, f'{elems:,} elements'))

        # ── Raw CDP operations (no browser-use overhead) ──

        # 1. Screenshot
        async def do_screenshot():
            r = await send.Page.captureScreenshot(params={'format':'png','quality':80}, session_id=sid)
            return len(r.get('data',''))
        r, ms, err = await timed(do_screenshot())
        rows.append(('Screenshot (raw CDP)', ms, err, f'{r:,}B' if r else ''))

        # 2. JS eval simple
        async def do_js():
            r = await send.Runtime.evaluate(params={'expression':'document.title','returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value','')
        r, ms, err = await timed(do_js())
        rows.append(('JS eval (title)', ms, err, ''))

        # 3. JS click
        async def do_click():
            r = await send.Runtime.evaluate(params={
                'expression':'document.getElementById("click-target").click(); document.getElementById("click-target").textContent',
                'returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value','')
        r, ms, err = await timed(do_click())
        rows.append(('JS click', ms, err, f'"{r}"' if r else ''))

        # 4. JS type
        async def do_type():
            r = await send.Runtime.evaluate(params={
                'expression':'const e=document.getElementById("type-target");e.focus();e.value="hello";e.value',
                'returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value','')
        r, ms, err = await timed(do_type())
        rows.append(('JS type', ms, err, f'"{r}"' if r else ''))

        # 5. JS get HTML length
        async def do_html_len():
            r = await send.Runtime.evaluate(params={
                'expression':'document.documentElement.outerHTML.length','returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value',0)
        r, ms, err = await timed(do_html_len())
        rows.append(('JS HTML length', ms, err, f'{r:,} chars' if r else ''))

        # 6. CDP raw mouse click
        async def do_mouse():
            await send.Runtime.evaluate(params={'expression':'document.getElementById("click-target").textContent="CLICK ME"'}, session_id=sid)
            await send.Input.dispatchMouseEvent(params={'type':'mousePressed','x':200,'y':80,'button':'left','clickCount':1}, session_id=sid)
            await send.Input.dispatchMouseEvent(params={'type':'mouseReleased','x':200,'y':80,'button':'left','clickCount':1}, session_id=sid)
            r = await send.Runtime.evaluate(params={'expression':'document.getElementById("click-target").textContent','returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value','')
        r, ms, err = await timed(do_mouse())
        rows.append(('CDP mouse click', ms, err, f'"{r}"' if r else ''))

        # 7. CDP keyboard
        async def do_kb():
            await send.Runtime.evaluate(params={'expression':'document.getElementById("type-target").focus();document.getElementById("type-target").value=""'}, session_id=sid)
            for ch in 'test':
                await send.Input.dispatchKeyEvent(params={'type':'keyDown','text':ch,'key':ch}, session_id=sid)
                await send.Input.dispatchKeyEvent(params={'type':'keyUp','key':ch}, session_id=sid)
            r = await send.Runtime.evaluate(params={'expression':'document.getElementById("type-target").value','returnByValue':True}, session_id=sid)
            return r.get('result',{}).get('value','')
        r, ms, err = await timed(do_kb())
        rows.append(('CDP keyboard type', ms, err, f'"{r}"' if r else ''))

        # ── Raw CDP data fetches (what the pipeline calls internally) ──

        # 8. DOM.getDocument
        async def do_dom():
            r = await send.DOM.getDocument(params={'depth':-1,'pierce':True}, session_id=sid)
            return len(json.dumps(r))
        r, ms, err = await timed(do_dom(), timeout=120)
        rows.append(('DOM.getDocument', ms, err, f'{r/1e6:.1f}MB' if r else ''))

        # 9. DOMSnapshot
        async def do_snap():
            r = await send.DOMSnapshot.captureSnapshot(params={
                'computedStyles':['display','visibility','opacity'],
                'includePaintOrder':True,'includeDOMRects':True,
                'includeBlendedBackgroundColors':False,'includeTextColorOpacities':False}, session_id=sid)
            nodes = sum(len(d.get('nodes',{}).get('nodeName',[])) for d in r.get('documents',[]))
            return nodes, len(json.dumps(r))
        r, ms, err = await timed(do_snap(), timeout=120)
        rows.append(('DOMSnapshot.capture', ms, err, f'{r[0]:,} nodes, {r[1]/1e6:.1f}MB' if r else ''))

        # 10. Accessibility tree
        async def do_ax():
            r = await send.Accessibility.getFullAXTree(params={}, session_id=sid)
            return len(r.get('nodes',[]))
        r, ms, err = await timed(do_ax(), timeout=120)
        rows.append(('Accessibility.getFull', ms, err, f'{r:,} AX nodes' if r else ''))

        # ── Full browser-use pipeline ──

        # 11. Full capture
        async def do_full():
            state = await session.get_browser_state_summary(cached=False)
            return len(state.dom_state.selector_map) if state and state.dom_state else 0
        r, ms, err = await timed(do_full(), timeout=300)
        rows.append(('FULL pipeline', ms, err, f'{r:,} selectors' if r is not None else ''))

        return n, elems, rows

    finally:
        await session.kill()


async def main():
    pages_dir = Path(__file__).parent / 'generated'
    pages_dir.mkdir(exist_ok=True)

    scales = [10_000, 50_000, 100_000, 500_000, 1_000_000]
    for s in scales:
        (pages_dir / f'bench_{s}.html').write_text(gen_page(s))

    server = serve(str(pages_dir))

    all_results = []
    for n in scales:
        print(f'\n{"="*90}')
        print(f'  {n:>12,} target elements')
        print(f'{"="*90}')
        try:
            n_actual, elems, rows = await bench_one(n, 'http://127.0.0.1:8767')
            all_results.append((n, elems, rows))
            for label, ms, err, detail in rows:
                status = 'PASS' if not err else 'FAIL'
                ms_str = f'{ms:>10.0f}ms' if ms < 100000 else f'{ms/1000:>9.1f}s '
                print(f'  {label:<28} {ms_str}  {status:<6} {detail}')
                if err:
                    print(f'    → {err}')
        except Exception as e:
            print(f'  FATAL: {e}')
            all_results.append((n, 0, []))

    # ── Summary table ──
    print('\n\n' + '='*130)
    print('TIMING SUMMARY (ms)')
    print('='*130)

    # Build method list from first result that has data
    method_names = []
    for _, _, rows in all_results:
        if rows:
            method_names = [r[0] for r in rows]
            break

    header = f'{"Operation":<28}' + ''.join(f'  {n:>12,}' for n, _, _ in all_results)
    print(header)
    print('-'*130)

    for i, mname in enumerate(method_names):
        line = f'{mname:<28}'
        for _, _, rows in all_results:
            if i < len(rows):
                _, ms, err, _ = rows[i]
                if err:
                    line += f'  {"FAIL":>12}'
                elif ms < 100000:
                    line += f'  {ms:>11.0f}ms'
                else:
                    line += f'  {ms/1000:>10.1f}s '
            else:
                line += f'  {"—":>12}'
        print(line)

    # ── What works at each scale ──
    print('\n' + '='*130)
    print('WHAT WORKS AT EACH SCALE')
    print('='*130)
    for n, elems, rows in all_results:
        working = [r[0] for r in rows if not r[2]]
        broken = [r[0] for r in rows if r[2]]
        print(f'\n  {n:>10,} elements ({elems:,} DOM nodes):')
        if working:
            print(f'    ✓ {", ".join(working)}')
        if broken:
            print(f'    ✗ {", ".join(broken)}')

    server.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
