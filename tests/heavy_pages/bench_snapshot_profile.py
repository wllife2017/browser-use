"""Profile build_snapshot_lookup to find the exact O(n²) bottleneck."""
import asyncio, os, sys, time, cProfile, pstats, io
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv
load_dotenv(Path('/Users/magnus/Developer/cloud/backend/.env'))

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from browser_use.dom.enhanced_snapshot import build_snapshot_lookup, REQUIRED_COMPUTED_STYLES, _parse_rare_boolean_data

import logging
logging.basicConfig(level=logging.WARNING)

def gen(n):
    return f'<html><body><div id=b></div><script>const f=document.createDocumentFragment();for(let i=0;i<{n};i++){{const d=document.createElement("div");d.innerHTML="<span>"+i+"</span><input value=v"+i+" /><button>X</button>";f.appendChild(d)}}document.getElementById("b").appendChild(f)</script></body></html>'

class Q(SimpleHTTPRequestHandler):
    def log_message(self,*a):pass

async def main():
    d = Path(__file__).parent / 'generated'; d.mkdir(exist_ok=True)
    for n in [5000, 20000]:
        (d/f'prof_{n}.html').write_text(gen(n))
    os.chdir(str(d))
    srv = HTTPServer(('127.0.0.1', 8774), Q)
    Thread(target=srv.serve_forever, daemon=True).start()

    for n in [5000, 20000]:
        s = BrowserSession(browser_profile=BrowserProfile(headless=True))
        await s.start()
        cdp = await s.get_or_create_cdp_session(focus=True)
        sid = cdp.session_id
        send = cdp.cdp_client.send

        await send.Page.navigate(params={'url':f'http://127.0.0.1:8774/prof_{n}.html'}, session_id=sid)
        await asyncio.sleep(2)

        # Get snapshot
        snapshot = await send.DOMSnapshot.captureSnapshot(params={
            'computedStyles': REQUIRED_COMPUTED_STYLES,
            'includePaintOrder':True,'includeDOMRects':True,
            'includeBlendedBackgroundColors':False,'includeTextColorOpacities':False
        }, session_id=sid)

        total_nodes = sum(len(d.get('nodes',{}).get('nodeName',[])) for d in snapshot.get('documents',[]))
        print(f'\n{"="*80}')
        print(f'  {n:,} elements, {total_nodes:,} snapshot nodes')
        print(f'{"="*80}')

        # Check isClickable data size
        for doc_idx, doc in enumerate(snapshot['documents']):
            nodes_data = doc['nodes']
            if 'isClickable' in nodes_data:
                clickable_list = nodes_data['isClickable']['index']
                print(f'  doc[{doc_idx}] isClickable index list length: {len(clickable_list)}')

        # Manual breakdown of build_snapshot_lookup
        strings = snapshot['strings']
        documents = snapshot['documents']

        for doc_idx, document in enumerate(documents):
            nodes_data = document['nodes']
            layout = document['layout']

            # Time: build backend_node_to_snapshot_index
            t0 = time.time()
            backend_node_to_snapshot_index = {}
            if 'backendNodeId' in nodes_data:
                for i, bid in enumerate(nodes_data['backendNodeId']):
                    backend_node_to_snapshot_index[bid] = i
            ms = (time.time()-t0)*1000
            print(f'  doc[{doc_idx}] build backend_node_to_snapshot_index: {ms:.1f}ms ({len(backend_node_to_snapshot_index)} entries)')

            # Time: build layout_index_map
            t0 = time.time()
            layout_index_map = {}
            if layout and 'nodeIndex' in layout:
                for layout_idx, node_index in enumerate(layout['nodeIndex']):
                    if node_index not in layout_index_map:
                        layout_index_map[node_index] = layout_idx
            ms = (time.time()-t0)*1000
            print(f'  doc[{doc_idx}] build layout_index_map: {ms:.1f}ms ({len(layout_index_map)} entries)')

            # Time: isClickable parsing (the suspected O(n²))
            if 'isClickable' in nodes_data:
                clickable_index_list = nodes_data['isClickable']['index']

                # Method 1: current (list scan per node)
                t0 = time.time()
                count = 0
                for snapshot_index in range(len(nodes_data.get('backendNodeId', []))):
                    if snapshot_index in clickable_index_list:  # O(len(clickable_index_list)) per call!
                        count += 1
                ms = (time.time()-t0)*1000
                print(f'  doc[{doc_idx}] isClickable via LIST scan: {ms:.1f}ms (found {count} clickable)')

                # Method 2: convert to set first
                t0 = time.time()
                clickable_set = set(clickable_index_list)
                count2 = 0
                for snapshot_index in range(len(nodes_data.get('backendNodeId', []))):
                    if snapshot_index in clickable_set:  # O(1) per call
                        count2 += 1
                ms = (time.time()-t0)*1000
                print(f'  doc[{doc_idx}] isClickable via SET scan: {ms:.1f}ms (found {count2} clickable)')
                assert count == count2

            # Time: the main loop (creating EnhancedSnapshotNode objects)
            t0 = time.time()
            dummy_count = 0
            for backend_node_id, snapshot_index in backend_node_to_snapshot_index.items():
                # Simulate the work without isClickable
                if snapshot_index in layout_index_map:
                    layout_idx = layout_index_map[snapshot_index]
                    if layout_idx < len(layout.get('bounds', [])):
                        bounds = layout['bounds'][layout_idx]
                        _ = bounds[0] if len(bounds) >= 4 else None
                    if layout_idx < len(layout.get('styles', [])):
                        style_indices = layout['styles'][layout_idx]
                        # Parse styles
                        styles = {}
                        for i, si in enumerate(style_indices):
                            if i < len(REQUIRED_COMPUTED_STYLES) and 0 <= si < len(strings):
                                styles[REQUIRED_COMPUTED_STYLES[i]] = strings[si]
                dummy_count += 1
            ms = (time.time()-t0)*1000
            print(f'  doc[{doc_idx}] main loop (no isClickable): {ms:.1f}ms ({dummy_count} iterations)')

        # Time: full build_snapshot_lookup
        t0 = time.time()
        result = build_snapshot_lookup(snapshot, 1.0)
        ms = (time.time()-t0)*1000
        print(f'\n  FULL build_snapshot_lookup: {ms:.0f}ms ({len(result)} entries)')

        # Profile it
        pr = cProfile.Profile()
        pr.enable()
        result2 = build_snapshot_lookup(snapshot, 1.0)
        pr.disable()

        stream = io.StringIO()
        ps = pstats.Stats(pr, stream=stream).sort_stats('cumulative')
        ps.print_stats(15)
        print(f'\n  cProfile top 15:')
        for line in stream.getvalue().split('\n')[:20]:
            print(f'    {line}')

        await s.kill()

    srv.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
