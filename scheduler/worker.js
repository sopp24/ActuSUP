const REPOSITORY = "sopp24/ActuSUP";
const WORKFLOW_FILE = "update-news.yml";
const API = `https://api.github.com/repos/${REPOSITORY}`;

const SUCCESS_GRACE_MS = 8 * 60 * 1000;
const STALE_RUN_MS = 12 * 60 * 1000;

function githubHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function githubJson(url, token, init = {}) {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...githubHeaders(token),
      ...(init.headers || {}),
    },
  });

  if (!response.ok) {
    const detail = (await response.text()).slice(0, 400);
    throw new Error(`GitHub API ${response.status}: ${detail}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function ensureCollection(env, scheduledTime) {
  if (!env.GITHUB_TOKEN) {
    throw new Error("Le secret Cloudflare GITHUB_TOKEN est absent.");
  }

  const token = env.GITHUB_TOKEN;
  const now = Date.now();
  const runsUrl =
    `${API}/actions/workflows/${WORKFLOW_FILE}/runs?branch=main&per_page=10`;

  const payload = await githubJson(runsUrl, token);
  const runs = Array.isArray(payload?.workflow_runs)
    ? payload.workflow_runs
    : [];

  // Ne jamais créer de doublon si une collecte est déjà en cours.
  const activeRun = runs.find((run) =>
    run.status === "queued" || run.status === "in_progress"
  );

  if (activeRun) {
    const startedAt = Date.parse(
      activeRun.run_started_at || activeRun.created_at || ""
    );
    const age = Number.isFinite(startedAt) ? now - startedAt : 0;

    if (age <= STALE_RUN_MS) {
      console.log(JSON.stringify({
        action: "skip",
        reason: "collection_already_active",
        run_id: activeRun.id,
        age_seconds: Math.max(0, Math.round(age / 1000)),
        scheduled_at: new Date(scheduledTime).toISOString(),
      }));
      return;
    }

    // Une exécution anormalement longue ne doit pas bloquer les cycles suivants.
    await githubJson(`${API}/actions/runs/${activeRun.id}/cancel`, token, {
      method: "POST",
    });

    console.warn(JSON.stringify({
      action: "cancel_stale_run",
      run_id: activeRun.id,
      age_seconds: Math.round(age / 1000),
    }));
  }

  // Si le cron natif GitHub vient de réussir, on le laisse faire :
  // le Worker sert de réveil indépendant, pas de source de doublons.
  const lastSuccess = runs.find((run) => run.conclusion === "success");
  const successAt = Date.parse(
    lastSuccess?.updated_at || lastSuccess?.created_at || ""
  );

  if (
    Number.isFinite(successAt) &&
    now - successAt < SUCCESS_GRACE_MS
  ) {
    console.log(JSON.stringify({
      action: "skip",
      reason: "recent_success",
      run_id: lastSuccess.id,
      success_age_seconds: Math.round((now - successAt) / 1000),
    }));
    return;
  }

  await githubJson(
    `${API}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    token,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    }
  );

  console.log(JSON.stringify({
    action: "workflow_dispatch",
    workflow: WORKFLOW_FILE,
    ref: "main",
    previous_success_at: Number.isFinite(successAt)
      ? new Date(successAt).toISOString()
      : null,
    scheduled_at: new Date(scheduledTime).toISOString(),
  }));
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      ensureCollection(env, controller.scheduledTime).catch((error) => {
        console.error("Échec du déclenchement ActuSUP :", error.message);
        throw error;
      })
    );
  },

  async fetch() {
    return new Response(
      "ActuSUP external scheduler is deployed. Collection is triggered by its private cron schedule.",
      {
        status: 200,
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      }
    );
  },
};
