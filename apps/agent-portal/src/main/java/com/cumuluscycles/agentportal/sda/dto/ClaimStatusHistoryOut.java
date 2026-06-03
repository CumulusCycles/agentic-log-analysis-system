package com.cumuluscycles.agentportal.sda.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.OffsetDateTime;

public record ClaimStatusHistoryOut(
        @JsonProperty("from_status") String fromStatus,
        @JsonProperty("to_status") String toStatus,
        @JsonProperty("actor_id") String actorId,
        @JsonProperty("changed_at") OffsetDateTime changedAt,
        String note
) {}
