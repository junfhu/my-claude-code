// =============================================================================
// Anthropic API Client Factory
// =============================================================================
// This module is the single entry point for creating Anthropic SDK client
// instances.  It abstracts over four distinct backends:
//   1. Direct (first-party) — talks to api.anthropic.com
//   2. AWS Bedrock         — uses AnthropicBedrock from @anthropic-ai/bedrock-sdk
//   3. Azure Foundry       — uses AnthropicFoundry from @anthropic-ai/foundry-sdk
//   4. Google Vertex AI    — uses AnthropicVertex from @anthropic-ai/vertex-sdk
//
// The active backend is selected at runtime via environment variables
// (CLAUDE_CODE_USE_BEDROCK, CLAUDE_CODE_USE_FOUNDRY, CLAUDE_CODE_USE_VERTEX).
// When none are set, the direct first-party API is used by default.
//
// Every client gets:
//   - A common set of default HTTP headers (session ID, user-agent, etc.)
//   - Proxy-aware fetch options (respects HTTPS_PROXY / NO_PROXY)
//   - A wrapped `fetch` that injects per-request correlation IDs
//   - OAuth / API-key authentication appropriate to the backend
// =============================================================================

import Anthropic, { type ClientOptions } from '@anthropic-ai/sdk'
import { randomUUID } from 'crypto'
import type { GoogleAuth } from 'google-auth-library'
// Authentication utilities — each backend has its own auth refresh flow
import {
  checkAndRefreshOAuthTokenIfNeeded,
  getAnthropicApiKey,
  getApiKeyFromApiKeyHelper,
  getClaudeAIOAuthTokens,
  isClaudeAISubscriber,
  refreshAndGetAwsCredentials,
  refreshGcpCredentialsIfNeeded,
} from 'src/utils/auth.js'
import { getUserAgent } from 'src/utils/http.js'
// Used to apply per-model region overrides (e.g. small/fast model on different AWS region)
import { getSmallFastModel } from 'src/utils/model/model.js'
// Provider detection — determines whether we're hitting first-party Anthropic or a proxy
import {
  getAPIProvider,
  isFirstPartyAnthropicBaseUrl,
} from 'src/utils/model/providers.js'
// Proxy configuration — applies HTTPS_PROXY, NO_PROXY, and custom CA bundles
import { getProxyFetchOptions } from 'src/utils/proxy.js'
import {
  getIsNonInteractiveSession,
  getSessionId,
} from '../../bootstrap/state.js'
import { getOauthConfig } from '../../constants/oauth.js'
import { isDebugToStdErr, logForDebugging } from '../../utils/debug.js'
import {
  getAWSRegion,
  getVertexRegionForModel,
  isEnvTruthy,
} from '../../utils/envUtils.js'

/**
 * Environment variables for different client types:
 *
 * Direct API:
 * - ANTHROPIC_API_KEY: Required for direct API access
 *
 * AWS Bedrock:
 * - AWS credentials configured via aws-sdk defaults
 * - AWS_REGION or AWS_DEFAULT_REGION: Sets the AWS region for all models (default: us-east-1)
 * - ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION: Optional. Override AWS region specifically for the small fast model (Haiku)
 *
 * Foundry (Azure):
 * - ANTHROPIC_FOUNDRY_RESOURCE: Your Azure resource name (e.g., 'my-resource')
 *   For the full endpoint: https://{resource}.services.ai.azure.com/anthropic/v1/messages
 * - ANTHROPIC_FOUNDRY_BASE_URL: Optional. Alternative to resource - provide full base URL directly
 *   (e.g., 'https://my-resource.services.ai.azure.com')
 *
 * Authentication (one of the following):
 * - ANTHROPIC_FOUNDRY_API_KEY: Your Microsoft Foundry API key (if using API key auth)
 * - Azure AD authentication: If no API key is provided, uses DefaultAzureCredential
 *   which supports multiple auth methods (environment variables, managed identity,
 *   Azure CLI, etc.). See: https://docs.microsoft.com/en-us/javascript/api/@azure/identity
 *
 * Vertex AI:
 * - Model-specific region variables (highest priority):
 *   - VERTEX_REGION_CLAUDE_3_5_HAIKU: Region for Claude 3.5 Haiku model
 *   - VERTEX_REGION_CLAUDE_HAIKU_4_5: Region for Claude Haiku 4.5 model
 *   - VERTEX_REGION_CLAUDE_3_5_SONNET: Region for Claude 3.5 Sonnet model
 *   - VERTEX_REGION_CLAUDE_3_7_SONNET: Region for Claude 3.7 Sonnet model
 * - CLOUD_ML_REGION: Optional. The default GCP region to use for all models
 *   If specific model region not specified above
 * - ANTHROPIC_VERTEX_PROJECT_ID: Required. Your GCP project ID
 * - Standard GCP credentials configured via google-auth-library
 *
 * Priority for determining region:
 * 1. Hardcoded model-specific environment variables
 * 2. Global CLOUD_ML_REGION variable
 * 3. Default region from config
 * 4. Fallback region (us-east5)
 */

// Creates an SDK logger that writes all SDK diagnostic output to stderr.
// This keeps SDK debug/info/warn/error messages from polluting stdout
// (which is reserved for the conversational UI). Only activated when
// debug-to-stderr mode is enabled (CLAUDE_CODE_DEBUG=1 or similar).
function createStderrLogger(): ClientOptions['logger'] {
  return {
    error: (msg, ...args) =>
      // biome-ignore lint/suspicious/noConsole:: intentional console output -- SDK logger must use console
      console.error('[Anthropic SDK ERROR]', msg, ...args),
    // biome-ignore lint/suspicious/noConsole:: intentional console output -- SDK logger must use console
    warn: (msg, ...args) => console.error('[Anthropic SDK WARN]', msg, ...args),
    // biome-ignore lint/suspicious/noConsole:: intentional console output -- SDK logger must use console
    info: (msg, ...args) => console.error('[Anthropic SDK INFO]', msg, ...args),
    debug: (msg, ...args) =>
      // biome-ignore lint/suspicious/noConsole:: intentional console output -- SDK logger must use console
      console.error('[Anthropic SDK DEBUG]', msg, ...args),
  }
}

// =============================================================================
// getAnthropicClient — The main factory function
// =============================================================================
// Creates and returns an authenticated Anthropic SDK client instance configured
// for the active backend.  The decision tree is:
//
//   CLAUDE_CODE_USE_BEDROCK=1  → AnthropicBedrock (AWS)
//   CLAUDE_CODE_USE_FOUNDRY=1  → AnthropicFoundry (Azure)
//   CLAUDE_CODE_USE_VERTEX=1   → AnthropicVertex (GCP)
//   (none of the above)        → Anthropic (direct first-party API)
//
// Each branch performs backend-specific auth (AWS STS, Azure AD, GCP ADC,
// or API key) before constructing the client.
//
// Parameters:
//   - apiKey:        Optional explicit API key (overrides env-based lookup)
//   - maxRetries:    SDK-level automatic retry count for transient errors
//   - model:         Model name, used for per-model region routing (Bedrock/Vertex)
//   - fetchOverride: Custom fetch implementation (e.g. for testing or x402 wrapping)
//   - source:        Caller tag logged alongside every outgoing request for tracing
// =============================================================================
export async function getAnthropicClient({
  apiKey,
  maxRetries,
  model,
  fetchOverride,
  source,
}: {
  apiKey?: string
  maxRetries: number
  model?: string
  fetchOverride?: ClientOptions['fetch']
  source?: string
}): Promise<Anthropic> {
  // ---- Collect environment-based context for outgoing request headers ----
  // Container ID and remote session ID are set in containerized / remote
  // deployments (e.g. Codespaces, remote SSH) so the backend can correlate
  // requests to a specific container instance.
  const containerId = process.env.CLAUDE_CODE_CONTAINER_ID
  const remoteSessionId = process.env.CLAUDE_CODE_REMOTE_SESSION_ID
  // SDK consumers (libraries built on top of Claude Code) identify themselves
  // via CLAUDE_AGENT_SDK_CLIENT_APP for backend analytics attribution.
  const clientApp = process.env.CLAUDE_AGENT_SDK_CLIENT_APP
  // Merge any user-specified custom headers (ANTHROPIC_CUSTOM_HEADERS env var)
  const customHeaders = getCustomHeaders()

  // ---- Build the default header set shared by ALL backends ----
  // These headers are sent with every API request regardless of backend type.
  // 'x-app: cli' identifies this traffic as coming from the CLI product.
  const defaultHeaders: { [key: string]: string } = {
    'x-app': 'cli',
    'User-Agent': getUserAgent(),
    // Session ID is a stable per-process UUID for grouping requests
    'X-Claude-Code-Session-Id': getSessionId(),
    // Custom headers from ANTHROPIC_CUSTOM_HEADERS env var (if any)
    ...customHeaders,
    // Conditionally include container/remote identifiers when present
    ...(containerId ? { 'x-claude-remote-container-id': containerId } : {}),
    ...(remoteSessionId
      ? { 'x-claude-remote-session-id': remoteSessionId }
      : {}),
    // SDK consumers can identify their app/library for backend analytics
    ...(clientApp ? { 'x-client-app': clientApp } : {}),
  }

  // Log API client configuration for HFI debugging
  logForDebugging(
    `[API:request] Creating client, ANTHROPIC_CUSTOM_HEADERS present: ${!!process.env.ANTHROPIC_CUSTOM_HEADERS}, has Authorization header: ${!!customHeaders['Authorization']}`,
  )

  // ---- Additional protection header ----
  // When enabled, signals to the backend that the user wants additional
  // safety protections on responses (content filtering, etc.)
  // Add additional protection header if enabled via env var
  const additionalProtectionEnabled = isEnvTruthy(
    process.env.CLAUDE_CODE_ADDITIONAL_PROTECTION,
  )
  if (additionalProtectionEnabled) {
    defaultHeaders['x-anthropic-additional-protection'] = 'true'
  }

  // ---- OAuth token refresh ----
  // For Claude AI subscribers using OAuth, proactively refresh the token
  // before it expires.  This prevents mid-conversation 401 errors.
  logForDebugging('[API:auth] OAuth token check starting')
  await checkAndRefreshOAuthTokenIfNeeded()
  logForDebugging('[API:auth] OAuth token check complete')

  // ---- API key header injection for non-subscriber users ----
  // Subscribers authenticate via OAuth (authToken field below), while
  // API-key users need an Authorization header set up front.
  if (!isClaudeAISubscriber()) {
    await configureApiKeyHeaders(defaultHeaders, getIsNonInteractiveSession())
  }

  // ---- Wrap the fetch implementation ----
  // buildFetch layers request ID injection and optional x402 payment
  // handling on top of the caller's fetchOverride (or globalThis.fetch).
  const resolvedFetch = buildFetch(fetchOverride, source)

  // ---- Common constructor arguments shared by ALL backend constructors ----
  // These are spread into every backend-specific constructor below.
  const ARGS = {
    defaultHeaders,
    maxRetries,
    // Default request timeout: 10 minutes (overridable via API_TIMEOUT_MS env var)
    timeout: parseInt(process.env.API_TIMEOUT_MS || String(600 * 1000), 10),
    // Allow browser-like environments (e.g. Electron) — the SDK normally
    // blocks instantiation when `window` is defined.
    dangerouslyAllowBrowser: true,
    // Proxy-aware fetch options (TLS certs, proxy agent, etc.)
    fetchOptions: getProxyFetchOptions({
      forAnthropicAPI: true,
    }) as ClientOptions['fetchOptions'],
    // Only inject the custom fetch wrapper when one was resolved
    ...(resolvedFetch && {
      fetch: resolvedFetch,
    }),
  }
  // =========================================================================
  // Backend 1: AWS Bedrock
  // =========================================================================
  // Dynamically imports the Bedrock SDK (tree-shaken away when unused).
  // Supports three auth modes:
  //   a) Bearer token (AWS_BEARER_TOKEN_BEDROCK) — for API-key-style access
  //   b) STS credentials (refreshAndGetAwsCredentials) — standard IAM
  //   c) Skip auth entirely (CLAUDE_CODE_SKIP_BEDROCK_AUTH) — testing/proxy
  if (isEnvTruthy(process.env.CLAUDE_CODE_USE_BEDROCK)) {
    const { AnthropicBedrock } = await import('@anthropic-ai/bedrock-sdk')
    // Use region override for small fast model if specified
    // This allows routing the cheap/fast model (Haiku) to a different region
    // than the primary model, useful when quotas differ across regions.
    const awsRegion =
      model === getSmallFastModel() &&
      process.env.ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION
        ? process.env.ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION
        : getAWSRegion()

    // Construct the Bedrock-specific arguments object, merging the common
    // ARGS with Bedrock-specific fields (region, auth skip, logger).
    const bedrockArgs: ConstructorParameters<typeof AnthropicBedrock>[0] = {
      ...ARGS,
      awsRegion,
      ...(isEnvTruthy(process.env.CLAUDE_CODE_SKIP_BEDROCK_AUTH) && {
        skipAuth: true,
      }),
      ...(isDebugToStdErr() && { logger: createStderrLogger() }),
    }

    // Auth path A: Bearer token authentication (API-key style).
    // When AWS_BEARER_TOKEN_BEDROCK is set, skip the normal STS credential
    // flow and inject the token directly as an Authorization header.
    // Add API key authentication if available
    if (process.env.AWS_BEARER_TOKEN_BEDROCK) {
      bedrockArgs.skipAuth = true
      // Add the Bearer token for Bedrock API key authentication
      bedrockArgs.defaultHeaders = {
        ...bedrockArgs.defaultHeaders,
        Authorization: `Bearer ${process.env.AWS_BEARER_TOKEN_BEDROCK}`,
      }
    } else if (!isEnvTruthy(process.env.CLAUDE_CODE_SKIP_BEDROCK_AUTH)) {
      // Auth path B: Standard IAM credential refresh.
      // Calls STS (or reads cached creds) and injects them into the SDK.
      // refreshAndGetAwsCredentials clears stale creds before refreshing.
      // Refresh auth and get credentials with cache clearing
      const cachedCredentials = await refreshAndGetAwsCredentials()
      if (cachedCredentials) {
        bedrockArgs.awsAccessKey = cachedCredentials.accessKeyId
        bedrockArgs.awsSecretKey = cachedCredentials.secretAccessKey
        bedrockArgs.awsSessionToken = cachedCredentials.sessionToken
      }
    }
    // NOTE: AnthropicBedrock is not fully type-compatible with Anthropic
    // (it lacks .batches, .models, etc.), but callers only use the
    // messages/streaming API which is compatible. The `as unknown as Anthropic`
    // cast keeps the return type uniform across all backends.
    // we have always been lying about the return type - this doesn't support batching or models
    return new AnthropicBedrock(bedrockArgs) as unknown as Anthropic
  }

  // =========================================================================
  // Backend 2: Azure Foundry
  // =========================================================================
  // Uses Microsoft Azure's AI Foundry endpoint for Anthropic models.
  // Auth options:
  //   a) ANTHROPIC_FOUNDRY_API_KEY — simple API key (SDK reads it automatically)
  //   b) Azure AD (DefaultAzureCredential → bearer token provider)
  //   c) Skip auth (CLAUDE_CODE_SKIP_FOUNDRY_AUTH) — for proxy/testing
  if (isEnvTruthy(process.env.CLAUDE_CODE_USE_FOUNDRY)) {
    const { AnthropicFoundry } = await import('@anthropic-ai/foundry-sdk')
    // Determine Azure AD token provider based on configuration
    // SDK reads ANTHROPIC_FOUNDRY_API_KEY by default
    let azureADTokenProvider: (() => Promise<string>) | undefined
    // When no explicit API key is set, fall back to Azure AD token auth.
    // If auth is skipped entirely, provide a no-op token provider.
    if (!process.env.ANTHROPIC_FOUNDRY_API_KEY) {
      if (isEnvTruthy(process.env.CLAUDE_CODE_SKIP_FOUNDRY_AUTH)) {
        // Mock token provider for testing/proxy scenarios (similar to Vertex mock GoogleAuth)
        azureADTokenProvider = () => Promise.resolve('')
      } else {
        // Use real Azure AD authentication with DefaultAzureCredential
        const {
          DefaultAzureCredential: AzureCredential,
          getBearerTokenProvider,
        } = await import('@azure/identity')
        azureADTokenProvider = getBearerTokenProvider(
          new AzureCredential(),
          'https://cognitiveservices.azure.com/.default',
        )
      }
    }

    const foundryArgs: ConstructorParameters<typeof AnthropicFoundry>[0] = {
      ...ARGS,
      ...(azureADTokenProvider && { azureADTokenProvider }),
      ...(isDebugToStdErr() && { logger: createStderrLogger() }),
    }
    // Same type-compatibility note as Bedrock — cast to uniform Anthropic type.
    // we have always been lying about the return type - this doesn't support batching or models
    return new AnthropicFoundry(foundryArgs) as unknown as Anthropic
  }

  // =========================================================================
  // Backend 3: Google Vertex AI
  // =========================================================================
  // Uses Google Cloud's Vertex AI endpoint for Anthropic models.
  // Auth: GoogleAuth with cloud-platform scope (ADC, service account, etc.)
  // Region is determined per-model via getVertexRegionForModel().
  // Credential refresh is handled by refreshGcpCredentialsIfNeeded() which
  // mirrors the AWS credential refresh pattern used by Bedrock.
  if (isEnvTruthy(process.env.CLAUDE_CODE_USE_VERTEX)) {
    // Refresh GCP credentials if gcpAuthRefresh is configured and credentials are expired
    // This is similar to how we handle AWS credential refresh for Bedrock
    if (!isEnvTruthy(process.env.CLAUDE_CODE_SKIP_VERTEX_AUTH)) {
      await refreshGcpCredentialsIfNeeded()
    }

    // Parallel-import both the Vertex SDK and the Google auth library to
    // minimize cold-start latency. The Vertex SDK wraps the Anthropic
    // messages API with Vertex-specific auth and routing.
    const [{ AnthropicVertex }, { GoogleAuth }] = await Promise.all([
      import('@anthropic-ai/vertex-sdk'),
      import('google-auth-library'),
    ])
    // TODO: Cache either GoogleAuth instance or AuthClient to improve performance
    // Currently we create a new GoogleAuth instance for every getAnthropicClient() call
    // This could cause repeated authentication flows and metadata server checks
    // However, caching needs careful handling of:
    // - Credential refresh/expiration
    // - Environment variable changes (GOOGLE_APPLICATION_CREDENTIALS, project vars)
    // - Cross-request auth state management
    // See: https://github.com/googleapis/google-auth-library-nodejs/issues/390 for caching challenges

    // Prevent metadata server timeout by providing projectId as fallback
    // google-auth-library checks project ID in this order:
    // 1. Environment variables (GCLOUD_PROJECT, GOOGLE_CLOUD_PROJECT, etc.)
    // 2. Credential files (service account JSON, ADC file)
    // 3. gcloud config
    // 4. GCE metadata server (causes 12s timeout outside GCP)
    //
    // We only set projectId if user hasn't configured other discovery methods
    // to avoid interfering with their existing auth setup

    // Check project environment variables in same order as google-auth-library
    // See: https://github.com/googleapis/google-auth-library-nodejs/blob/main/src/auth/googleauth.ts
    const hasProjectEnvVar =
      process.env['GCLOUD_PROJECT'] ||
      process.env['GOOGLE_CLOUD_PROJECT'] ||
      process.env['gcloud_project'] ||
      process.env['google_cloud_project']

    // Check for credential file paths (service account or ADC)
    // Note: We're checking both standard and lowercase variants to be safe,
    // though we should verify what google-auth-library actually checks
    const hasKeyFile =
      process.env['GOOGLE_APPLICATION_CREDENTIALS'] ||
      process.env['google_application_credentials']

    // Create the GoogleAuth instance. In testing/proxy scenarios we
    // substitute a mock that returns empty auth headers.
    const googleAuth = isEnvTruthy(process.env.CLAUDE_CODE_SKIP_VERTEX_AUTH)
      ? ({
          // Mock GoogleAuth for testing/proxy scenarios
          getClient: () => ({
            getRequestHeaders: () => ({}),
          }),
        } as unknown as GoogleAuth)
      : new GoogleAuth({
          scopes: ['https://www.googleapis.com/auth/cloud-platform'],
          // Only use ANTHROPIC_VERTEX_PROJECT_ID as last resort fallback
          // This prevents the 12-second metadata server timeout when:
          // - No project env vars are set AND
          // - No credential keyfile is specified AND
          // - ADC file exists but lacks project_id field
          //
          // Risk: If auth project != API target project, this could cause billing/audit issues
          // Mitigation: Users can set GOOGLE_CLOUD_PROJECT to override
          ...(hasProjectEnvVar || hasKeyFile
            ? {}
            : {
                projectId: process.env.ANTHROPIC_VERTEX_PROJECT_ID,
              }),
        })

    const vertexArgs: ConstructorParameters<typeof AnthropicVertex>[0] = {
      ...ARGS,
      region: getVertexRegionForModel(model),
      googleAuth,
      ...(isDebugToStdErr() && { logger: createStderrLogger() }),
    }
    // Same type-compatibility note as Bedrock — cast to uniform Anthropic type.
    // we have always been lying about the return type - this doesn't support batching or models
    return new AnthropicVertex(vertexArgs) as unknown as Anthropic
  }

  // =========================================================================
  // Backend 4: Direct first-party Anthropic API (default)
  // =========================================================================
  // Used when no cloud-provider env var is set. Authenticates via either:
  //   a) OAuth (Claude AI subscribers) — authToken from OAuth flow
  //   b) API key — from ANTHROPIC_API_KEY env var or key helper

  // Determine authentication method based on available tokens
  const clientConfig: ConstructorParameters<typeof Anthropic>[0] = {
    // For subscribers, null out apiKey and use authToken (OAuth access token).
    // For non-subscribers, use the explicit or env-derived API key.
    apiKey: isClaudeAISubscriber() ? null : apiKey || getAnthropicApiKey(),
    authToken: isClaudeAISubscriber()
      ? getClaudeAIOAuthTokens()?.accessToken
      : undefined,
    // When using staging OAuth (ant-internal), redirect to the staging API endpoint
    // Set baseURL from OAuth config when using staging OAuth
    ...(process.env.USER_TYPE === 'ant' &&
    isEnvTruthy(process.env.USE_STAGING_OAUTH)
      ? { baseURL: getOauthConfig().BASE_API_URL }
      : {}),
    ...ARGS,
    ...(isDebugToStdErr() && { logger: createStderrLogger() }),
  }

  return new Anthropic(clientConfig)
}

// =============================================================================
// configureApiKeyHeaders — Injects API key into request headers
// =============================================================================
// For non-OAuth users, this looks for an auth token from two sources:
//   1. ANTHROPIC_AUTH_TOKEN env var (explicit override)
//   2. getApiKeyFromApiKeyHelper() — an external helper program that can
//      provide tokens dynamically (useful for SSO / credential managers)
// The token is set as a Bearer Authorization header.
async function configureApiKeyHeaders(
  headers: Record<string, string>,
  isNonInteractiveSession: boolean,
): Promise<void> {
  const token =
    process.env.ANTHROPIC_AUTH_TOKEN ||
    (await getApiKeyFromApiKeyHelper(isNonInteractiveSession))
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
}

// =============================================================================
// getCustomHeaders — Parses user-specified HTTP headers from env var
// =============================================================================
// Reads ANTHROPIC_CUSTOM_HEADERS, which supports multiple headers separated
// by newlines.  Each header is in "Name: Value" (curl-style) format.
// This enables enterprise proxies and custom middleware to inject headers
// (e.g. Authorization, X-Org-Id) without modifying source code.
function getCustomHeaders(): Record<string, string> {
  const customHeaders: Record<string, string> = {}
  const customHeadersEnv = process.env.ANTHROPIC_CUSTOM_HEADERS

  if (!customHeadersEnv) return customHeaders

  // Split by newlines to support multiple headers
  // Each line is expected to be in "Header-Name: header-value" format.
  const headerStrings = customHeadersEnv.split(/\n|\r\n/)

  for (const headerString of headerStrings) {
    if (!headerString.trim()) continue

    // Parse header in format "Name: Value" (curl style). Split on first `:`
    // then trim — avoids regex backtracking on malformed long header lines.
    const colonIdx = headerString.indexOf(':')
    if (colonIdx === -1) continue
    const name = headerString.slice(0, colonIdx).trim()
    const value = headerString.slice(colonIdx + 1).trim()
    if (name) {
      customHeaders[name] = value
    }
  }

  return customHeaders
}

// =============================================================================
// CLIENT_REQUEST_ID_HEADER — Per-request correlation ID header name
// =============================================================================
// This header carries a UUID generated client-side on each outgoing request.
// It enables correlating client-side timeouts (which never receive a
// server-side request ID in the response) with server-side logs. The API
// team uses this for debugging latency and error investigations.
export const CLIENT_REQUEST_ID_HEADER = 'x-client-request-id'

// =============================================================================
// buildFetch — Wraps the fetch implementation with middleware
// =============================================================================
// Layers two concerns on top of the base fetch function:
//
//   1. x402 payment handling — if the x402 module is available and enabled,
//      wraps fetch so that HTTP 402 (Payment Required) responses are
//      automatically retried with a payment token.
//
//   2. Client request ID injection — for first-party API calls, generates a
//      UUID and sets it as the x-client-request-id header.  This enables
//      server-side log correlation even when the response times out.
//
// The `source` parameter is logged alongside each request for tracing which
// code path (e.g. "query", "compact", "tool_call") initiated the request.
function buildFetch(
  fetchOverride: ClientOptions['fetch'],
  source: string | undefined,
): ClientOptions['fetch'] {
  // eslint-disable-next-line eslint-plugin-n/no-unsupported-features/node-builtins
  // Start with the caller-provided fetch or fall back to the global fetch
  let inner = fetchOverride ?? globalThis.fetch

  // ---- x402 payment protocol wrapping ----
  // Wrap with x402 payment handler for automatic 402 Payment Required handling
  // The x402 module is optional — if not bundled, this is silently skipped.
  try {
    const { wrapFetchWithX402, isX402Enabled } =
      require('../x402/index.js') as typeof import('../x402/index.js')
    if (isX402Enabled()) {
      inner = wrapFetchWithX402(inner as typeof globalThis.fetch) as typeof inner
    }
  } catch {
    // x402 module not available, skip
  }

  // ---- Request ID injection ----
  // Only inject x-client-request-id for first-party API calls.
  // Third-party backends (Bedrock/Vertex/Foundry) don't log this header,
  // and strict enterprise proxies may reject unknown headers (inc-4029 class).
  // Only send to the first-party API — Bedrock/Vertex/Foundry don't log it
  // and unknown headers risk rejection by strict proxies (inc-4029 class).
  const injectClientRequestId =
    getAPIProvider() === 'firstParty' && isFirstPartyAnthropicBaseUrl()
  // Return a wrapped fetch function that:
  //   1. Injects x-client-request-id header (for first-party API only)
  //   2. Logs the request URL and correlation ID for debugging
  //   3. Delegates to the inner fetch (which may include x402 wrapping)
  return (input, init) => {
    // eslint-disable-next-line eslint-plugin-n/no-unsupported-features/node-builtins
    const headers = new Headers(init?.headers)
    // Generate a client-side request ID so timeouts (which return no server
    // request ID) can still be correlated with server logs by the API team.
    // Callers that want to track the ID themselves can pre-set the header.
    if (injectClientRequestId && !headers.has(CLIENT_REQUEST_ID_HEADER)) {
      headers.set(CLIENT_REQUEST_ID_HEADER, randomUUID())
    }
    try {
      // eslint-disable-next-line eslint-plugin-n/no-unsupported-features/node-builtins
      const url = input instanceof Request ? input.url : String(input)
      const id = headers.get(CLIENT_REQUEST_ID_HEADER)
      logForDebugging(
        `[API REQUEST] ${new URL(url).pathname}${id ? ` ${CLIENT_REQUEST_ID_HEADER}=${id}` : ''} source=${source ?? 'unknown'}`,
      )
    } catch {
      // never let logging crash the fetch
    }
    return inner(input, { ...init, headers })
  }
}

