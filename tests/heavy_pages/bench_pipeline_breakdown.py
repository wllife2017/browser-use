"""
Pipeline breakdown: time EVERY stage separately.

Q1: Where do the 8 seconds go at 5k elements?
Q2: Would AX tree alone be enough (and faster)?
Q3: Can we use partial AX tree (viewport-scoped)?
Q4: What if we skip paint order? Skip AX tree? Skip snapshot?
Q5: Can we get interactive elements via a fast JS query instead?
Q6: How fast is each raw CDP call vs the Python processing on top?
"""

import asyncio, json, logging, os, sys, time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))
os.environ['TIMEOUT_BrowserStateRequestEvent'] = '120'

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from browser_use.dom.service import DomService
from browser_use.dom.enhanced_snapshot import build_snapshot_lookup, REQUIRED_COMPUTED_STYLES
from browser_use.dom.serializer.serializer import DOMTreeSerializer

logging.basicConfig(level=logging.WARNING)

def gen(n):
    # Mix of interactive elements: buttons, inputs, links, selects, divs with handlers
    return f'''<html><head><title>Pipeline Bench {n}</title></head><body>
<h1>Pipeline Bench</h1>
<nav>{"".join(f'<a href="#">Link {i}</a> ' for i in range(min(n//10, 50)))}</nav>
<form>{"".join(f'<div><label>F{i}</label><input type="text" value="v{i}" /><select><option>A</option><option>B</option></select></div>' for i in range(min(n//5, 200)))}</form>
<div id="bulk"></div>
<script>
const f=document.createDocumentFragment();
for(let i=0;i<{n};i++){{
  const d=document.createElement('div');
  d.innerHTML='<span>'+i+'</span><input value=v'+i+' /><button onclick="this.textContent=\\'ok\\'">btn'+i+'</button>';
  if(i%3===0) d.addEventListener('click',()=>{{}});
  f.appendChild(d);
}}
document.getElementById('bulk').appendChild(f);
</script></body></html>'''

class Q(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass

async def t(label, coro, timeout=60):
    t0=time.time()
    try:
        r = await asyncio.wait_for(coro, timeout=timeout)
        ms=(time.time()-t0)*1000
        return r, ms, None
    except Exception as e:
        return None, (time.time()-t0)*1000, type(e).__name__

async def bench(n, base):
    s = BrowserSession(browser_profile=BrowserProfile(headless=True, cross_origin_iframes=False))
    await s.start()
    cdp = await s.get_or_create_cdp_session(focus=True)
    sid = cdp.session_id
    send = cdp.cdp_client.send

    await send.Page.navigate(params={'url':f'{base}/pipe_{n}.html'}, session_id=sid)
    await asyncio.sleep(2)

    r = await send.Runtime.evaluate(params={'expression':'document.querySelectorAll("*").length','returnByValue':True}, session_id=sid)
    elems = r.get('result',{}).get('value',0)

    target_id = s.agent_focus_target_id

    print(f'\n{"="*90}')
    print(f'  {n:,} target elements ({elems:,} DOM nodes)')
    print(f'{"="*90}')

    # ── RAW CDP CALLS (what Chrome does) ──────────────────────────────
    print(f'\n  {"RAW CDP CALLS":-<70}')

    # 1. DOMSnapshot.captureSnapshot
    async def do_snap():
        return await send.DOMSnapshot.captureSnapshot(params={
            'computedStyles': REQUIRED_COMPUTED_STYLES,
            'includePaintOrder':True,'includeDOMRects':True,
            'includeBlendedBackgroundColors':False,'includeTextColorOpacities':False
        }, session_id=sid)
    snapshot, ms, err = await t('DOMSnapshot.captureSnapshot', do_snap())
    snap_nodes = sum(len(d.get('nodes',{}).get('nodeName',[])) for d in (snapshot or {}).get('documents',[])) if snapshot else 0
    print(f'    DOMSnapshot.captureSnapshot          {ms:>8.0f}ms  {snap_nodes:,} nodes  {err or ""}')
    snap_ms = ms

    # 2. DOM.getDocument
    async def do_dom():
        return await send.DOM.getDocument(params={'depth':-1,'pierce':True}, session_id=sid)
    dom_tree, ms, err = await t('DOM.getDocument', do_dom())
    print(f'    DOM.getDocument(depth=-1)             {ms:>8.0f}ms  {err or ""}')
    dom_ms = ms

    # 3. Full AX tree
    async def do_ax_full():
        return await send.Accessibility.getFullAXTree(params={}, session_id=sid)
    ax_full, ms, err = await t('Accessibility.getFullAXTree', do_ax_full())
    ax_full_count = len(ax_full.get('nodes',[])) if ax_full else 0
    print(f'    Accessibility.getFullAXTree           {ms:>8.0f}ms  {ax_full_count:,} nodes  {err or ""}')
    ax_full_ms = ms

    # 4. Partial AX tree (single node, to see if the API exists)
    async def do_ax_partial():
        # Get the root node's backendNodeId
        root_id = dom_tree['root']['backendNodeId'] if dom_tree else 1
        return await send.Accessibility.getPartialAXTree(params={
            'backendNodeId': root_id, 'fetchRelatives': False
        }, session_id=sid)
    ax_partial, ms, err = await t('Accessibility.getPartialAXTree', do_ax_partial())
    ax_partial_count = len(ax_partial.get('nodes',[])) if ax_partial else 0
    print(f'    Accessibility.getPartialAXTree        {ms:>8.0f}ms  {ax_partial_count:,} nodes  {err or ""}')

    # 5. Screenshot
    async def do_ss():
        return await send.Page.captureScreenshot(params={'format':'png','quality':80}, session_id=sid)
    _, ms, err = await t('Screenshot', do_ss())
    print(f'    Page.captureScreenshot                {ms:>8.0f}ms  {err or ""}')

    # 6. JS query for interactive elements (viewport-scoped)
    async def do_js_interactive():
        return await send.Runtime.evaluate(params={
            'expression': '''
            (() => {
                const sel = 'a, button, input, select, textarea, [onclick], [role="button"], [role="link"], [role="tab"], [tabindex]';
                const all = document.querySelectorAll(sel);
                const vh = window.innerHeight;
                const visible = [];
                const offscreen = [];
                for (const el of all) {
                    const r = el.getBoundingClientRect();
                    const entry = {tag: el.tagName, id: el.id || undefined, name: el.name || undefined,
                                   type: el.type || undefined, value: (el.value || '').slice(0,30),
                                   text: (el.textContent || '').slice(0,30).trim(),
                                   x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                    if (r.bottom > 0 && r.top < vh) visible.push(entry);
                    else offscreen.push(entry);
                }
                return {visible: visible.length, offscreen: offscreen.length, total: all.length,
                        sample_visible: visible.slice(0, 5)};
            })()
            ''', 'returnByValue': True
        }, session_id=sid)
    js_r, ms, err = await t('JS interactive query', do_js_interactive())
    js_data = js_r.get('result',{}).get('value',{}) if js_r else {}
    print(f'    JS interactive query (viewport)       {ms:>8.0f}ms  {js_data.get("visible",0)} visible, {js_data.get("total",0)} total  {err or ""}')
    js_ms = ms

    # 7. JS query ALL elements (to compare with querySelectorAll('*'))
    async def do_js_all():
        return await send.Runtime.evaluate(params={
            'expression': 'document.querySelectorAll("*").length', 'returnByValue': True
        }, session_id=sid)
    _, ms, err = await t('JS querySelectorAll(*)', do_js_all())
    print(f'    JS querySelectorAll("*").length       {ms:>8.0f}ms  {err or ""}')

    # ── PYTHON PROCESSING (what browser-use adds) ─────────────────────
    if snapshot and dom_tree:
        print(f'\n  {"PYTHON PROCESSING":-<70}')

        # 8. build_snapshot_lookup
        t0=time.time()
        device_pixel_ratio = 1.0
        snapshot_lookup = build_snapshot_lookup(snapshot, device_pixel_ratio)
        ms = (time.time()-t0)*1000
        print(f'    build_snapshot_lookup                 {ms:>8.0f}ms  {len(snapshot_lookup):,} entries')

        # 9. Build AX tree lookup
        t0=time.time()
        ax_tree_data = ax_full if ax_full else {'nodes': []}
        ax_tree_lookup = {n['backendDOMNodeId']: n for n in ax_tree_data['nodes'] if 'backendDOMNodeId' in n}
        ms = (time.time()-t0)*1000
        print(f'    build AX tree lookup                  {ms:>8.0f}ms  {len(ax_tree_lookup):,} entries')

        # 10. Full _construct_enhanced_node + get_dom_tree
        dom_service = DomService(
            browser_session=s, cross_origin_iframes=False,
            paint_order_filtering=True, max_iframes=100, max_iframe_depth=5
        )
        t0=time.time()
        try:
            enhanced_tree, timing = await asyncio.wait_for(
                dom_service.get_dom_tree(target_id=target_id), timeout=60
            )
            ms = (time.time()-t0)*1000
            tree_ok = True
        except Exception as e:
            ms = (time.time()-t0)*1000
            tree_ok = False
            enhanced_tree = None
            timing = {}
        print(f'    get_dom_tree (full)                   {ms:>8.0f}ms')
        # Print sub-timings from the timing dict
        for k, v in sorted(timing.items()):
            print(f'      {k:<40} {v:>8.1f}ms')

        # 11. Serialization
        if tree_ok and enhanced_tree:
            t0=time.time()
            serialized, ser_timing = DOMTreeSerializer(
                enhanced_tree, None, paint_order_filtering=True, session_id=s.id
            ).serialize_accessible_elements()
            ms = (time.time()-t0)*1000
            print(f'    serialize_accessible_elements         {ms:>8.0f}ms  {len(serialized.selector_map):,} selectors')
            for k, v in sorted(ser_timing.items()):
                print(f'      {k:<40} {v*1000:>8.1f}ms')

            # 12. Serialization WITHOUT paint order
            t0=time.time()
            serialized2, ser_timing2 = DOMTreeSerializer(
                enhanced_tree, None, paint_order_filtering=False, session_id=s.id
            ).serialize_accessible_elements()
            ms = (time.time()-t0)*1000
            print(f'    serialize (NO paint order)            {ms:>8.0f}ms  {len(serialized2.selector_map):,} selectors')
            for k, v in sorted(ser_timing2.items()):
                print(f'      {k:<40} {v*1000:>8.1f}ms')

    # ── COMPARISON SUMMARY ────────────────────────────────────────────
    print(f'\n  {"COMPARISON":-<70}')
    print(f'    Raw CDP snapshot+DOM+AX:              {snap_ms+dom_ms+ax_full_ms:>8.0f}ms  (Chrome work)')
    print(f'    JS interactive query:                 {js_ms:>8.0f}ms  (alternative)')
    print(f'    Full pipeline overhead:               Python processing on top of CDP')

    await s.kill()


async def main():
    d = Path(__file__).parent / 'generated'; d.mkdir(exist_ok=True)
    scales = [5000, 20000, 100000]
    for n in scales:
        (d/f'pipe_{n}.html').write_text(gen(n))
    os.chdir(str(d))
    srv = HTTPServer(('127.0.0.1', 8775), Q)
    Thread(target=srv.serve_forever, daemon=True).start()

    for n in scales:
        await bench(n, 'http://127.0.0.1:8775')

    srv.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
