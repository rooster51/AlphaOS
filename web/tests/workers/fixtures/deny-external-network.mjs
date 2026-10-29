// Loaded ONLY by upload CLI subprocess tests. Never used by the application.
import net from 'node:net';
import {syncBuiltinESMExports} from 'node:module';

const local=host=>['127.0.0.1','localhost','::1','[::1]'].includes(host);
const connect=net.Socket.prototype.connect;
net.Socket.prototype.connect=function(...args) {
  let options=args[0];
  while(Array.isArray(options))options=options[0];
  if(typeof options==='object' && options!==null) {
    if(options.path && !options.port) {
      if(!String(options.path).startsWith('\\\\.\\pipe\\'))throw Error('External network blocked by upload test');
    } else if(!local(options.host??options.hostname??'localhost'))throw Error('External network blocked by upload test');
  } else if(typeof options==='number') {
    if(typeof args[1]==='string' && !local(args[1]))throw Error('External network blocked by upload test');
  } else throw Error('External network blocked by upload test');
  return connect.apply(this,args);
};
const fetch=globalThis.fetch;
globalThis.fetch=(input,...rest)=>{
  const url=new URL(typeof input==='string'||input instanceof URL?input:input.url);
  if(!local(url.hostname))throw Error('External network blocked by upload test');
  return fetch(input,...rest);
};
syncBuiltinESMExports();
