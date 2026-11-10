import React from 'react';
import {readFileSync} from 'node:fs';
import {afterEach,expect,test,vi} from 'vitest';
import {render,screen,waitFor,cleanup,fireEvent} from '@testing-library/react';
import axe from 'axe-core';
import Dashboard from '../app/page';

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals()});
const run={id:'0123456789abcdef0123456789abcdef',summary:'ZeroDivisionError in average',status:'report',steps:8,mode:'simulation',reserved_usd:0,created_at:'2026-11-10T00:00:00Z'};
function mockApi(){
 vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>{
 let body:unknown={};
 if(input==='/api/runs')body=[run];
 else if(input==='/api/health')body={repository:'fixture',version:'1.0.0',docker:false,model_configured:false};
 else if(input==='/api/settings')body={max_files:5,max_steps:20,max_attempts:3,dollar_budget:.5};
 else if(input.startsWith('/api/knowledge'))body={results:[{path:'stats.py',start_line:1,end_line:3,text:'def average(values): return sum(values) / len(values)'}]};
 return {ok:true,json:async()=>body};
 }));
}
async function audit(){
 const results=await axe.run(document.body,{rules:{'color-contrast':{enabled:false}}});
 expect(results.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>n.html)}))).toEqual([]);
}

test('login is labelled and rejects missing server authentication',async()=>{
 vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({detail:'Sign in required'})})));
 render(<Dashboard/>);
 expect(screen.getByLabelText('Installation access token')).toBeTruthy();
 expect(screen.getByRole('button',{name:/enter mission control/i})).toBeTruthy();
 await audit();
});

test('overview, settings and knowledge have no automated accessibility violations',async()=>{
 mockApi();render(<Dashboard/>);
 await screen.findByRole('heading',{name:'Your code. Under watch.'});
 await audit();
 fireEvent.click(screen.getByRole('button',{name:/^Settings$/}));
 await screen.findByText('Execution guardrails');
 await audit();
 fireEvent.click(screen.getByRole('button',{name:'Knowledge'}));
 await screen.findByText('stats.py:1–3');
 await audit();
});

test('command palette supports Escape and restores focus',async()=>{
 mockApi();render(<Dashboard/>);
 await screen.findByRole('heading',{name:'Your code. Under watch.'});
 const trigger=screen.getByRole('button',{name:/Quick navigation/});
 trigger.focus();fireEvent.click(trigger);
 const dialog=await screen.findByRole('dialog',{name:'Quick navigation'});
 expect(dialog.contains(document.activeElement)).toBe(true);
 fireEvent.keyDown(window,{key:'Escape'});
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
 expect(document.activeElement).toBe(trigger);
});

test('new incident form traps focus and has a named log field',async()=>{
 mockApi();render(<Dashboard/>);
 await screen.findByRole('heading',{name:'Your code. Under watch.'});
 fireEvent.click(screen.getByRole('button',{name:/New incident/}));
 const dialog=await screen.findByRole('dialog',{name:'Submit an incident'});
 expect(screen.getByLabelText('Failure log / stack trace')).toBeTruthy();
 const last=screen.getByRole('button',{name:/Queue diagnosis/});
 last.focus();fireEvent.keyDown(document,{key:'Tab'});
 expect(dialog.contains(document.activeElement)).toBe(true);
 await audit();
});


test('small theme text meets WCAG AA contrast on its surface',()=>{
 const css=readFileSync('app/globals.css','utf8');
 const token=(name:string)=>{const value=css.match(new RegExp('--'+name+':(#[0-9a-f]{6})'));if(!value)throw Error(name);return value[1]};
 const luminance=(hex:string)=>{const v=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(n=>n<=.04045?n/12.92:((n+.055)/1.055)**2.4);return v[0]*.2126+v[1]*.7152+v[2]*.0722};
 const ratio=(a:string,b:string)=>{const values=[luminance(a),luminance(b)].sort((x,y)=>y-x);return (values[0]+.05)/(values[1]+.05)};
 for(const name of ['text','muted'])expect(ratio(token(name),token('surface'))).toBeGreaterThanOrEqual(4.5);
 for(const [selector,bg] of [['nav-label','#0d0f11'],['sequence','#111315']]){const color=css.match(new RegExp('\\.'+selector+'\\{[^}]*color:(#[0-9a-f]{6})'));expect(color).toBeTruthy();expect(ratio(color![1],bg)).toBeGreaterThanOrEqual(4.5)}
});

vi.mock('@tanstack/react-virtual',()=>({useVirtualizer:({count}:{count:number})=>({getVirtualItems:()=>Array.from({length:count},(_,index)=>({index,key:index,start:index*48,end:(index+1)*48})),getTotalSize:()=>count*48})}));

test('incident, replay and PR review remain accessible and block simulation publication',async()=>{
 const events=[
  {seq:1,agent:'watcher',kind:'incident',duration_ms:10,payload:{summary:'ZeroDivisionError'}},
  {seq:2,agent:'diagnostician',kind:'diagnosis',duration_ms:20,payload:{hypothesis:'Empty collection divides by zero',confidence:.98,evidence:[{path:'stats.py',start_line:1,end_line:3,text:'return sum(values) / len(values)'}]}},
  {seq:3,agent:'surgeon',kind:'proposal',duration_ms:30,payload:{summary:'Guard empty input',edits:[{path:'stats.py',rationale:'Preserve empty-input contract'}],diff:'--- a/stats.py\n+++ b/stats.py\n+    if not values:\n+        return 0.0'}},
  {seq:4,agent:'verifier',kind:'verification',duration_ms:40,payload:{passed:true,simulated:true}},
  {seq:5,agent:'reporter',kind:'report',duration_ms:10,payload:{title:'Fix fixture',simulated:true}},
 ];
 class Socket{
  onmessage:((e:{data:string})=>void)|null=null;
  onclose:(()=>void)|null=null;
  constructor(){queueMicrotask(()=>events.forEach(e=>this.onmessage?.({data:JSON.stringify(e)})))}
  close(){}
 }
 vi.stubGlobal('WebSocket',Socket);
 mockApi();
 const original=globalThis.fetch;
 vi.stubGlobal('fetch',vi.fn(async(input:string,options?:RequestInit)=>input.startsWith('/api/runs/')?{ok:true,json:async()=>({mode:'simulation',events})}:original(input,options)));
 render(<Dashboard/>);
 await screen.findByRole('heading',{name:'Your code. Under watch.'});
 fireEvent.click(screen.getByRole('button',{name:/ZeroDivisionError in average/}));
 await screen.findByText('Empty collection divides by zero');
 await waitFor(()=>expect((screen.getByRole('button',{name:/Approve & create draft PR/}) as HTMLButtonElement).disabled).toBe(true));
 await audit();
 fireEvent.click(screen.getByRole('button',{name:/^Replay$/}));
 await screen.findByLabelText('Replay event position');
 await audit();
 fireEvent.click(screen.getByRole('button',{name:'PR review'}));
 await screen.findByText('Review & draft PR');
 await audit();
});
