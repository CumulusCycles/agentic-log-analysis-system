package com.cumuluscycles.agentportal.config;

import com.cumuluscycles.agentportal.auth.JwtAuthenticationFilter;
import com.cumuluscycles.agentportal.chaos.ChaosFilter;
import com.cumuluscycles.agentportal.logging.RequestLoggingFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebConfig {

    @Bean
    public FilterRegistrationBean<JwtAuthenticationFilter> jwtFilterRegistration(
            AppProperties props, ObjectMapper objectMapper) {
        FilterRegistrationBean<JwtAuthenticationFilter> reg =
                new FilterRegistrationBean<>(new JwtAuthenticationFilter(props, objectMapper));
        reg.addUrlPatterns("/api/*");
        reg.setOrder(1);
        return reg;
    }

    @Bean
    public FilterRegistrationBean<RequestLoggingFilter> requestLoggingFilterRegistration() {
        FilterRegistrationBean<RequestLoggingFilter> reg = new FilterRegistrationBean<>(new RequestLoggingFilter());
        reg.addUrlPatterns("/api/*", "/actuator/*");
        reg.setOrder(10);
        return reg;
    }

    @Bean
    public FilterRegistrationBean<ChaosFilter> chaosFilterRegistration(
            AppProperties props, ObjectMapper objectMapper) {
        // Order 20 -> runs AFTER auth (order 1) and request logging (order 10).
        // Scoped to /api/* only so /actuator/health is never chaosed (Docker
        // healthcheck stays honest). Per ADR-013.
        FilterRegistrationBean<ChaosFilter> reg =
                new FilterRegistrationBean<>(new ChaosFilter(props, objectMapper));
        reg.addUrlPatterns("/api/*");
        reg.setOrder(20);
        return reg;
    }
}
