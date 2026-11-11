import assert from 'node:assert/strict';
import {test} from 'node:test';
import {PassThrough,Writable} from 'node:stream';
import {createKeypressInput as createHiddenInput} from '../scripts/hidden-input.mjs';

function fixture() {
  const input=new PassThrough();input.isTTY=true;input.isRaw=false;
  const modes=[];input.setRawMode=value=>{input.isRaw=value;modes.push(value);return input;};
  let displayed='';const output=new Writable({write(chunk,_encoding,done){displayed+=chunk;done();}});
  const terminal=createHiddenInput({input,output});
  return {input,terminal,modes,displayed:()=>displayed};
}
const sample='public-test-input-not-a-real-password';
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('Windows CRLF and buffered blank Enter cannot prematurely submit the first prompt',async()=>{
  const f=fixture();try{
    let completed=false;
    const result=f.terminal.read('Password: ').then(value=>{completed=true;return value;});
    f.input.write('\r\n');await tick();assert.equal(completed,false);
    f.input.write(sample+'\r\n');assert.equal((await result)===sample,true);
    const confirm=f.terminal.read('Confirm: ');
    f.input.write('\r\n');await tick();
    f.input.write(sample+'\r\n');assert.equal((await confirm)===sample,true);
    assert.equal(f.displayed(),'Password: \nConfirm: \n');
    assert.deepEqual(f.modes,[true]);
  }finally{f.terminal.close();}
  assert.equal(f.input.isRaw,false);
});
test('coalesced Windows password and confirmation lines are retained with no echo/history',async()=>{
  const f=fixture();try{
    const first=f.terminal.read('Password: ');
    f.input.write(sample+'\r\n'+sample+'\r\n');
    assert.equal((await first)===sample,true);
    assert.equal((await f.terminal.read('Confirm: '))===sample,true);
    assert.equal(f.displayed().includes(sample),false);
  }finally{f.terminal.close();}
});
test('Windows backspace, split CR/LF, UTF-8 chunks and terminal keys are decoded correctly',async()=>{
  const f=fixture();try{
    const first=f.terminal.read('Password: ');
    f.input.write(sample);f.input.write('X');f.input.write('\u007f');f.input.write('\r');
    assert.equal((await first)===sample,true);
    f.input.write('\n');
    const second=f.terminal.read('Confirm: ');
    const unicode='public-test-é-🔑';const bytes=Buffer.from(unicode);
    for(const byte of bytes)f.input.write(Buffer.from([byte]));
    f.input.write('\r\n');assert.equal((await second)===unicode,true);
    assert.equal(f.displayed(),'Password: \nConfirm: \n');
  }finally{f.terminal.close();}
});
test('Ctrl-C, EOF and stream errors reject safely and restore terminal mode',async()=>{
  for(const action of [f=>f.input.write('\u0003'),f=>f.input.end(),f=>f.input.emit('error',Error('synthetic input failure'))]) {
    const f=fixture();const answer=f.terminal.read('Password: ');
    action(f);await assert.rejects(answer,/Cancelled|closed|failed/);
    f.terminal.close();assert.equal(f.input.isRaw,false);assert.equal(f.displayed().includes(sample),false);
  }
});
test('piped/non-TTY input is rejected before reading a password',()=>{
  assert.throws(()=>createHiddenInput({input:new PassThrough()}),/interactive private terminal/);
});
test('bracketed paste and arrow sequences are not included in a password',async()=>{
  const f=fixture();try{
    const answer=f.terminal.read('Password: ');
    f.input.write('\u001b[200~'+sample+'\u001b[201~');
    f.input.write('\u001b[A');f.input.write('\u001b[B');f.input.write('\r\n');
    assert.equal((await answer)===sample,true);
    assert.equal(f.displayed(),'Password: \n');
  }finally{f.terminal.close();}
});
