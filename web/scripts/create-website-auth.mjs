// Offline owner tool. Never run with real credentials in CI or a shared log.
import {randomBytes} from 'node:crypto';
import {writeFile} from 'node:fs/promises';
import {resolve,relative,isAbsolute} from 'node:path';
import {fileURLToPath} from 'node:url';
import bcrypt from 'bcryptjs';
import {createHiddenInput} from './hidden-input.mjs';

const target=process.argv[2];
const repository=fileURLToPath(new URL('../../',import.meta.url));
const destination=target&&resolve(target);
const rel=destination&&relative(repository,destination);
if(!destination || !rel || (!rel.startsWith('..')&&!isAbsolute(rel)))throw Error('Provide a new private output file OUTSIDE the repository');
const terminal=createHiddenInput();
let password;
try {
  password=await terminal.read('Password (20–72 UTF-8 bytes; hidden): ');
  if(Buffer.byteLength(password)<20 || Buffer.byteLength(password)>72)throw Error('Use 20–72 UTF-8 bytes; prefer a password-manager generated random password');
  if(await terminal.read('Confirm password (hidden): ')!==password)throw Error('Passwords do not match');
} finally { terminal.close(); }
const secrets={ALPHAOS_PASSWORD_HASH:await bcrypt.hash(password,12),ALPHAOS_SESSION_KEY:randomBytes(32).toString('base64url')};
await writeFile(destination,JSON.stringify(secrets,null,2)+'\n',{flag:'wx',mode:0o600});
process.stderr.write('Private authentication file created. Restrict its Windows ACL if applicable; import through the approved runtime-secret procedure. No deployment performed.\n');
