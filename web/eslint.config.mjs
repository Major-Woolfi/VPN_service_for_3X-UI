import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

import { FlatCompat } from "@eslint/eslintrc";
import { defineConfig, globalIgnores } from "eslint/config";

const baseDirectory = dirname(fileURLToPath(import.meta.url));
const compat = new FlatCompat({ baseDirectory });

const eslintConfig = defineConfig([
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts", "src/lib/i18n-generated.ts"]),
  ...compat.extends("next/core-web-vitals", "next/typescript"),
]);

export default eslintConfig;
