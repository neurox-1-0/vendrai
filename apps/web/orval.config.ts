import { defineConfig } from "orval";

export default defineConfig({
  neurox: {
    input: {
      target: "../../packages/contracts/openapi.json",
    },
    output: {
      target: "./src/generated/neurox.ts",
      schemas: "./src/generated/models",
      client: "react-query",
      httpClient: "fetch",
      clean: true,
      override: {
        mutator: {
          path: "./src/lib/generated-client.ts",
          name: "generatedClient",
        },
        fetch: {
          includeHttpResponseReturnType: false,
        },
      },
    },
  },
});
