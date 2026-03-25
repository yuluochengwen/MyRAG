// Shared frontend configuration for API routing.
(function initAppConfig(globalScope) {
  const basePath = "";

  globalScope.APP_CONFIG = {
    API_BASE_URL: basePath,
    API_PREFIX: "/api",
    AGENT_PREFIX: "/api/agent",
    buildUrl(path) {
      const safePath = String(path || "").startsWith("/") ? path : `/${path}`;
      return `${this.API_BASE_URL}${safePath}`;
    },
    buildAgentUrl(path) {
      const safePath = String(path || "").startsWith("/") ? path : `/${path}`;
      return `${this.API_BASE_URL}${this.AGENT_PREFIX}${safePath}`;
    }
  };
})(window);
