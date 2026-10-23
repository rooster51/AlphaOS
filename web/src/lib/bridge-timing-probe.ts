/** Temporary server-only diagnostics. Never accepts headers, bodies or errors for logging. */
export class BridgeTimingProbe {
  private readonly started = performance.now();
  private readonly times: Partial<Record<"fetch_started_ms" | "headers_received_ms" | "body_consumption_end_ms" | "validated_ms", number>> = {};
  private deadlineStart?: number;
  private deadlineSignal?: AbortSignal;
  private abortAt?: number;
  private readonly onAbort = () => { this.abortAt = performance.now() - this.started; };
  private declaredBytes?: number;
  private readMs?: number;
  private bodyCompleted = false;
  private readonly requestId: string;
  constructor(requestId: string) { this.requestId = requestId; }
  mark(name: keyof BridgeTimingProbe["times"]) { this.times[name] = performance.now() - this.started; }
  deadline(signal: AbortSignal) {
    this.deadlineStart = performance.now();
    this.deadlineSignal = signal;
    if (signal.aborted) this.onAbort();
    else signal.addEventListener("abort", this.onAbort, { once: true });
    return signal;
  }
  async json(response: Response): Promise<unknown> {
    const declared = response.headers.get("content-length");
    if (declared && /^\d{1,15}$/.test(declared)) this.declaredBytes = Number(declared);
    const readStarted = performance.now();
    // Preserve Fetch's native consumption, decompression, decoding and parsing.
    // This interval also includes scheduling/CPU contention; it is not CPU time.
    try {
      const value: unknown = await response.json();
      this.bodyCompleted = true;
      return value;
    } finally {
      this.readMs = performance.now() - readStarted;
      this.mark("body_consumption_end_ms");
    }
  }

  finish(status: number | undefined, clientSignal: AbortSignal) {
    const now = performance.now();
    this.deadlineSignal?.removeEventListener("abort", this.onAbort);
    const rounded = (value: number | undefined) => value === undefined ? null : Math.round(value * 1000) / 1000;
    console.warn(JSON.stringify({
      event: "research_bridge_probe", version: 3, request_id: this.requestId,
      status: status ?? null, ...Object.fromEntries(Object.entries(this.times).map(([k,v]) => [k,rounded(v)])),
      body_json_completed: this.bodyCompleted,
      upstream_declared_content_length_bytes: this.declaredBytes ?? null,
      body_decompression_decode_parse_ms: rounded(this.readMs),
      elapsed_ms: rounded(now - this.started),
      deadline_elapsed_ms: this.deadlineStart === undefined ? null : rounded(now - this.deadlineStart),
      deadline_budget_exceeded: this.deadlineStart === undefined ? null : now - this.deadlineStart >= 12000,
      timeout_signal_aborted: this.deadlineSignal?.aborted ?? false,
      timeout_observed_ms: rounded(this.abortAt), client_aborted: clientSignal.aborted,
    }));
  }
}
