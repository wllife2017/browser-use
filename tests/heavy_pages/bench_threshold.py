"""Find the exact threshold where DOM capture becomes too slow for interactive use."""
import asyncio, os, sys, time, json
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))
os.environ['TIMEOUT_BrowserStateRequestEvent'] = '120'

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

import logging
logging.basicConfig(level=logging.WARNING)

def gen(n):
    return f'<html><body><div id=b></div><script>const f=document.createDocumentFragment();for(let i=0;i<{n};i++){{const d=document.createElement("div");d.innerHTML="<span>"+i+"</span><input value=v"+i+" /><button>X</button>";f.appendChild(d)}}document.getElementById("b").appendChild(f)</script></body></html>'

class Q(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass

async def main():
    d = Path(__file__).parent / 'generated'; d.mkdir(exist_ok=True)
    # Fine-grained scales around the threshold
    scales = [500, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 30000, 50000]
    for n in scales:
        (d/f't_{n}.html').write_text(gen(n))
    os.chdir(str(d))
    srv = HTTPServer(('127.0.0.1',8771), Q)
    Thread(target=srv.serve_forever, daemon=True).start()

    print(f'{"Elements":>10} {"DOM nodes":>10} {"Full capture":>13} {"Screenshot":>11} {"JS click":>10} {"CDP click":>11} {"Selectors":>10}')
    print('-'*80)

    for n in scales:
        s = BrowserSession(browser_profile=BrowserProfile(headless=True, cross_origin_iframes=False))
        await s.start()
        cdp = await s.get_or_create_cdp_session(focus=True)
        sid = cdp.session_id
        send = cdp.cdp_client.send

        await send.Page.navigate(params={'url':f'http://127.0.0.1:8771/t_{n}.html'}, session_id=sid)
        await asyncio.sleep(2)

        r = await send.Runtime.evaluate(params={'expression':'document.querySelectorAll("*").length','returnByValue':True}, session_id=sid)
        elems = r.get('result',{}).get('value',0)

        # Full capture
        t0=time.time()
        try:
            state = await asyncio.wait_for(s.get_browser_state_summary(cached=False), timeout=60)
            full_ms = (time.time()-t0)*1000
            sel_count = len(state.dom_state.selector_map) if state and state.dom_state else 0
        except:
            full_ms = (time.time()-t0)*1000
            sel_count = 0

        # Screenshot
        t0=time.time()
        try:
            await send.Page.captureScreenshot(params={'format':'png','quality':80}, session_id=sid)
            ss_ms = (time.time()-t0)*1000
        except:
            ss_ms = -1

        # JS click
        t0=time.time()
        await send.Runtime.evaluate(params={'expression':'document.querySelector("button")?.click()','returnByValue':True}, session_id=sid)
        js_ms = (time.time()-t0)*1000

        # CDP mouse click
        t0=time.time()
        try:
            await send.Input.dispatchMouseEvent(params={'type':'mousePressed','x':100,'y':50,'button':'left','clickCount':1}, session_id=sid)
            await send.Input.dispatchMouseEvent(params={'type':'mouseReleased','x':100,'y':50,'button':'left','clickCount':1}, session_id=sid)
            cdp_ms = (time.time()-t0)*1000
        except:
            cdp_ms = -1

        print(f'{n:>10,} {elems:>10,} {full_ms:>12.0f}ms {ss_ms:>10.0f}ms {js_ms:>9.0f}ms {cdp_ms:>10.0f}ms {sel_count:>10,}')
        await s.kill()

    srv.shutdown()

if __name__=='__main__':
    asyncio.run(main())
