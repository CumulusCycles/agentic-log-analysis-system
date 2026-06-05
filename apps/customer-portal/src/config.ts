import { z } from "zod";

const ConfigSchema = z.object({
  PORT: z.coerce.number().int().positive().default(3000),
  JWT_SECRET: z.string().min(1, "JWT_SECRET is required"),
  JWT_ALGORITHM: z.string().default("HS256"),
  SHARED_DATA_API_BASE_URL: z.string().url().default("http://shared-data-api:8000"),
  SHARED_DATA_API_KEY_CUSTOMER_PORTAL: z
    .string()
    .min(1, "SHARED_DATA_API_KEY_CUSTOMER_PORTAL is required"),
  LOG_FILE_PATH: z.string().default("/app/logs/customer-portal.log"),
});

export type Config = z.infer<typeof ConfigSchema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const result = ConfigSchema.safeParse(env);
  if (!result.success) {
    const issues = result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ");
    throw new Error(`invalid configuration: ${issues}`);
  }
  return result.data;
}
