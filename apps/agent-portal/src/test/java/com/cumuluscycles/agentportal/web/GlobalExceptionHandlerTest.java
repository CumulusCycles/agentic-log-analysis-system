package com.cumuluscycles.agentportal.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.support.TestTokens;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Import(GlobalExceptionHandlerTest.ThrowingController.class)
class GlobalExceptionHandlerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    SdaClient sdaClient;

    @RestController
    static class ThrowingController {
        @GetMapping("/api/__test/throw")
        public String throwRuntime() {
            throw new RuntimeException("kaboom — must not leak to client");
        }
    }

    @Test
    void runtimeExceptionMappedTo500WithGenericBodyNoLeak() throws Exception {
        var result = mvc.perform(get("/api/__test/throw")
                        .header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.detail").value("internal server error"))
                .andReturn();
        // The exception message must not appear in the response body anywhere.
        assertThat(result.getResponse().getContentAsString()).doesNotContain("kaboom");
    }

    @Test
    void malformedJsonBodyMappedTo400() throws Exception {
        mvc.perform(post("/api/auth/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{ not valid json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("malformed request body"));
    }
}
