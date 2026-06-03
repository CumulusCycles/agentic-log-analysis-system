package com.cumuluscycles.agentportal.config;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app")
public record AppProperties(
        @Valid SharedDataApi sharedDataApi,
        @Valid Jwt jwt,
        @NotBlank String logFilePath
) {
    public record SharedDataApi(
            @NotBlank String baseUrl,
            @NotBlank String apiKey,
            @Positive int timeoutMs
    ) {}

    public record Jwt(
            @NotBlank String secret,
            @NotBlank String algorithm
    ) {}
}
