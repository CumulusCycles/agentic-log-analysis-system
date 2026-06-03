package com.cumuluscycles.agentportal.auth;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.dto.UserOut;
import com.cumuluscycles.agentportal.support.TestTokens;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class JwtAuthenticationFilterTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    SdaClient sdaClient;

    @Test
    void missingAuthHeaderReturns401() throws Exception {
        mvc.perform(get("/api/profile/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("missing bearer token"));
    }

    @Test
    void wrongSecretReturns401() throws Exception {
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.wrongSecret()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("invalid token"));
    }

    @Test
    void wrongIssuerReturns401() throws Exception {
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.wrongIssuer()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("invalid token"));
    }

    @Test
    void wrongAudienceReturns401() throws Exception {
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.wrongAudience()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("invalid token"));
    }

    @Test
    void expiredTokenReturns401() throws Exception {
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.expired()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("invalid token"));
    }

    @Test
    void validTokenPassesThroughToController() throws Exception {
        when(sdaClient.getUser(anyString(), anyString()))
                .thenReturn(new UserOut(TestTokens.USER_ID, "agent1", "agent", "Agent One"));
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("agent1"));
    }
}
