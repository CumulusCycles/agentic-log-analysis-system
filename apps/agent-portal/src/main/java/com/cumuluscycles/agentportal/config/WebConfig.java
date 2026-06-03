package com.cumuluscycles.agentportal.config;

import com.cumuluscycles.agentportal.auth.JwtAuthenticationFilter;
import com.cumuluscycles.agentportal.logging.RequestLoggingFilter;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class WebConfig {

    @Bean
    public FilterRegistrationBean<JwtAuthenticationFilter> jwtFilterRegistration(AppProperties props) {
        FilterRegistrationBean<JwtAuthenticationFilter> reg = new FilterRegistrationBean<>(new JwtAuthenticationFilter(props));
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
}
