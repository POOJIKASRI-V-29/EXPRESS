import { defineRailway, postgres, preserve, project, service, volume } from "railway/iac";

// EXPRESS OS production topology.
//
// `railway up` uploads from the git root, so each service names its own
// rootDirectory and Dockerfile: the repo holds two apps and the auto-detected
// builder cannot tell which one it is looking at.
//
// Both app images are the *.prod Dockerfiles. The plain Dockerfiles next to
// them still run the local docker-compose stack and are untouched.
export default defineRailway(() => {
  const Postgres = postgres("Postgres", { region: "ams" });
  const postgresVolume = volume("postgres-volume", {
    alerts: { usage: { "100": {}, "80": {}, "95": {} } },
    allowOnlineResize: true,
    region: "ams",
    sizeMB: 500,
  });

  const backend = service("backend", {
    rootDirectory: "backend",
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile.prod" },
    // Migrations run in prestart, so a deploy can be slow to first byte.
    healthcheckPath: "/health",
    healthcheckTimeout: 180,
    replicas: { ams: 1 },
    // Secrets stay in Railway; preserve() keeps them out of source.
    env: {
      DATABASE_URL: preserve(), DEMO_EMAIL: preserve(), DEMO_PASSWORD: preserve(),
      ENV: preserve(), GEMINI_API_KEY: preserve(), GEMINI_MODEL: preserve(),
      LOCAL_TZ: preserve(), LOG_LEVEL: preserve(), SECRET_KEY: preserve(),
      FRONTEND_ORIGIN: preserve(), OAUTH_REDIRECT_BASE: preserve(),
    },
  });

  const frontend = service("frontend", {
    rootDirectory: "frontend",
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile.prod" },
    replicas: { ams: 1 },
    // NEXT_PUBLIC_* is inlined by `next build`, so this has to reach the image
    // as a build arg — Railway passes service variables to the Docker build.
    env: { NEXT_PUBLIC_API_URL: preserve() },
  });

  return project("express-os", {
    resources: [backend, frontend, Postgres, postgresVolume],
  });
});
