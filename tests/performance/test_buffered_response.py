"""Full-contract, redaction and lifetime checks for the buffered experiment."""
import gc,json,weakref
from datetime import date
from copy import deepcopy
import numpy as np
import pytest
from alphaos_api.app import sanitized
from alphaos_api.json_encoding import encode_json
from alphaos_api.buffered_research_json import encode_research_response

def payload(entry):
 return dict(schema_version='alphaos-interface-v2',research=dict(research_session=dict(
  candidates=[entry,entry],excluded=[dict(research=entry)],comparison={'same':'retained'})),other='retained')

@pytest.mark.parametrize('entry',[
 {'name':'unicode café — λ','v':[1.0,-0.0,2,True,None]},
 {'v':[float('inf'),float('-inf'),float('nan')]},
 {'v':[2**80,-2**80]},
 {'v':np.float64(1.25),'date':date(2030,1,18)},
 {'access_token':'DROP','account_number':'DROP','password':'DROP','source':'prefix SECRET suffix'},
 {'v':({'a':1}, {'a':2})},
 {1:'first','1':'second'},
])
def test_full_bytes_and_redaction(entry,monkeypatch):
 monkeypatch.setenv('ALPHAOS_API_TOKEN','SECRET')
 p=payload(entry);before=deepcopy(p)
 actual=encode_research_response(p,sanitize=sanitized,encode=encode_json)
 assert actual==encode_json(sanitized(p))
 assert b'SECRET' not in actual and b'DROP' not in actual
 # NaN equality is undefined; byte parity also checks unchanged input content.
 assert encode_json(sanitized(p))==encode_json(sanitized(before))

@pytest.mark.parametrize('p',[{'other':1},dict(schema_version='alphaos-interface-v2',research={}),payload({})])
def test_legacy_and_empty_shapes(p):
 assert encode_research_response(p,sanitize=sanitized,encode=encode_json)==encode_json(sanitized(p))

@pytest.mark.parametrize('bad',[object()])
def test_unknown_values_still_fail_closed(bad):
 with pytest.raises(TypeError):encode_research_response(payload({'unknown':bad}),sanitize=sanitized,encode=encode_json)

class SourceList(list):pass

def test_source_graph_is_not_retained_by_buffered_encoding():
 enabled=gc.isenabled();gc.collect();gc.disable()
 try:
  source=SourceList([{'trade':{'legs':[{'strike':100}]}}]);ref=weakref.ref(source)
  p=payload({});p['research']['research_session']['candidates']=source
  encoded=encode_research_response(p,sanitize=sanitized,encode=encode_json)
  del p,source
  assert ref() is None
  assert json.loads(encoded)['research']['research_session']['candidates'][0]['trade']['legs'][0]['strike']==100
 finally:
  gc.collect()
  if enabled:gc.enable()
