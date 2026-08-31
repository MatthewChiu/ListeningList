import { verifyKey, InteractionType, InteractionResponseType } from 'discord-interactions';

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'POST') {
      return new Response('Expected POST', { status: 405 });
    }

    const signature = request.headers.get('X-Signature-Ed25519');
    const timestamp = request.headers.get('X-Signature-Timestamp');
    const body = await request.text();

    const isValid =
      signature &&
      timestamp &&
      (await verifyKey(body, signature, timestamp, env.DISCORD_PUBLIC_KEY));

    if (!isValid) {
      return new Response('Bad request signature', { status: 401 });
    }

    const interaction = JSON.parse(body);

    // Discord's handshake check
    if (interaction.type === InteractionType.PING) {
      return jsonResponse({ type: InteractionResponseType.PONG });
    }

    if (interaction.type === InteractionType.APPLICATION_COMMAND) {
      const { name, options = [] } = interaction.data;
      const opt = (key) => options.find((o) => o.name === key)?.value ?? '';

      let eventType;
      let payload = {};

      if (name === 'recommend') {
        eventType = 'discord-recommend';
        payload = { prompt: opt('prompt') };
      } else if (name === 'add') {
        eventType = 'discord-add';
        payload = { prompt: opt('prompt') };
      } else if (name === 'listened') {
        eventType = 'discord-checkoff';
        payload = { composer: opt('composer'), title: opt('title') };
      } else {
        return jsonResponse({
          type: InteractionResponseType.CHANNEL_MESSAGE_WITH_SOURCE,
          data: { content: `Unknown command: ${name}` },
        });
      }

      payload.application_id = interaction.application_id;
      payload.interaction_token = interaction.token;

      // Fire the GitHub dispatch after responding, since Discord requires an
      // ack within 3 seconds but the workflow (LLM call + commit) takes longer.
      ctx.waitUntil(triggerGithubDispatch(env, eventType, payload));

      return jsonResponse({
        type: InteractionResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE,
      });
    }

    return new Response('Unhandled interaction type', { status: 400 });
  },
};

async function triggerGithubDispatch(env, eventType, payload) {
  const resp = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'listening-log-bot',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ event_type: eventType, client_payload: payload }),
  });

  if (!resp.ok) {
    // Best-effort: edit the deferred reply so it doesn't hang forever if this fails.
    const errBody = await resp.text();
    await fetch(
      `https://discord.com/api/v10/webhooks/${payload.application_id}/${payload.interaction_token}/messages/@original`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: `⚠️ Couldn't reach GitHub to run that command (${resp.status}).`,
        }),
      }
    );
    console.error('GitHub dispatch failed:', resp.status, errBody);
  }
}

function jsonResponse(obj) {
  return new Response(JSON.stringify(obj), {
    headers: { 'Content-Type': 'application/json' },
  });
}
