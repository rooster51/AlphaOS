// Offline owner tool. Never run with real credentials in CI or a shared log.
import {randomBytes} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import bcrypt from 'bcryptjs';

const target=process.argv[2];
const repository=fileURLToPath(new URL('../../',import.meta.url));
const destination=target&&resolve(target);
const rel=destination&&relative(repository,destination);
if(!destination || !rel || (!rel.startsWith('..')&&!isAbsolute(rel)))throw Error('Provide a new private output file OUTSIDE the repository');
if(!process.stdin.isTTY || !process.stdin.setRawMode)throw Error('Use an interactive private terminal; password input is never accepted from arguments or environment');
async function hidden(prompt) {
  process.stderr.write(prompt);process.stdin.setRawMode(true);process.stdin.resume();process.stdin.setEncoding('utf8');
  return new Promise((resolve,reject)=>{
    let value='';
    const end=()=>{process.stdin.removeListener('data',read);process.stdin.setRawMode(false);process.stdin.pause();process.stderr.write('\n');};
    const read=chunk=>{for(const c of chunk){
      if(c==='\u0003'){end();reject(Error('Cancelled'));return;}
      if(c==='\r'||c==='\n'){end();resolve(value);return;}
      if(c==='\u007f'||c==='\b')value=value.slice(0,-1);
      else if(c>=' ')value+=c;
    }};
    process.stdin.on('data',read);
  });
}
const password=await hidden('Password (20–72 UTF-8 bytes; hidden): ');
if(Buffer.byteLength(password)<20 || Buffer.byteLength(password)>72)throw Error('Use 20–72 UTF-8 bytes; prefer a password-manager generated random password');
if(await hidden('Confirm password (hidden): ')!==password)throw Error('Passwords do not match');
const secrets={ALPHAOS_PASSWORD_HASH:await bcrypt.hash(password,12),ALPHAOS_SESSION_KEY:randomBytes(32).toString('base64url')};
await writeFile(destination,JSON.stringify(secrets,null,2)+'\n',{flag:'wx',mode:0o600});
process.stderr.write('Private authentication file created. Restrict its Windows ACL if applicable; import through the approved runtime-secret procedure. No deployment performed.\n');
