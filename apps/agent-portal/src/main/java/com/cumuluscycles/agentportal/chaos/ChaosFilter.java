package com.cumuluscycles.agentportal.chaos;

import com.cumuluscycles.agentportal.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Chaos filter — header-driven failure simulation gated by app.chaos.enabled.
 *
 * <p>Behavior identical to the SDA / FNOL / CP chaos middleware (same directive
 * grammar, clamps, log events, response shape). Per ADR-013.
 *
 * <p>{@code X-Chaos: slow:<ms>}    -- sleep N ms (0..60000), then continue normally.<br>
 * {@code X-Chaos: error:<status>}  -- return immediate HTTP {@code <status>} (400..599).
 *
 * <p>Filter order = 20 in {@link com.cumuluscycles.agentportal.config.WebConfig}, so
 * it runs AFTER the JWT auth filter (order 1) and the request logging filter
 * (order 10): unauthenticated requests with X-Chaos are rejected by JWT before
 * chaos sees them, and the request log line records the delayed/errored response.
 */
public class ChaosFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(ChaosFilter.class);
    private static final int MAX_SLOW_MS = 60_000;

    private final boolean enabled;
    private final ObjectMapper objectMapper;

    public ChaosFilter(AppProperties props, ObjectMapper objectMapper) {
        this.enabled = props.chaos() != null && props.chaos().enabled();
        this.objectMapper = objectMapper;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        if (!enabled) {
            chain.doFilter(request, response);
            return;
        }
        String directive = request.getHeader("X-Chaos");
        if (directive == null || directive.isBlank()) {
            chain.doFilter(request, response);
            return;
        }
        Directive parsed = parse(directive);
        if (parsed == null) {
            log.warn("chaos_directive_invalid directive_raw={} reason=malformed method={} path={} source={}",
                    directive, request.getMethod(), request.getRequestURI(),
                    com.cumuluscycles.agentportal.logging.SourceContext.currentSource());
            respond(response, 400, Map.of("detail", "invalid X-Chaos directive: " + directive));
            return;
        }
        if (parsed.kind() == Kind.SLOW) {
            try {
                Thread.sleep(parsed.n());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                // Interrupt during chaos -> treat as a chaos honor with a 500 outcome.
                respond(response, 500, Map.of("detail", "chaos interrupted"));
                return;
            }
            log.warn("chaos_honored directive={} delay_ms={} method={} path={} source={}",
                    directive, parsed.n(), request.getMethod(), request.getRequestURI(),
                    com.cumuluscycles.agentportal.logging.SourceContext.currentSource());
            chain.doFilter(request, response);
            return;
        }
        log.warn("chaos_honored directive={} status={} method={} path={} source={}",
                directive, parsed.n(), request.getMethod(), request.getRequestURI(),
                com.cumuluscycles.agentportal.logging.SourceContext.currentSource());
        respond(response, parsed.n(), Map.of("detail", "chaos"));
    }

    private void respond(HttpServletResponse response, int status, Map<String, Object> body) throws IOException {
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(objectMapper.writeValueAsString(body));
    }

    private static Directive parse(String value) {
        int idx = value.indexOf(':');
        if (idx < 0) {
            return null;
        }
        String kind = value.substring(0, idx);
        String raw = value.substring(idx + 1);
        int n;
        try {
            n = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            return null;
        }
        if ("slow".equals(kind) && n >= 0 && n <= MAX_SLOW_MS) {
            return new Directive(Kind.SLOW, n);
        }
        if ("error".equals(kind) && n >= 400 && n <= 599) {
            return new Directive(Kind.ERROR, n);
        }
        return null;
    }

    private enum Kind { SLOW, ERROR }

    private record Directive(Kind kind, int n) {}
}
