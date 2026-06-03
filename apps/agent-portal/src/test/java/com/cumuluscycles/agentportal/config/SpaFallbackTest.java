package com.cumuluscycles.agentportal.config;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import org.assertj.core.api.Assertions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SpaFallbackTest {

    @Autowired
    MockMvc mvc;

    // Filter chain still tries to wire SdaClient through the controllers; supply a mock.
    @MockitoBean
    SdaClient sdaClient;

    @Test
    void rootServesIndexHtml() throws Exception {
        // Spring Boot's WelcomePageHandlerMapping forwards "/" to /index.html
        // in MockMvc; the forwarded request itself is asserted on by checking
        // forwardedUrl. /login below proves the SPA fallback actually streams
        // the index.html body for client-side routes.
        mvc.perform(get("/"))
                .andExpect(status().isOk())
                .andExpect(org.springframework.test.web.servlet.result.MockMvcResultMatchers
                        .forwardedUrl("index.html"));
    }

    @Test
    void spaRouteFallsBackToIndexHtml() throws Exception {
        mvc.perform(get("/login"))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("<div id=\"root\">")));
    }

    @Test
    void apiMissingReturns404NotIndexHtml() throws Exception {
        // No /api/missing controller — Spring returns 404. The SPA resolver
        // explicitly excludes /api/** so it never serves index.html for these.
        MvcResult result = mvc.perform(get("/api/missing").header("Authorization", "Bearer fake"))
                .andReturn();
        // Either 401 from filter (no valid token) or 404; both prove we did not
        // fall through to index.html.
        Assertions.assertThat(result.getResponse().getStatus()).isNotEqualTo(200);
        Assertions.assertThat(result.getResponse().getContentAsString()).doesNotContain("<div id=\"root\">");
    }

    @Test
    void pathTraversalDoesNotLeakHostFiles() throws Exception {
        // Even though /etc/passwd is well outside classpath:/static/, prove the
        // response is either the SPA index (200) or 4xx — never the file's
        // contents.
        for (String path : new String[]{
                "/../etc/passwd",
                "/..%2F..%2Fetc%2Fpasswd",
                "/static/../../../etc/passwd"
        }) {
            MvcResult result = mvc.perform(get(path)).andReturn();
            String body = result.getResponse().getContentAsString();
            Assertions.assertThat(body).doesNotContain("root:x:");
            Assertions.assertThat(body).doesNotContain("/bin/bash");
        }
    }
}
