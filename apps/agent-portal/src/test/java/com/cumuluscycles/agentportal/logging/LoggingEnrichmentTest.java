package com.cumuluscycles.agentportal.logging;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.http.HttpHeaders.AUTHORIZATION;
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.SdaException;
import com.cumuluscycles.agentportal.sda.dto.ClaimDetail;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import com.cumuluscycles.agentportal.sda.dto.LoginRequest;
import com.cumuluscycles.agentportal.sda.dto.TokenResponse;
import com.cumuluscycles.agentportal.sda.dto.UserOut;
import com.cumuluscycles.agentportal.support.TestTokens;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

/**
 * Phase 6.75 — verify AP's new log events fire with the expected fields.
 *
 * Controllers use {@link OutputCaptureExtension} since they go through the
 * standard SpringBootTest stack; SdaClient is exercised against a
 * {@link MockRestServiceServer}-bound real client so its log-then-throw path
 * actually runs (mocking SdaClient would bypass the WARN log under test).
 *
 * NEVER assert positively on credential values — tests confirm bearer,
 * password, and API key NEVER appear in any logged event.
 */
class LoggingEnrichmentTest {

    @Nested
    @SpringBootTest
    @AutoConfigureMockMvc
    @ActiveProfiles("test")
    @ExtendWith(OutputCaptureExtension.class)
    class Controllers {

        @Autowired
        MockMvc mvc;

        @MockitoBean
        SdaClient sdaClient;

        @Test
        void loginProxiedSuccessLogged(CapturedOutput output) throws Exception {
            when(sdaClient.login(any(LoginRequest.class)))
                    .thenReturn(new TokenResponse("jwt-token", "bearer", 3600));
            mvc.perform(post("/api/auth/login")
                            .contentType(APPLICATION_JSON)
                            .content("{\"username\":\"agent1\",\"password\":\"DO-NOT-LOG-PW-X1\"}"))
                    .andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("login_proxied_success")
                    .contains("username=agent1")
                    .doesNotContain("DO-NOT-LOG-PW-X1");
        }

        @Test
        void claimsFetchedLogsCount(CapturedOutput output) throws Exception {
            when(sdaClient.getClaims(any()))
                    .thenReturn(List.of(stubClaimOut("c1"), stubClaimOut("c2")));
            String bearer = TestTokens.valid();
            mvc.perform(get("/api/claims").header(AUTHORIZATION, "Bearer " + bearer))
                    .andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("claims_fetched")
                    .contains("count=2")
                    .doesNotContain(bearer);
        }

        @Test
        void claimFetchedLogsIdAndStatus(CapturedOutput output) throws Exception {
            when(sdaClient.getClaim(any(), any())).thenReturn(stubClaimDetail("c42", "submitted"));
            String bearer = TestTokens.valid();
            mvc.perform(get("/api/claims/c42").header(AUTHORIZATION, "Bearer " + bearer))
                    .andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("claim_fetched")
                    .contains("claim_id=c42")
                    .contains("current_status=submitted")
                    .doesNotContain(bearer);
        }

        @Test
        void profileFetchedLogsUserId(CapturedOutput output) throws Exception {
            when(sdaClient.getUser(any(), any()))
                    .thenReturn(new UserOut("u-7", "agent1", "agent", "Agent One"));
            String bearer = TestTokens.valid();
            mvc.perform(get("/api/profile/me").header(AUTHORIZATION, "Bearer " + bearer))
                    .andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("profile_fetched")
                    // user_id comes from the JWT, not the response
                    .contains("user_id=")
                    .doesNotContain(bearer);
        }

        // ---------------------------------------------------------------
        // request middleware: X-Source header propagation (ADR-011)
        // ---------------------------------------------------------------

        @Test
        void requestEventEmitsSourceFromHeader(CapturedOutput output) throws Exception {
            mvc.perform(get("/api/health").header("X-Source", "test"))
                    .andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("path=/api/health")
                    .contains("source=test");
        }

        @Test
        void requestEventEmitsSourceUnknownWhenHeaderAbsent(CapturedOutput output) throws Exception {
            // Missing X-Source → `unknown` per ADR-011 2026-06-07 amendment.
            // The React SPA tags `prod` explicitly via its fetch wrapper.
            mvc.perform(get("/api/health")).andExpect(status().isOk());
            assertThat(output.getOut())
                    .contains("path=/api/health")
                    .contains("source=unknown");
        }
    }

    @Nested
    @ExtendWith(OutputCaptureExtension.class)
    class Client {

        @Test
        void sdaUpstreamRejectedLogged(CapturedOutput output) {
            RestClient.Builder builder = RestClient.builder().baseUrl("http://sda-test");
            MockRestServiceServer server =
                    MockRestServiceServer.bindTo(builder).build();
            SdaClient client = new SdaClient(builder.build(), new ObjectMapper());

            server.expect(requestTo("http://sda-test/claims"))
                    .andRespond(withStatus(HttpStatus.FORBIDDEN)
                            .contentType(APPLICATION_JSON)
                            .body("{\"detail\":\"only fnol may create claims\"}"));

            assertThatThrownBy(() -> client.getClaims("bearer-X9Z"))
                    .isInstanceOf(SdaException.class);

            assertThat(output.getOut())
                    .contains("sda_upstream_rejected")
                    .contains("target=/claims")
                    .contains("status=403")
                    .contains("detail=only fnol may create claims")
                    .doesNotContain("bearer-X9Z");
        }

        @Test
        void sdaUpstreamUnreachableLogged(CapturedOutput output) {
            RestClient.Builder builder = RestClient.builder()
                    .baseUrl("http://sda-test")
                    .requestInterceptor((request, body, execution) -> {
                        throw new ResourceAccessException("connect failed");
                    });
            SdaClient client = new SdaClient(builder.build(), new ObjectMapper());

            assertThatThrownBy(() -> client.getClaims("bearer-Q7W"))
                    .isInstanceOf(SdaException.class);

            assertThat(output.getOut())
                    .contains("sda_upstream_unreachable")
                    .contains("target=/claims")
                    .contains("error_class=ResourceAccessException")
                    .doesNotContain("bearer-Q7W");
        }
    }

    private static ClaimOut stubClaimOut(String id) {
        return new ClaimOut(id, "POL-1", "cust-1", "VIN-1", null, null, null, "submitted", null, null);
    }

    private static ClaimDetail stubClaimDetail(String id, String status) {
        return new ClaimDetail(id, "POL-1", "cust-1", "VIN-1", null, null, null, status, null, null, List.of());
    }
}
