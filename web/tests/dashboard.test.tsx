import React from 'react';
import {afterEach,expect,test,vi} from 'vitest';
import {render,screen,waitFor,cleanup,fireEvent} from '@testing-library/react';
import axe from 'axe-core';
import Dashboard from '../app/page';

afterEach(()=>{cleanup();vi.restoreAllMocks()});
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
