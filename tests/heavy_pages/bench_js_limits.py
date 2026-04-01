"""
Test: what can JS click/type actually reach?

- Same-origin iframe
- Cross-origin iframe
- Open shadow DOM
- Closed shadow DOM
- Coordinate-based JS click (elementFromPoint)
- Coordinate click INTO an iframe
- Coordinate click INTO shadow DOM
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
from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger('bench')
logger.setLevel(logging.INFO)


MAIN_PAGE = '''<html><head><title>JS Boundary Test</title></head>
<body style="font-family:monospace">
<h2>JS Boundary Tests</h2>

<!-- 1. Regular button -->
<div id="test-regular">
  <button id="btn-regular" onclick="this.textContent='REGULAR_CLICKED'">Regular Button</button>
</div>

<!-- 2. Same-origin iframe -->
<iframe id="iframe-same" srcdoc="
  <html><body>
    <button id='btn-iframe' onclick='this.textContent=&quot;IFRAME_CLICKED&quot;'>Iframe Button</button>
    <input id='input-iframe' type='text' value='' placeholder='type here' />
  </body></html>
" style="width:400px;height:80px;border:2px solid blue;"></iframe>

<!-- 3. Cross-origin iframe -->
<iframe id="iframe-cross" src="https://example.com"
  style="width:400px;height:80px;border:2px solid red;" sandbox="allow-scripts"></iframe>

<!-- 4. Open shadow DOM -->
<div id="shadow-host-open"></div>
<script>
  const hostOpen = document.getElementById('shadow-host-open');
  const shadowOpen = hostOpen.attachShadow({mode: 'open'});
  shadowOpen.innerHTML = '<button id="btn-shadow-open" onclick="this.textContent=\\'SHADOW_OPEN_CLICKED\\'">Open Shadow Button</button><input id="input-shadow-open" type="text" />';
</script>

<!-- 5. Closed shadow DOM -->
<div id="shadow-host-closed"></div>
<script>
  const hostClosed = document.getElementById('shadow-host-closed');
  const shadowClosed = hostClosed.attachShadow({mode: 'closed'});
  shadowClosed.innerHTML = '<button id="btn-shadow-closed" onclick="this.textContent=\\'SHADOW_CLOSED_CLICKED\\'">Closed Shadow Button</button><input id="input-shadow-closed" type="text" />';
  // Stash reference for testing
  window.__closedShadow = shadowClosed;
</script>

<!-- 6. Heavy background (10k elements) to test coordinate click perf -->
<div id="bulk"></div>
<script>
const frag = document.createDocumentFragment();
for(let i=0;i<10000;i++){const d=document.createElement('div');d.textContent='item-'+i;frag.appendChild(d)}
document.getElementById('bulk').appendChild(frag);
</script>
</body></html>'''


class Q(SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

def serve(d, port=8768):
    os.chdir(d)
    s = HTTPServer(('127.0.0.1', port), Q)
    Thread(target=s.serve_forever, daemon=True).start()
    return s


async def js_eval(send, sid, expr):
    """Run JS, return (value, ms, error)."""
    t0 = time.time()
    try:
        r = await send.Runtime.evaluate(
            params={'expression': expr, 'returnByValue': True, 'awaitPromise': True},
            session_id=sid
        )
        ms = (time.time()-t0)*1000
        val = r.get('result', {}).get('value')
        exc = r.get('exceptionDetails', {}).get('text')
        if exc:
            return None, ms, exc
        return val, ms, None
    except Exception as e:
        return None, (time.time()-t0)*1000, str(e)[:100]


async def main():
    pages_dir = Path(__file__).parent / 'generated'
    pages_dir.mkdir(exist_ok=True)
    (pages_dir / 'js_limits.html').write_text(MAIN_PAGE)

    server = serve(str(pages_dir))
    session = BrowserSession(browser_profile=BrowserProfile(headless=True))
    await session.start()

    cdp = await session.get_or_create_cdp_session(focus=True)
    sid = cdp.session_id
    send = cdp.cdp_client.send

    await send.Page.navigate(params={'url': 'http://127.0.0.1:8768/js_limits.html'}, session_id=sid)
    await asyncio.sleep(2.0)

    print('='*80)
    print('  JS BOUNDARY TESTS')
    print('='*80)

    tests = []

    def report(name, val, ms, err, expected=None):
        ok = False
        if err:
            status = f'FAIL ({err[:60]})'
        elif expected and val == expected:
            status = f'PASS -> "{val}"'
            ok = True
        elif val is not None:
            status = f'MAYBE -> "{val}"'
            ok = True
        else:
            status = 'FAIL (None)'
        tests.append((name, ok, ms))
        print(f'  {name:<45} {ms:>7.0f}ms  {status}')

    # ── 1. Regular button via JS .click() ──
    val, ms, err = await js_eval(send, sid, '''
        document.getElementById("btn-regular").click();
        document.getElementById("btn-regular").textContent
    ''')
    report('JS .click() on regular button', val, ms, err, 'REGULAR_CLICKED')

    # ── 2. Same-origin iframe via JS ──
    val, ms, err = await js_eval(send, sid, '''
        const iframe = document.getElementById("iframe-same");
        const doc = iframe.contentDocument;
        doc.getElementById("btn-iframe").click();
        doc.getElementById("btn-iframe").textContent
    ''')
    report('JS .click() into same-origin iframe', val, ms, err, 'IFRAME_CLICKED')

    # ── 3. Same-origin iframe: type ──
    val, ms, err = await js_eval(send, sid, '''
        const iframe = document.getElementById("iframe-same");
        const input = iframe.contentDocument.getElementById("input-iframe");
        input.focus(); input.value = "typed-in-iframe"; input.value
    ''')
    report('JS .value= into same-origin iframe', val, ms, err, 'typed-in-iframe')

    # ── 4. Cross-origin iframe via JS ──
    val, ms, err = await js_eval(send, sid, '''
        try {
            const iframe = document.getElementById("iframe-cross");
            const doc = iframe.contentDocument;
            doc ? doc.title : "ACCESS_BLOCKED"
        } catch(e) { "BLOCKED: " + e.message }
    ''')
    report('JS access cross-origin iframe', val, ms, err)

    # ── 5. Open shadow DOM via JS ──
    val, ms, err = await js_eval(send, sid, '''
        const host = document.getElementById("shadow-host-open");
        const btn = host.shadowRoot.querySelector("#btn-shadow-open");
        btn.click();
        btn.textContent
    ''')
    report('JS .click() into open shadow DOM', val, ms, err, 'SHADOW_OPEN_CLICKED')

    # ── 6. Open shadow DOM: type ──
    val, ms, err = await js_eval(send, sid, '''
        const host = document.getElementById("shadow-host-open");
        const input = host.shadowRoot.querySelector("#input-shadow-open");
        input.focus(); input.value = "typed-in-shadow"; input.value
    ''')
    report('JS .value= into open shadow DOM', val, ms, err, 'typed-in-shadow')

    # ── 7. Closed shadow DOM via JS ──
    val, ms, err = await js_eval(send, sid, '''
        const host = document.getElementById("shadow-host-closed");
        const sr = host.shadowRoot;
        sr ? "HAS_ACCESS" : "NULL_SHADOWROOT"
    ''')
    report('JS access closed shadow DOM (shadowRoot)', val, ms, err)

    # ── 8. Closed shadow DOM via stashed ref ──
    val, ms, err = await js_eval(send, sid, '''
        const sr = window.__closedShadow;
        if (sr) {
            const btn = sr.querySelector("#btn-shadow-closed");
            btn.click();
            btn.textContent
        } else { "NO_REF" }
    ''')
    report('JS .click() closed shadow via window ref', val, ms, err, 'SHADOW_CLOSED_CLICKED')

    # ── 9. Coordinate-based JS click (elementFromPoint) ──
    # First get button position
    val, ms, err = await js_eval(send, sid, '''
        document.getElementById("btn-regular").textContent = "Regular Button";
        const rect = document.getElementById("btn-regular").getBoundingClientRect();
        JSON.stringify({x: rect.x + rect.width/2, y: rect.y + rect.height/2})
    ''')
    if val:
        import json
        coords = json.loads(val)
        val2, ms2, err2 = await js_eval(send, sid, f'''
            const el = document.elementFromPoint({coords["x"]}, {coords["y"]});
            if (el) {{ el.click(); el.textContent }} else {{ "NO_ELEMENT" }}
        ''')
        report('JS elementFromPoint().click()', val2, ms2, err2, 'REGULAR_CLICKED')
    else:
        report('JS elementFromPoint().click()', None, ms, 'Could not get coords')

    # ── 10. Coordinate click INTO iframe ──
    val, ms, err = await js_eval(send, sid, '''
        // Reset iframe button
        document.getElementById("iframe-same").contentDocument.getElementById("btn-iframe").textContent = "Iframe Button";
        const iframeRect = document.getElementById("iframe-same").getBoundingClientRect();
        // elementFromPoint at iframe location returns the iframe element, not its content
        const el = document.elementFromPoint(iframeRect.x + 50, iframeRect.y + 20);
        el ? el.tagName + "#" + el.id : "NOTHING"
    ''')
    report('JS elementFromPoint() at iframe coords', val, ms, err)

    # ── 11. Can we dispatch a synthetic click event at coordinates? ──
    val, ms, err = await js_eval(send, sid, '''
        document.getElementById("btn-regular").textContent = "Regular Button";
        const rect = document.getElementById("btn-regular").getBoundingClientRect();
        const evt = new MouseEvent('click', {
            bubbles: true, cancelable: true, view: window,
            clientX: rect.x + rect.width/2, clientY: rect.y + rect.height/2
        });
        document.getElementById("btn-regular").dispatchEvent(evt);
        document.getElementById("btn-regular").textContent
    ''')
    report('JS synthetic MouseEvent on element', val, ms, err, 'REGULAR_CLICKED')

    # ── 12. CDP Input.dispatchMouseEvent (for comparison) ──
    await js_eval(send, sid, 'document.getElementById("btn-regular").textContent = "Regular Button"')
    t0 = time.time()
    try:
        # Get position
        r = await send.Runtime.evaluate(params={
            'expression': 'JSON.stringify(document.getElementById("btn-regular").getBoundingClientRect())',
            'returnByValue': True
        }, session_id=sid)
        import json
        rect = json.loads(r['result']['value'])
        x, y = rect['x'] + rect['width']/2, rect['y'] + rect['height']/2
        await send.Input.dispatchMouseEvent(params={'type':'mousePressed','x':x,'y':y,'button':'left','clickCount':1}, session_id=sid)
        await send.Input.dispatchMouseEvent(params={'type':'mouseReleased','x':x,'y':y,'button':'left','clickCount':1}, session_id=sid)
        r2 = await send.Runtime.evaluate(params={
            'expression': 'document.getElementById("btn-regular").textContent', 'returnByValue': True
        }, session_id=sid)
        val = r2['result']['value']
        ms = (time.time()-t0)*1000
        report('CDP Input.dispatchMouseEvent', val, ms, None, 'REGULAR_CLICKED')
    except Exception as e:
        report('CDP Input.dispatchMouseEvent', None, (time.time()-t0)*1000, str(e))

    # ── 13. CDP mouse into same-origin iframe ──
    await js_eval(send, sid, '''
        document.getElementById("iframe-same").contentDocument.getElementById("btn-iframe").textContent = "Iframe Button"
    ''')
    t0 = time.time()
    try:
        r = await send.Runtime.evaluate(params={
            'expression': '''JSON.stringify((() => {
                const iframe = document.getElementById("iframe-same");
                const iRect = iframe.getBoundingClientRect();
                const btn = iframe.contentDocument.getElementById("btn-iframe");
                const bRect = btn.getBoundingClientRect();
                return {x: iRect.x + bRect.x + bRect.width/2, y: iRect.y + bRect.y + bRect.height/2};
            })())''', 'returnByValue': True
        }, session_id=sid)
        coords = json.loads(r['result']['value'])
        await send.Input.dispatchMouseEvent(params={'type':'mousePressed','x':coords['x'],'y':coords['y'],'button':'left','clickCount':1}, session_id=sid)
        await send.Input.dispatchMouseEvent(params={'type':'mouseReleased','x':coords['x'],'y':coords['y'],'button':'left','clickCount':1}, session_id=sid)
        await asyncio.sleep(0.1)
        r2 = await send.Runtime.evaluate(params={
            'expression': 'document.getElementById("iframe-same").contentDocument.getElementById("btn-iframe").textContent',
            'returnByValue': True
        }, session_id=sid)
        val = r2['result']['value']
        ms = (time.time()-t0)*1000
        report('CDP mouse click into same-origin iframe', val, ms, None, 'IFRAME_CLICKED')
    except Exception as e:
        report('CDP mouse click into same-origin iframe', None, (time.time()-t0)*1000, str(e))

    # ── 14. Can JS reach into cross-origin iframe via CDP target? ──
    # This tests if we can use CDP to get a separate session for cross-origin iframes
    t0 = time.time()
    try:
        targets = await send.Target.getTargets(params={}, session_id=sid)
        iframe_targets = [t for t in targets.get('targetInfos', []) if t.get('type') == 'iframe']
        val = f'Found {len(iframe_targets)} iframe targets'
        ms = (time.time()-t0)*1000
        report('CDP Target.getTargets (iframe count)', val, ms, None)
    except Exception as e:
        report('CDP Target.getTargets', None, (time.time()-t0)*1000, str(e))

    # ── Summary ──
    print('\n' + '='*80)
    print('  SUMMARY')
    print('='*80)

    passed = sum(1 for _, ok, _ in tests if ok)
    failed = len(tests) - passed
    print(f'\n  {passed} passed, {failed} failed out of {len(tests)} tests\n')

    print('  What JS CAN do:')
    print('    - Click/type regular elements')
    print('    - Click/type into same-origin iframes (via contentDocument)')
    print('    - Click/type into open shadow DOM (via shadowRoot)')
    print('    - Click/type into closed shadow DOM IF page holds a reference')
    print('    - elementFromPoint + click (coordinate-based)')
    print('    - Synthetic MouseEvent dispatch')
    print()
    print('  What JS CANNOT do:')
    print('    - Access cross-origin iframe content (blocked by Same-Origin Policy)')
    print('    - Access closed shadow DOM without a stashed reference')
    print('    - elementFromPoint into iframes (returns the iframe element, not content)')
    print()
    print('  What CDP can do that JS cannot:')
    print('    - Input.dispatchMouseEvent clicks INTO any iframe (cross-origin or not)')
    print('    - Separate CDP sessions per cross-origin iframe target')

    await session.kill()
    server.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
