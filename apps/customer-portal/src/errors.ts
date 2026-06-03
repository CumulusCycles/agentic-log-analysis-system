import { AxiosError } from "axios";

export class AppError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
    this.name = "AppError";
  }
}

/**
 * Convert an axios error (from an outbound SDA call) into an AppError that
 * preserves the SDA's status code 1:1 and its `detail` body when present.
 * Network failures become 502 "shared data api unreachable".
 */
export function sdaErrorToHttp(err: unknown): AppError {
  if (err instanceof AxiosError) {
    if (err.response) {
      const data = err.response.data as { detail?: string } | undefined;
      const detail = data?.detail ?? "upstream error";
      return new AppError(err.response.status, detail);
    }
    return new AppError(502, "shared data api unreachable");
  }
  return new AppError(500, "internal error");
}
