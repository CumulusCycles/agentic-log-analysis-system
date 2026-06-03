package com.cumuluscycles.agentportal.web;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.SdaException;
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
class ProfileControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    SdaClient sdaClient;

    @Test
    void profileMeReturnsUserFromSda() throws Exception {
        when(sdaClient.getUser(eq(TestTokens.USER_ID), anyString()))
                .thenReturn(new UserOut(TestTokens.USER_ID, "agent1", "agent", "Agent One"));
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(TestTokens.USER_ID))
                .andExpect(jsonPath("$.username").value("agent1"))
                .andExpect(jsonPath("$.role").value("agent"))
                .andExpect(jsonPath("$.display_name").value("Agent One"));
    }

    @Test
    void profileMeWithoutTokenReturns401() throws Exception {
        mvc.perform(get("/api/profile/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void profileMeSda404PassesThrough() throws Exception {
        when(sdaClient.getUser(anyString(), anyString()))
                .thenThrow(new SdaException(404, "user not found"));
        mvc.perform(get("/api/profile/me").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("user not found"));
    }
}
