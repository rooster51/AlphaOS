import {emitKeypressEvents} from 'node:readline';
import {createWindowsHiddenInput} from './windows-hidden-input.mjs';

export function createHiddenInput(options={}) {
  return process.platform==='win32' ? createWindowsHiddenInput(options) : createKeypressInput(options);
}

/** One terminal reader for the entire interaction. No echo, history or file I/O. */
export function createKeypressInput({input=process.stdin,output=process.stderr}={}) {
  if(!input.isTTY || typeof input.setRawMode!=='function')
    throw Error('Use an interactive private terminal; password input is never accepted from arguments or environment');
  const wasRaw=Boolean(input.isRaw);
  // Use Node's console/UTF-8 key decoder, without readline's echo, history or
  // TERM-dependent line editor. Keep raw mode active across both prompts.
  emitKeypressEvents(input);
  const lines=[];
  let pending,stopped=false,problem,value='';
  function stop(error) {
    if(stopped)return;
    stopped=true;problem=error;lines.length=0;value='';
    if(pending){pending.reject(error??Error('Password input closed'));pending=undefined;}
    input.removeListener('keypress',read);
    input.removeListener('error',onError);
    input.removeListener('end',onEnd);
    input.setRawMode(wasRaw);
    input.pause();
  }
  function read(text,key={}) {
    if(key.ctrl && key.name==='c'){stop(Error('Cancelled'));return;}
    if(key.name==='backspace' || (key.ctrl && key.name==='h')) {
      value=Array.from(value).slice(0,-1).join('');return;
    }
    if(key.ctrl && key.name==='u'){value='';return;}
    if(key.name!=='return' && key.name!=='enter') {
      // Ignore escape/control sequences (arrows, paste delimiters, console
      // focus events), rather than accidentally incorporating them in a hash.
      if(!key.ctrl && !key.meta && text && !/[\x00-\x1f\x7f-\x9f]/.test(text))value+=text;
      if(value.length>256)stop(Error('Password input too long'));
      return;
    }
    // A pending/empty CRLF must not submit an empty password. In particular,
    // never turn the shell's trailing Enter into an immediate length error.
    if(!value)return;
    const line=value;value='';
    if(pending){const current=pending;pending=undefined;current.resolve(line);}
    else if(lines.length<2)lines.push(line);
    else stop(Error('Too many input lines; retry in a private terminal'));
  }
  input.on('keypress',read);
  input.on('error',onError);
  input.on('end',onEnd);
  function onError(){stop(Error('Password input failed'));}
  function onEnd(){stop(Error('Password input closed'));}
  input.setRawMode(true);
  input.resume();
  return {
    read(prompt) {
      if(stopped)return Promise.reject(problem??Error('Password input closed'));
      if(pending)return Promise.reject(Error('Password prompt already active'));
      output.write(prompt);
      const answer=lines.length?Promise.resolve(lines.shift()):new Promise((resolve,reject)=>{pending={resolve,reject};});
      return answer.then(value=>{output.write('\n');return value;});
    },
    close(){stop();input.removeListener('error',onError);},
  };
}
