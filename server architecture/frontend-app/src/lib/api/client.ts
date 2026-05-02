// Typed API client. Types regenerated from /openapi.json via `npm run gen-types`.
// Base URL comes from VITE_API_BASE_URL (.env.local) or defaults to localhost:8000.

import createClient from "openapi-fetch";
import type { paths } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl: BASE_URL });
export const API_BASE_URL = BASE_URL;
