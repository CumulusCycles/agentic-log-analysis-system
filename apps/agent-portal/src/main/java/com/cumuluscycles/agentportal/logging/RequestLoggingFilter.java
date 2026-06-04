package com.cumuluscycles.agentportal.logging;

import com.cumuluscycles.agentportal.auth.AuthAttributes;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

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
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            double durationMs = (System.nanoTime() - start) / 1_000_000.0;
            Object userId = request.getAttribute(AuthAttributes.USER_ID);
            String source = request.getHeader("X-Source");
            if (source == null || source.isBlank()) {
                source = "prod";
            }
            log.info(
                    "request method={} path={} caller=- source={} "
                            + "user={} status={} duration_ms={}",
                    request.getMethod(),
                    request.getRequestURI(),
                    source,
                    userId != null ? userId : "-",
                    response.getStatus(),
                    String.format("%.2f", durationMs));
        }
    }
}
