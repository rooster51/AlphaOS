"""Bounded process-local TTL storage. No persistence of quotes or credentials."""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock

class TTLStore:
    def __init__(self,clock,maxsize=128):
        self.clock,self.maxsize=clock,maxsize
        self.items=OrderedDict();self.lock=RLock()
    def get(self,key):
        with self.lock:
            entry=self.items.get(key)
            if entry is None: return None
            if self.clock().timestamp()>=entry[0]:
                del self.items[key];return None
            self.items.move_to_end(key)
            return deepcopy(entry[1])
    def put(self,key,value,ttl):
        with self.lock:
            now=self.clock().timestamp()
            for old in list(self.items):
                if self.items[old][0]<=now: del self.items[old]
            self.items[key]=(now+ttl,deepcopy(value));self.items.move_to_end(key)
            while len(self.items)>self.maxsize:self.items.popitem(last=False)
        return value
    def load(self,key,ttl,loader):
        with self.lock:
            value=self.get(key)
            return value if value is not None else self.put(key,loader(),ttl)
