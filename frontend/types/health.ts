export type HealthResponse = {
  status: "ok" | "degraded";
  database: "ok" | "error";
};
