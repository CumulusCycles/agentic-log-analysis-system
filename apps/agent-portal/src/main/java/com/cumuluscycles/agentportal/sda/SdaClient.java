package com.cumuluscycles.agentportal.sda;

import com.cumuluscycles.agentportal.logging.SourceContext;
import com.cumuluscycles.agentportal.sda.dto.ClaimDetail;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import com.cumuluscycles.agentportal.sda.dto.LoginRequest;
import com.cumuluscycles.agentportal.sda.dto.TokenResponse;
import com.cumuluscycles.agentportal.sda.dto.UserOut;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpRequest;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * Every outbound call emits {@code sda_upstream_rejected} (WARN) on 4xx/5xx
 * or {@code sda_upstream_unreachable} (WARN) on transport error, then
 * propagates an {@link SdaException}. NEVER logs the bearer header, the API
 * key, or any password — only target/status/parsed detail.
 */
public class SdaClient {

    private static final Logger log = LoggerFactory.getLogger(SdaClient.class);

    private final RestClient http;
    private final ObjectMapper mapper;

    public SdaClient(RestClient http, ObjectMapper mapper) {
        this.http = http;
        this.mapper = mapper;
    }

    public TokenResponse login(LoginRequest req) {
        return invoke("/auth/login", () -> http.post()
                .uri("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .body(req)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::throwSda)
                .body(TokenResponse.class));
    }

    public UserOut getUser(String userId, String bearer) {
        String target = "/users/" + userId;
        return invoke(target, () -> http.get()
                .uri(uriBuilder -> uriBuilder.path("/users/{id}").build(userId))
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + bearer)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::throwSda)
                .body(UserOut.class));
    }

    public List<ClaimOut> getClaims(String bearer) {
        return invoke("/claims", () -> http.get()
                .uri("/claims")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + bearer)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::throwSda)
                .body(new ParameterizedTypeReference<List<ClaimOut>>() {}));
    }

    public ClaimDetail getClaim(String id, String bearer) {
        String target = "/claims/" + id;
        return invoke(target, () -> http.get()
                .uri(uriBuilder -> uriBuilder.path("/claims/{id}").build(id))
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + bearer)
                .retrieve()
                .onStatus(HttpStatusCode::isError, this::throwSda)
                .body(ClaimDetail.class));
    }

    private <T> T invoke(String target, java.util.function.Supplier<T> call) {
        try {
            return call.get();
        } catch (SdaException ex) {
            throw ex;
        } catch (ResourceAccessException ex) {
            log.warn("sda_upstream_unreachable target={} error_class={} source={}",
                    target, ex.getClass().getSimpleName(), SourceContext.currentSource());
            throw new SdaException(502, "shared data api unreachable");
        }
    }

    private void throwSda(HttpRequest request, ClientHttpResponse resp) throws IOException {
        int status = resp.getStatusCode().value();
        String body = new String(resp.getBody().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
        String detail = extractDetail(body);
        String target = request.getURI().getPath();
        log.warn("sda_upstream_rejected target={} status={} detail={} source={}",
                target, status, detail, SourceContext.currentSource());
        throw new SdaException(status, detail);
    }

    private String extractDetail(String body) {
        if (body == null || body.isBlank()) {
            return "upstream error";
        }
        try {
            JsonNode node = mapper.readTree(body);
            JsonNode d = node.get("detail");
            if (d != null && d.isTextual()) {
                return d.asText();
            }
        } catch (IOException ignored) {
            // fall through
        }
        return "upstream error";
    }
}
