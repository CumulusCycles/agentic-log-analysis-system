package com.cumuluscycles.agentportal.config;

import java.io.IOException;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

/**
 * Serves the React SPA from classpath:/static. For any request that does not
 * match an /api/** or /actuator/** route and isn't a real static asset, this
 * returns index.html so React Router can resolve the client-side route.
 * Path-traversal is blocked by PathResourceResolver's built-in
 * isResourceUnderLocation check.
 */
@Configuration
public class SpaResourceConfig implements WebMvcConfigurer {

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/**")
                .addResourceLocations("classpath:/static/")
                .resourceChain(false)
                .addResolver(new SpaPathResolver());
    }

    private static final class SpaPathResolver extends PathResourceResolver {

        @Override
        protected Resource getResource(String resourcePath, Resource location) throws IOException {
            if (resourcePath.startsWith("api/") || resourcePath.startsWith("actuator/")) {
                return null;
            }
            if (resourcePath.isEmpty()) {
                return readableOrNull(location.createRelative("index.html"));
            }
            Resource requested = super.getResource(resourcePath, location);
            if (requested != null) {
                return requested;
            }
            return readableOrNull(location.createRelative("index.html"));
        }

        private static Resource readableOrNull(Resource resource) throws IOException {
            return (resource.exists() && resource.isReadable()) ? resource : null;
        }
    }
}
