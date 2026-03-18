const RUNPOD_ROUTE = '/api/runpod';
const RUNPOD_STATUS_PREFIX = '/api/runpod/status/';

const parseAllowedOrigins = (value) =>
  String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

const isOriginAllowed = (origin, allowedOrigins) =>
  !origin || allowedOrigins.length === 0 || allowedOrigins.includes(origin);

const buildCorsHeaders = (origin, allowedOrigins) => {
  const allowOrigin = origin && allowedOrigins.length > 0
    ? origin
    : allowedOrigins[0] || '*';

  return {
    'Access-Control-Allow-Origin': allowOrigin,
    'Access-Control-Allow-Methods': 'POST, GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
    Vary: 'Origin',
  };
};

const jsonResponse = (payload, status, corsHeaders) =>
  new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders,
      'Content-Type': 'application/json',
    },
  });

const parseJsonSafe = async (response) => {
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return { error: await response.text() };
};

const extractStatusJobId = (pathname) => {
  if (!pathname.startsWith(RUNPOD_STATUS_PREFIX)) return null;
  const rawId = pathname.slice(RUNPOD_STATUS_PREFIX.length);
  if (!rawId) return null;
  try {
    return decodeURIComponent(rawId);
  } catch {
    return null;
  }
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || '';
    const allowedOrigins = parseAllowedOrigins(env.ALLOWED_ORIGIN);

    if (!isOriginAllowed(origin, allowedOrigins)) {
      return new Response('Forbidden', { status: 403 });
    }

    const corsHeaders = buildCorsHeaders(origin, allowedOrigins);

    if (request.method === 'OPTIONS') {
      return new Response(null, {
        status: 204,
        headers: corsHeaders,
      });
    }

    const statusJobId = extractStatusJobId(url.pathname);
    if (request.method === 'GET' && statusJobId) {
      try {
        const runpodResponse = await fetch(
          `https://api.runpod.ai/v2/${env.RUNPOD_ENDPOINT_ID}/status/${encodeURIComponent(statusJobId)}`,
          {
            method: 'GET',
            headers: {
              Authorization: `Bearer ${env.RUNPOD_API_KEY}`,
            },
          }
        );

        const responseBody = await parseJsonSafe(runpodResponse);
        return jsonResponse(responseBody, runpodResponse.status, corsHeaders);
      } catch (error) {
        return jsonResponse(
          { error: 'Status request failed', details: String(error) },
          500,
          corsHeaders
        );
      }
    }

    if (request.method === 'POST' && url.pathname === RUNPOD_ROUTE) {
      let body;
      try {
        body = await request.json();
      } catch {
        return jsonResponse({ error: 'Invalid JSON body' }, 400, corsHeaders);
      }

      if (!body || typeof body !== 'object' || Array.isArray(body)) {
        return jsonResponse({ error: 'JSON body must be an object' }, 400, corsHeaders);
      }

      try {
        const runpodResponse = await fetch(
          `https://api.runpod.ai/v2/${env.RUNPOD_ENDPOINT_ID}/run`,
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${env.RUNPOD_API_KEY}`,
            },
            body: JSON.stringify(body),
          }
        );

        const responseBody = await parseJsonSafe(runpodResponse);
        return jsonResponse(responseBody, runpodResponse.status, corsHeaders);
      } catch (error) {
        return jsonResponse(
          { error: 'RunPod submit failed', details: String(error) },
          500,
          corsHeaders
        );
      }
    }

    return new Response('Not Found', { status: 404, headers: corsHeaders });
  },
};
