package com.cumuluscycles.agentportal.web;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.cumuluscycles.agentportal.sda.SdaException;
import com.cumuluscycles.agentportal.sda.dto.ClaimDetail;
import com.cumuluscycles.agentportal.sda.dto.ClaimOut;
import com.cumuluscycles.agentportal.sda.dto.ClaimStatusHistoryOut;
import com.cumuluscycles.agentportal.sda.dto.VehicleSnapshot;
import com.cumuluscycles.agentportal.support.TestTokens;
import java.time.OffsetDateTime;
import java.util.List;
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
class ClaimsControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    SdaClient sdaClient;

    @Test
    void listReturnsClaimsFromSda() throws Exception {
        ClaimOut claim = new ClaimOut(
                "claim-1", "POL-1004", "alice-uuid", "VIN12345",
                new VehicleSnapshot("Toyota", "Camry", 2022),
                OffsetDateTime.parse("2026-05-01T10:00:00Z"),
                "rear-ended", "CREATED", null,
                OffsetDateTime.parse("2026-05-01T10:05:00Z"));
        when(sdaClient.getClaims(anyString())).thenReturn(List.of(claim));
        mvc.perform(get("/api/claims").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value("claim-1"))
                .andExpect(jsonPath("$[0].policy_number").value("POL-1004"))
                .andExpect(jsonPath("$[0].current_status").value("CREATED"))
                .andExpect(jsonPath("$[0].vehicle_snapshot.make").value("Toyota"));
    }

    @Test
    void listReturnsEmptyArray() throws Exception {
        when(sdaClient.getClaims(anyString())).thenReturn(List.of());
        mvc.perform(get("/api/claims").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$").isArray())
                .andExpect(jsonPath("$.length()").value(0));
    }

    @Test
    void listWithoutTokenReturns401() throws Exception {
        mvc.perform(get("/api/claims"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void detailReturnsClaimWithHistory() throws Exception {
        ClaimDetail detail = new ClaimDetail(
                "claim-1", "POL-1004", "alice-uuid", "VIN12345",
                new VehicleSnapshot("Toyota", "Camry", 2022),
                OffsetDateTime.parse("2026-05-01T10:00:00Z"),
                "rear-ended", "ASSIGNED", "agent1-uuid",
                OffsetDateTime.parse("2026-05-01T10:05:00Z"),
                List.of(
                        new ClaimStatusHistoryOut(null, "CREATED", "system",
                                OffsetDateTime.parse("2026-05-01T10:05:00Z"), null),
                        new ClaimStatusHistoryOut("CREATED", "ASSIGNED", "system",
                                OffsetDateTime.parse("2026-05-01T10:15:00Z"), "auto-assigned")
                ));
        when(sdaClient.getClaim(eq("claim-1"), anyString())).thenReturn(detail);
        mvc.perform(get("/api/claims/claim-1").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("claim-1"))
                .andExpect(jsonPath("$.current_status").value("ASSIGNED"))
                .andExpect(jsonPath("$.history.length()").value(2))
                .andExpect(jsonPath("$.history[1].from_status").value("CREATED"))
                .andExpect(jsonPath("$.history[1].to_status").value("ASSIGNED"));
    }

    @Test
    void detailSda404PassesThrough() throws Exception {
        when(sdaClient.getClaim(anyString(), anyString()))
                .thenThrow(new SdaException(404, "claim not found"));
        mvc.perform(get("/api/claims/missing-id").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value("claim not found"));
    }

    @Test
    void listSda500PassesThrough() throws Exception {
        when(sdaClient.getClaims(anyString()))
                .thenThrow(new SdaException(500, "internal error"));
        mvc.perform(get("/api/claims").header("Authorization", "Bearer " + TestTokens.valid()))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.detail").value("internal error"));
    }
}
