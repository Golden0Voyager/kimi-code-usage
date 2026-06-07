"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const config_1 = require("vitest/config");
const node_url_1 = require("node:url");
exports.default = (0, config_1.defineConfig)({
    resolve: {
        alias: {
            vscode: (0, node_url_1.fileURLToPath)(new URL('./src/__mocks__/vscode.ts', import.meta.url)),
        },
    },
    test: {
        include: ['src/**/*.test.ts'],
        exclude: ['src/__mocks__/**'],
        environment: 'node',
        globals: false,
    },
});
//# sourceMappingURL=vitest.config.js.map