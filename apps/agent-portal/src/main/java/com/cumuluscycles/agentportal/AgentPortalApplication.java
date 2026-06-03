package com.cumuluscycles.agentportal;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class AgentPortalApplication {

    public static void main(String[] args) {
        SpringApplication.run(AgentPortalApplication.class, args);
    }
}
