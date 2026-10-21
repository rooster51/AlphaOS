import assert from "node:assert/strict";
import {test} from "node:test";
import {archiveExpirations} from "../src/lib/market-candidates.ts";

test("expiration choices require stored observations when coverage is supplied",()=>{
  const session={diagnostics:{expiration_selection:{available:["2030-01-02","2030-01-18","2031-01-17"]}}};
  const archive={expiration_coverage:{entries:[
    {expiration:"2030-01-18",status:"archived_observations",eligible_date:true},
    {expiration:"2031-01-17",status:"missing_verified_evidence",eligible_date:true},
    {expiration:"2030-01-05",status:"archived_observations",eligible_date:false}
  ]}};
  assert.deepEqual(archiveExpirations(session,archive),["2030-01-18"]);
  assert.deepEqual(archiveExpirations(session,{expiration_coverage:{entries:[]}}),[]);
  assert.deepEqual(archiveExpirations(session),["2030-01-02","2030-01-18","2031-01-17"]);
});
