package com.cumuluscycles.agentportal.chaos;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import com.cumuluscycles.agentportal.support.TestTokens;
import java.util.List;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

/**
 * Chaos filter contract: ENABLE_CHAOS env gate + X-Chaos directive grammar.
 *
 * <p>Behavior asserted (per ADR-013):
 * <ul>
 *   <li>app.chaos.enabled=false -> X-Chaos header ignored, normal flow.
 *   <li>app.chaos.enabled=true + slow:<ms>    -> sleep, then continue.
 *   <li>app.chaos.enabled=true + error:<code> -> that status with detail=chaos.
 *   <li>app.chaos.enabled=true + malformed    -> 400 + chaos_directive_invalid WARN.
 *   <li>chaos_honored WARN includes directive + method + path + status/delay_ms.
 * </ul>
 *
 * Uses {@link OutputCaptureExtension} for log assertions; {@link MockitoBean}
 * stubs SdaClient because the chaos-gated path is /api/claims (the GET reads
 * SDA when chaos is off; when chaos errors, SDA is not called).
 */
class ChaosFilterTest {

    @Nested
    @SpringBootTest(properties = "app.chaos.enabled=true")
    @AutoConfigureMockMvc
    @ActiveProfiles("test")
    @ExtendWith(OutputCaptureExtension.class)
    class ChaosEnabled {

        @Autowired
        MockMvc mvc;

        @MockitoBean
        SdaClient sdaClient;

        @Test
        void slowDirectiveDelaysAndContinues(CapturedOutput output) throws Exception {
            when(sdaClient.getClaims(any())).thenReturn(List.<ClaimOut>of());
            long start = System.currentTimeMillis();
            mvc.perform(get("/api/claims")
                            .header("X-Chaos", "slow:120")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().isOk());
            long elapsed = System.currentTimeMillis() - start;
            assertThat(elapsed).as("expected >=110ms delay, got %dms", elapsed).isGreaterThanOrEqualTo(110L);
            assertThat(output.getOut())
                    .contains("chaos_honored")
                    .contains("directive=slow:120")
                    .contains("delay_ms=120");
        }

        @Test
        void errorDirective5xxLogsAtErrorLevel(CapturedOutput output) throws Exception {
            // PR 4c: 5xx chaos returns are escalated to ERROR so the
            // dashboard's proactive scan sees ERROR-tier signal in Chroma.
            mvc.perform(get("/api/claims")
                            .header("X-Chaos", "error:503")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().is(503))
                    .andExpect(content().json("{\"detail\":\"chaos\"}"));
            String chaosLine = output.getOut().lines()
                    .filter(line -> line.contains("chaos_honored"))
                    .findFirst()
                    .orElseThrow(() -> new AssertionError("no chaos_honored log line"));
            assertThat(chaosLine)
                    .contains("ERROR")
                    .contains("directive=error:503")
                    .contains("status=503");
            // SDA must not have been called when chaos short-circuits
            verifyNoInteractions(sdaClient);
        }

        @Test
        void errorDirective4xxLogsAtWarnLevel(CapturedOutput output) throws Exception {
            // 4xx stays WARN — operator-driven client error, not a server failure.
            mvc.perform(get("/api/claims")
                            .header("X-Chaos", "error:418")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().is(418))
                    .andExpect(content().json("{\"detail\":\"chaos\"}"));
            String chaosLine = output.getOut().lines()
                    .filter(line -> line.contains("chaos_honored"))
                    .findFirst()
                    .orElseThrow(() -> new AssertionError("no chaos_honored log line"));
            assertThat(chaosLine)
                    .contains("WARN")
                    .contains("directive=error:418")
                    .contains("status=418");
            verifyNoInteractions(sdaClient);
        }

        @Test
        void malformedDirectiveReturns400(CapturedOutput output) throws Exception {
            mvc.perform(get("/api/claims")
                            .header("X-Chaos", "garbage")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().is(400));
            assertThat(output.getOut())
                    .contains("chaos_directive_invalid")
                    .contains("directive_raw=garbage")
                    .contains("reason=malformed");
        }

        @Test
        void noHeaderPassesThrough(CapturedOutput output) throws Exception {
            when(sdaClient.getClaims(any())).thenReturn(List.<ClaimOut>of());
            mvc.perform(get("/api/claims")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().isOk());
            assertThat(output.getOut()).doesNotContain("chaos_honored").doesNotContain("chaos_directive_invalid");
        }
    }

    @Nested
    @SpringBootTest(properties = "app.chaos.enabled=false")
    @AutoConfigureMockMvc
    @ActiveProfiles("test")
    @ExtendWith(OutputCaptureExtension.class)
    class ChaosDisabled {

        @Autowired
        MockMvc mvc;

        @MockitoBean
        SdaClient sdaClient;

        @Test
        void headerIgnoredWhenChaosOff(CapturedOutput output) throws Exception {
            when(sdaClient.getClaims(any())).thenReturn(List.<ClaimOut>of());
            mvc.perform(get("/api/claims")
                            .header("X-Chaos", "error:503")
                            .header("Authorization", "Bearer " + TestTokens.valid()))
                    .andExpect(status().isOk());
            assertThat(output.getOut()).doesNotContain("chaos_honored").doesNotContain("chaos_directive_invalid");
        }
    }
}
