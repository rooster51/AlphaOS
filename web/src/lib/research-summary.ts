import { record } from './market-candidates.ts';

const digest = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
export function validCandidateReference(value: unknown): boolean {
  const ref = record(value);
  return Object.keys(ref).length === 4 && ['candidates','excluded'].includes(String(ref.bucket)) &&
    Number.isInteger(ref.index) && Number(ref.index) >= 0 && Number(ref.index) <= 10000 &&
    digest(ref.archive_sha256) && digest(ref.candidate_sha256);
}

export function validResearchSummary(value: unknown): boolean {
  const envelope = record(value), research = record(envelope.research);
  const session = record(research.research_session), transport = record(session.transport);
  const checksum = record(record(research.archive).storage).archive_sha256;
  if (envelope.response_format !== 'summary-v1' || transport.format !== 'summary-v1' ||
      transport.complete !== true || !digest(checksum)) return false;
  const reasons: Record<string, number> = {};
  for (const bucket of ['candidates','excluded'] as const) {
    const entries = session[bucket];
    if (!Array.isArray(entries) || transport[bucket === 'candidates' ? 'candidate_count' : 'excluded_count'] !== entries.length) return false;
    for (let index = 0; index < entries.length; index++) {
      const row = record(entries[index]), ref = record(row.detail);
      if (!validCandidateReference(ref) || ref.index !== index || ref.bucket !== bucket || ref.archive_sha256 !== checksum) return false;
      if (bucket === 'candidates' && !Array.isArray(record(row.research).legs)) return false;
      if (bucket === 'excluded') {
        const reason = typeof row.reason === 'string' ? row.reason : 'unspecified';
        reasons[reason] = (reasons[reason] ?? 0) + 1;
      }
    }
  }
  const reported = record(transport.exclusion_counts);
  return Object.keys(reported).length === Object.keys(reasons).length &&
    Object.entries(reasons).every(([key,count]) => reported[key] === count);
}
