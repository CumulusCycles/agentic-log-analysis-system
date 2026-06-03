package com.cumuluscycles.agentportal.sda.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record UserOut(
        String id,
        String username,
        String role,
        @JsonProperty("display_name") String displayName
) {}
