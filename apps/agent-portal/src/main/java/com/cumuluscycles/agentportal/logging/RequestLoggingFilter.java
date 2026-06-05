package com.cumuluscycles.agentportal.logging;

import com.cumuluscycles.agentportal.auth.AuthAttributes;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.web.filter.OncePerRequestFilter;

/**
 * Per-request filter that binds {@code X-Source} (default {@code prod}) onto
 * SLF4J {@code MDC} so any domain log statement emitted during the request
 * can read it back via {@link SourceContext#currentSource()}. Domain WARN
 * call sites — {@code SdaClient}, {@code ChaosFilter},
 * {@code GlobalExceptionHandler} — read MDC and append
 * {@code source=<value>} as the trailing key so the dashboard parser picks
 * it up uniformly with SDA/FNOL/CP. Mirrors the
 * {@code structlog.contextvars} pattern used by the Python apps.
 */
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !path.startsWith("/api/") && !path.startsWith("/actuator/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String source = SourceContext.normalize(request.getHeader("X-Source"));
        MDC.put(SourceContext.MDC_KEY, source);
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            double durationMs = (System.nanoTime() - start) / 1_000_000.0;
            Object userId = request.getAttribute(AuthAttributes.USER_ID);
            log.info(
                    "request method={} path={} caller=- source={} "
                            + "user={} status={} duration_ms={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    source,
                    userId != null ? userId : "-",
                    response.getStatus(),
                    String.format("%.2f", durationMs));
            MDC.remove(SourceContext.MDC_KEY);
        }
    }
}
