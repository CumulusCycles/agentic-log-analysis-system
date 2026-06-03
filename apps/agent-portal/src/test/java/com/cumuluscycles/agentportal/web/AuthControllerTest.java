package com.cumuluscycles.agentportal.web;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.SdaException;
import com.cumuluscycles.agentportal.sda.dto.LoginRequest;
import com.cumuluscycles.agentportal.sda.dto.TokenResponse;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    SdaClient sdaClient;

    @Test
    void loginSuccessProxiesTokenResponse() throws Exception {
        when(sdaClient.login(any(LoginRequest.class)))
                .thenReturn(new TokenResponse("jwt-token", "bearer", 3600));
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"agent1\",\"password\":\"agent\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access_token").value("jwt-token"))
                .andExpect(jsonPath("$.expires_in").value(3600));
    }

    @Test
    void loginSdaUnauthorizedPassesThrough401() throws Exception {
        when(sdaClient.login(any(LoginRequest.class)))
                .thenThrow(new SdaException(401, "invalid credentials"));
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"agent1\",\"password\":\"wrong\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("invalid credentials"));
    }

    @Test
    void loginSdaUnreachableReturns502() throws Exception {
        when(sdaClient.login(any(LoginRequest.class)))
                .thenThrow(new SdaException(502, "shared data api unreachable"));
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"agent1\",\"password\":\"agent\"}"))
                .andExpect(status().isBadGateway())
                .andExpect(jsonPath("$.detail").value("shared data api unreachable"));
    }

    @Test
    void loginRejectsMissingFields() throws Exception {
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"username\":\"\",\"password\":\"\"}"))
                .andExpect(status().isBadRequest());
        Mockito.verifyNoInteractions(sdaClient);
    }
}
