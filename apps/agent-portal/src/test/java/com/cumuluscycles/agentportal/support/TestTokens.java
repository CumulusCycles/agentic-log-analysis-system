package com.cumuluscycles.agentportal.support;

import com.cumuluscycles.agentportal.auth.JwtConstants;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.Map;
import javax.crypto.SecretKey;

public final class TestTokens {

    public static final String SECRET = "test-secret-please-change-test-secret-please-change";
    public static final String USER_ID = "agent-1-uuid";

    private TestTokens() {}

    public static SecretKey key() {
        return Keys.hmacShaKeyFor(SECRET.getBytes(StandardCharsets.UTF_8));
    }

    public static String valid() {
        return build(Map.of(), JwtConstants.ISSUER, JwtConstants.AUDIENCE, secondsFromNow(600), SECRET);
    }

    public static String withClaims(Map<String, Object> extra) {
        return build(extra, JwtConstants.ISSUER, JwtConstants.AUDIENCE, secondsFromNow(600), SECRET);
    }

    public static String wrongIssuer() {
        return build(Map.of(), "not-the-sda", JwtConstants.AUDIENCE, secondsFromNow(600), SECRET);
    }

    public static String wrongAudience() {
        return build(Map.of(), JwtConstants.ISSUER, "not-the-audience", secondsFromNow(600), SECRET);
    }

    public static String expired() {
        return build(Map.of(), JwtConstants.ISSUER, JwtConstants.AUDIENCE, Instant.now().minusSeconds(60), SECRET);
    }

    public static String wrongSecret() {
        String otherSecret = "different-secret-different-secret-different-secret";
        return build(Map.of(), JwtConstants.ISSUER, JwtConstants.AUDIENCE, secondsFromNow(600), otherSecret);
    }

    private static Instant secondsFromNow(int seconds) {
        return Instant.now().plusSeconds(seconds);
    }

    private static String build(Map<String, Object> extra, String issuer, String audience, Instant exp, String secret) {
        SecretKey k = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
        Instant now = Instant.now();
        var builder = Jwts.builder()
                .issuer(issuer)
                .audience().add(audience).and()
                .issuedAt(Date.from(now))
                .expiration(Date.from(exp))
                .claim("user_id", USER_ID)
                .claim("role", "agent")
                .claim("app", "agent-portal");
        extra.forEach(builder::claim);
        return builder.signWith(k).compact();
    }
}
