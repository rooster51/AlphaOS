import {spawn} from 'node:child_process';
import {join} from 'node:path';

const marker='ALPHAOS_HIDDEN_INPUT_V1:';
// This command contains no password. The native Windows host owns secure input;
// only a private, captured pipe transfers its UTF-8 bytes to the hashing process.
const command=`
$ErrorActionPreference = 'Stop'
$secure = $null; $pointer = [IntPtr]::Zero; $bytes = $null; $text = $null
try {
  $secure = Read-Host -AsSecureString
  $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
  $text = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
  $bytes = [Text.Encoding]::UTF8.GetBytes($text)
  [Console]::Out.WriteLine('${marker}' + [Convert]::ToBase64String($bytes))
} catch { exit 1 }
finally {
  if ($bytes) { [Array]::Clear($bytes, 0, $bytes.Length) }
  $text = $null
  if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
  if ($secure) { $secure.Dispose() }
}
`;
export function createWindowsHiddenInput({input=process.stdin,output=process.stderr,spawnProcess=spawn,systemRoot=process.env.SystemRoot}={}) {
  if(!input.isTTY)throw Error('Use an interactive private terminal; piped password input is not accepted');
  if(!systemRoot)throw Error('Windows secure input is unavailable');
  let active,closed=false;
  return {
    read(prompt) {
      if(closed || active)return Promise.reject(Error('Password input unavailable'));
      input.pause();output.write(prompt);
      return new Promise((resolve,reject)=>{
        let captured='',size=0,done=false,interrupt;
        const finish=(error,value)=>{
          if(done)return;done=true;captured='';active=undefined;
          if(interrupt)process.removeListener('SIGINT',interrupt);
          output.write('\n');
          if(error)reject(Error('Windows secure input failed or was cancelled; no credential file was written'));
          else resolve(value);
        };
        try {
          const child=spawnProcess(join(systemRoot,'System32','WindowsPowerShell','v1.0','powershell.exe'),
            ['-NoLogo','-NoProfile','-EncodedCommand',Buffer.from(command,'utf16le').toString('base64')],
            {stdio:['inherit','pipe','pipe'],windowsHide:true});
          active=child;
          interrupt=()=>{child.kill();finish(true);};
          process.once('SIGINT',interrupt);
          child.stdout.setEncoding('utf8');
          child.stdout.on('data',chunk=>{
            size+=Buffer.byteLength(chunk);
            if(size>4096){child.kill();finish(true);return;}
            captured+=chunk;
          });
          // Never forward host output, errors or captured password bytes to logs.
          child.stderr.resume();
          child.once('error',()=>finish(true));
          child.once('close',code=>{
            if(done)return;
            const match=captured.match(/ALPHAOS_HIDDEN_INPUT_V1:([A-Za-z0-9+/]*={0,2})\r?\n?$/);
            if(code!==0 || !match){finish(true);return;}
            const bytes=Buffer.from(match[1],'base64');
            if(bytes.toString('base64')!==match[1]){bytes.fill(0);finish(true);return;}
            const value=bytes.toString('utf8');bytes.fill(0);finish(false,value);
          });
        } catch {finish(true);}
      });
    },
    close(){closed=true;if(active)active.kill();},
  };
}

export function reportInputDiagnostics(output,value) {
  output.write(JSON.stringify({inputReceived:value.length>0,byteLength:Buffer.byteLength(value,'utf8')})+'\n');
}
