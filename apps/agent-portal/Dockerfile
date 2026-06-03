# Stage 1 — React frontend build
FROM node:22-alpine AS frontend

RUN corepack enable
WORKDIR /build

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile --ignore-scripts

COPY frontend ./
RUN pnpm run build


# Stage 2 — Spring Boot backend build
FROM maven:3.9-eclipse-temurin-21-alpine AS backend

WORKDIR /app

# Cache dependencies before copying the rest of the source.
COPY pom.xml ./
COPY .mvn .mvn
COPY mvnw mvnw.cmd ./
RUN mvn -B -q dependency:go-offline

COPY src ./src
# Drop the frontend build into the JAR's static path before packaging.
COPY --from=frontend /build/dist ./src/main/resources/static
RUN mvn -B -q -DskipTests package


# Stage 3 — runtime
FROM eclipse-temurin:21-jre-alpine AS runtime

WORKDIR /app

# Non-root user. eclipse-temurin:21-jre-alpine does not ship one.
RUN addgroup -g 1000 app && adduser -D -u 1000 -G app app \
    && mkdir -p /app/logs \
    && chown -R app:app /app

COPY --from=backend --chown=app:app /app/target/agent-portal.jar /app/agent-portal.jar

USER app
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/agent-portal.jar"]
