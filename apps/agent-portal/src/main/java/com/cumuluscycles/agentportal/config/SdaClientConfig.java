package com.cumuluscycles.agentportal.config;

import com.cumuluscycles.agentportal.sda.SdaClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
public class SdaClientConfig {

    @Bean
    public SdaClient sdaClient(ObjectMapper mapper, AppProperties props) {
        Duration timeout = Duration.ofMillis(props.sharedDataApi().timeoutMs());

        // Pin HTTP/1.1 — the JDK HttpClient default policy is
        // HttpClient.Version.HTTP_2 which sends Upgrade: h2c on every cleartext
        // request, and uvicorn (the SDA's ASGI server) rejects upgrades with
        // 400 / "Unsupported upgrade request" before the body reaches pydantic.
        HttpClient jdk = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(timeout)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(jdk);
        factory.setReadTimeout(timeout);

        RestClient http = RestClient.builder()
                .baseUrl(props.sharedDataApi().baseUrl())
                .defaultHeader("X-API-Key", props.sharedDataApi().apiKey())
                .requestFactory(factory)
                .build();
        return new SdaClient(http, mapper);
    }
}
