CREATE TABLE IF NOT EXISTS public.website_login_limiter_lock (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton)
);

INSERT INTO public.website_login_limiter_lock (singleton)
VALUES (true)
ON CONFLICT (singleton) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.website_login_attempts (
    attempted_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS website_login_attempts_attempted_at_idx
    ON public.website_login_attempts (attempted_at);

ALTER TABLE public.website_login_limiter_lock ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.website_login_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.website_login_limiter_lock FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.website_login_attempts FROM PUBLIC, anon, authenticated, service_role;
GRANT USAGE ON SCHEMA public TO service_role;

CREATE OR REPLACE FUNCTION public.consume_website_login_attempt()
RETURNS TABLE (allowed boolean, retry_after_seconds integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $function$
DECLARE
    v_now timestamptz;
    v_attempt_count bigint;
    v_oldest_attempt timestamptz;
BEGIN
    PERFORM 1
    FROM public.website_login_limiter_lock
    WHERE singleton = true
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'website login limiter lock is missing';
    END IF;

    v_now := pg_catalog.clock_timestamp();

    DELETE FROM public.website_login_attempts
    WHERE attempted_at <= v_now - interval '60 seconds';

    SELECT count(*), min(attempted_at)
    INTO v_attempt_count, v_oldest_attempt
    FROM public.website_login_attempts;

    IF v_attempt_count >= 5 THEN
        allowed := false;
        retry_after_seconds := greatest(
            1,
            ceil(extract(epoch FROM (v_oldest_attempt + interval '60 seconds' - v_now)))::integer
        );
    ELSE
        INSERT INTO public.website_login_attempts (attempted_at) VALUES (v_now);
        allowed := true;
        retry_after_seconds := 0;
    END IF;

    RETURN NEXT;
END;
$function$;

REVOKE ALL ON FUNCTION public.consume_website_login_attempt() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_website_login_attempt() TO service_role;
