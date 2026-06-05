package com.cumuluscycles.agentportal.logging;

import java.util.regex.Pattern;
import org.slf4j.MDC;

/**
 * Helpers around the per-request {@code source} value bound onto SLF4J
 * {@link MDC} by {@link RequestLoggingFilter}.
 *
 * <p>WARN/ERROR call sites in {@code SdaClient}, {@code ChaosFilter} and
 * {@code GlobalExceptionHandler} read {@link #currentSource()} when
 * formatting log lines so the dashboard parser sees the same
 * {@code source=<value>} kv pair the SDA / FNOL / CP loggers produce.
 *
 * <p>The outbound SDA {@code RestClient} interceptor configured in
 * {@code SdaClientConfig} also reads {@link #currentSource()} to forward
 * {@code X-Source} on every call so SDA tags any WARN/ERROR it emits with
 * the original source instead of defaulting to {@code prod}.
 */
public final class SourceContext {

    public static final String MDC_KEY = "source";

    private static final String DEFAULT = "prod";
    private static final Pattern VALID = Pattern.compile("^[a-z][a-z0-9_-]*$");

    private SourceContext() {}

    /** Returns the source bound onto MDC, or {@code prod} when none is set. */
    public static String currentSource() {
        String value = MDC.get(MDC_KEY);
        return value == null || value.isBlank() ? DEFAULT : value;
    }

    /**
     * Coerces the inbound {@code X-Source} header to the canonical lowercase
     * value the dashboard expects. Anything that doesn't match
     * {@code ^[a-z][a-z0-9_-]*$} falls back to {@code prod} so a malicious
     * caller can't inject arbitrary characters through the header into our
     * log stream.
     */
    public static String normalize(String raw) {
        if (raw == null) {
            return DEFAULT;
        }
        String trimmed = raw.trim().toLowerCase();
        if (trimmed.isEmpty()) {
            return DEFAULT;
        }
        return VALID.matcher(trimmed).matches() ? trimmed : DEFAULT;
    }
}
