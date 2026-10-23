import { monitorEventLoopDelay } from "node:perf_hooks";

/** Temporary server-only diagnostics. Never accepts headers, bodies or errors for logging. */
export class BridgeTimingProbe {
  private readonly started = performance.now();
  private readonly delay = monitorEventLoopDelay({ resolution: 20 });
  private readonly times: Partial<Record<"fetch_started_ms" | "headers_received_ms" | "body_received_ms" | "parsed_ms" | "validated_ms", number>> = {};
  private deadlineStart?: number;
  private deadlineSignal?: AbortSignal;
  private abortAt?: number;
  private readonly onAbort = () => { this.abortAt = performance.now() - this.started; };
  private bytes?: number;
  private readMs?: number;
  private decodeMs?: number;
  private parseMs?: number;
  private readonly requestId: string;
  constructor(requestId: string) { this.requestId = requestId; this.delay.enable(); }
  mark(name: keyof BridgeTimingProbe["times"]) { this.times[name] = performance.now() - this.started; }
  deadline(signal: AbortSignal) {
    this.deadlineStart = performance.now();
    this.deadlineSignal = signal;
    if (signal.aborted) this.onAbort();
    else signal.addEventListener("abort", this.onAbort, { once: true });
    return signal;
  }
  async json(response: Response): Promise<unknown> {
    const readStarted = performance.now();
    let buffer: ArrayBuffer;
    try { buffer = await response.arrayBuffer(); }
    finally { this.readMs = performance.now() - readStarted; }
    this.bytes = buffer.byteLength; // Fetch has already decompressed these bytes.
    this.mark("body_received_ms");
    const decodeStarted = performance.now();
    const text = new TextDecoder().decode(buffer); // Fetch JSON uses UTF-8 with BOM removal.
    this.decodeMs = performance.now() - decodeStarted;
    const parseStarted = performance.now();
    try { return JSON.parse(text); }
    finally { this.parseMs = performance.now() - parseStarted; this.mark("parsed_ms"); }
  }
  finish(status: number | undefined, clientSignal: AbortSignal) {
    const now = performance.now();
    this.delay.disable();
    this.deadlineSignal?.removeEventListener("abort", this.onAbort);
    const rounded = (value: number | undefined) => value === undefined ? null : Math.round(value * 1000) / 1000;
    console.warn(JSON.stringify({
      event: "research_bridge_probe", version: 1, request_id: this.requestId,
      status: status ?? null, ...Object.fromEntries(Object.entries(this.times).map(([k,v]) => [k,rounded(v)])),
      decoded_body_bytes: this.bytes ?? null, body_read_including_decompression_ms: rounded(this.readMs),
      utf8_decode_ms: rounded(this.decodeMs), json_parse_ms: rounded(this.parseMs),
      elapsed_ms: rounded(now - this.started),
      deadline_elapsed_ms: this.deadlineStart === undefined ? null : rounded(now - this.deadlineStart),
      deadline_budget_exceeded: this.deadlineStart === undefined ? null : now - this.deadlineStart >= 12000,
      timeout_signal_aborted: this.deadlineSignal?.aborted ?? false,
      timeout_observed_ms: rounded(this.abortAt), client_aborted: clientSignal.aborted,
      event_loop_samples: this.delay.count,
      event_loop_delay_max_ms: this.delay.count ? rounded(this.delay.max / 1e6) : null,
    }));
  }
}
