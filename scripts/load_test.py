"""Local authenticated WebSocket replay fan-out test; never targets a remote host."""
import argparse
import asyncio
import json
import os
import time
import httpx
import websockets

async def main(clients: int) -> None:
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',trust_env=False) as http:
        response=await http.post('/api/login',json={'token':os.environ['IRONCLAD_ADMIN_TOKEN']})
        response.raise_for_status()
        cookie='ironclad_session='+http.cookies['ironclad_session']
        response=await http.post('/api/demo',headers={'X-Ironclad-Intent':'dashboard'})
        response.raise_for_status()
        rid=response.json()['id']
    ready=0
    gate=asyncio.Event()
    elapsed=[]
    failures=[]
    started=time.monotonic()
    async def client(index: int) -> None:
        nonlocal ready
        try:
            before=time.monotonic()
            async with websockets.connect('ws://127.0.0.1:8000/api/runs/'+rid+'/stream?after=0',additional_headers={'Cookie':cookie},open_timeout=60,proxy=None) as ws:
                seq=[]
                while len(seq)<8:
                    data=json.loads(await asyncio.wait_for(ws.recv(),60))
                    if 'seq' in data:
                        seq.append(data['seq'])
                assert seq==list(range(1,9))
                elapsed.append((time.monotonic()-before)*1000)
                ready+=1
                if ready+len(failures)==clients:
                    gate.set()
                await asyncio.wait_for(gate.wait(),60)
                await asyncio.sleep(.5)
        except Exception as exc:
            failures.append(type(exc).__name__)
            if ready+len(failures)==clients:
                gate.set()
    await asyncio.gather(*(client(i) for i in range(clients)))
    elapsed.sort()
    print(json.dumps({'requested_clients':clients,'successful_clients':ready,'failed_clients':len(failures),'replay_events_per_client':8,'connection_plus_replay_p95_ms':round(elapsed[int(.95*(len(elapsed)-1))],2) if elapsed else None,'wall_seconds':round(time.monotonic()-started,2),'scope':'localhost connection and persisted replay fan-out; not a live event latency guarantee'},indent=2))
    if failures:
        raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--clients',type=int,default=50)
    args=parser.parse_args()
    if not 1<=args.clients<=500:
        parser.error('clients must be between 1 and 500')
    asyncio.run(main(args.clients))
