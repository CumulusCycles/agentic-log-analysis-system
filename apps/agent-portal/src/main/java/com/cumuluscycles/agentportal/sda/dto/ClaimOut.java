package com.cumuluscycles.agentportal.sda.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.OffsetDateTime;

public record ClaimOut(
        String id,
        @JsonProperty("policy_number") String policyNumber,
        @JsonProperty("customer_id") String customerId,
        String vin,
        @JsonProperty("vehicle_snapshot") VehicleSnapshot vehicleSnapshot,
        @JsonProperty("incident_at") OffsetDateTime incidentAt,
        String description,
        @JsonProperty("current_status") String currentStatus,
        @JsonProperty("assigned_adjuster_id") String assignedAdjusterId,
        @JsonProperty("created_at") OffsetDateTime createdAt
) {}
