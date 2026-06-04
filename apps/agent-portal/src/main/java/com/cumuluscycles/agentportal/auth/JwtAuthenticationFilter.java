package com.cumuluscycles.agentportal.auth;

import com.cumuluscycles.agentportal.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import javax.crypto.SecretKey;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.filter.OncePerRequestFilter;

public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(JwtAuthenticationFilter.class);

    private final SecretKey secretKey;
    private final ObjectMapper objectMapper;

    public JwtAuthenticationFilter(AppProperties props, ObjectMapper objectMapper) {
        this.secretKey = Keys.hmacShaKeyFor(props.jwt().secret().getBytes(StandardCharsets.UTF_8));
        this.objectMapper = objectMapper;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        if (path.startsWith("/actuator/")) return true;
        if ("/api/health".equals(path)) return true;
        if ("/api/auth/login".equals(path)) return true;
        return !path.startsWith("/api/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header == null || !header.regionMatches(true, 0, "Bearer ", 0, 7)) {
            unauthorized(response, "missing bearer token");
            return;
        }
        String token = header.substring(7).trim();
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(secretKey)
                    .requireIssuer(JwtConstants.ISSUER)
                    .requireAudience(JwtConstants.AUDIENCE)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            request.setAttribute(AuthAttributes.USER_ID, claims.get("user_id", String.class));
            request.setAttribute(AuthAttributes.ROLE, claims.get("role", String.class));
            request.setAttribute(AuthAttributes.BEARER, token);
            chain.doFilter(request, response);
        } catch (JwtException ex) {
            log.info("jwt_decode_failed reason={}", ex.getMessage());
            unauthorized(response, "invalid token");
        }
    }

    private void unauthorized(HttpServletResponse response, String detail) throws IOException {
        response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        // Jackson serializes the map so any embedded quotes/backslashes in
        // `detail` are escaped correctly — replaces a raw string concat that
        // would have produced broken JSON for non-trivial detail values.
        response.getWriter().write(objectMapper.writeValueAsString(Map.of("detail", detail)));
    }
}
