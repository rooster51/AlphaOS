import assert from 'node:assert/strict';
import {test} from 'node:test';
import {EventEmitter} from 'node:events';
import {PassThrough,Writable} from 'node:stream';
import {createWindowsHiddenInput,reportInputDiagnostics} from '../scripts/windows-hidden-input.mjs';
import {createKeypressInput} from '../scripts/hidden-input.mjs';
const sample='public-native-test-password-42';
const marker='ALPHAOS_HIDDEN_INPUT_V1:';
const encode=value=>Buffer.from(value,'utf8').toString('base64');
function fixture() {
  let displayed='',call;
  const output=new Writable({write(chunk,_encoding,done){displayed+=chunk;done();}});
  const input=new PassThrough();input.isTTY=true;
  const child=new EventEmitter();child.stdout=new PassThrough();child.stderr=new PassThrough();
  let killed=false;child.kill=()=>{killed=true;child.emit('close',null);};
  const terminal=createWindowsHiddenInput({input,output,systemRoot:'C:\\Windows',spawnProcess:(file,args,options)=>{
    call={file,args,options};return child;
  }});
  return {terminal,child,output,input,displayed:()=>displayed,call:()=>call,killed:()=>killed};
}
test('Windows uses native SecureString with inherited console input and private pipes, never password arguments',async()=>{
  const f=fixture();const answer=f.terminal.read('Password: ');
  const call=f.call();assert(call.file.endsWith('powershell.exe'));
  assert.deepEqual(call.options.stdio,['inherit','pipe','pipe']);assert(call.options.windowsHide);
  const command=Buffer.from(call.args.at(-1),'base64').toString('utf16le');
  assert(command.includes('Read-Host -AsSecureString'));assert(command.includes('ZeroFreeBSTR'));assert(command.includes('$secure.Dispose()'));
  assert(!command.includes(sample));assert(!Object.hasOwn(call.options,'env'));
  const raw='host output\r\n'+marker+encode(sample)+'\r\n';
  for(const part of [raw.slice(0,11),raw.slice(11)])f.child.stdout.write(part);
  f.child.emit('close',0);assert.equal((await answer)===sample,true);
  assert.equal(f.displayed(),'Password: \n');f.terminal.close();
});
test('safe diagnostics contain exactly receipt boolean and UTF-8 byte length, including multibyte input',()=>{
  const f=fixture();
  for(const value of ['',sample,'é🔑'])reportInputDiagnostics(f.output,value);
  const lines=f.displayed().trim().split('\n').map(line=>JSON.parse(line));
  assert.deepEqual(lines,[{inputReceived:false,byteLength:0},{inputReceived:true,byteLength:30},{inputReceived:true,byteLength:6}]);
  assert(!f.displayed().includes(sample));f.terminal.close();
});
test('native input preserves spaces and Unicode exactly; empty input is reported without fabricated characters',async()=>{
  for(const value of ['',sample,'  public-🔑-test-é  ']) {
    const f=fixture();const answer=f.terminal.read('Password: ');
    f.child.stdout.write(marker+encode(value)+'\r\n');f.child.emit('close',0);
    assert.equal((await answer)===value,true);assert.equal(f.displayed(),'Password: \n');f.terminal.close();
  }
});
test('process failures, cancellation and invalid protocols never echo captured output or errors',async()=>{
  for(const action of [
    f=>{f.child.stdout.write(sample);f.child.emit('close',1);},
    f=>{f.child.stderr.write(sample);f.child.emit('error',Error(sample));},
    f=>{f.child.stdout.write(marker+'***');f.child.emit('close',0);},
    f=>f.terminal.close(),
  ]) {
    const f=fixture();const answer=f.terminal.read('Password: ');action(f);
    await assert.rejects(answer,error=>!error.message.includes(sample)&&/secure input failed|cancelled/.test(error.message));
    assert.equal(f.displayed(),'Password: \n');f.terminal.close();
  }
});
test('oversized native output is killed, not logged; non-TTY input never starts PowerShell',async()=>{
  const f=fixture();const answer=f.terminal.read('Password: ');
  f.child.stdout.write('x'.repeat(5000));await assert.rejects(answer,/secure input failed/);
  assert(f.killed());assert.equal(f.displayed(),'Password: \n');f.terminal.close();
  assert.throws(()=>createWindowsHiddenInput({input:new PassThrough()}),/interactive private terminal/);
});
test('raw key filter regression: Windows modified printable events can truncate otherwise valid text',async()=>{
  // Demonstrates why this reader must not be used on Windows. Synthetic events
  // carry only public test characters; assertions never print password contents.
  const input=new PassThrough();input.isTTY=true;input.setRawMode=()=>{};
  const output=new Writable({write(_chunk,_encoding,done){done();}});
  const raw=createKeypressInput({input,output});const answer=raw.read('Password: ');
  input.emit('keypress','x',{name:'x'});
  for(let n=0;n<25;n++)input.emit('keypress','@',{ctrl:true,meta:true,name:'q'});
  input.emit('keypress','\r',{name:'return'});
  assert.equal(Buffer.byteLength(await answer),1);raw.close();
});
