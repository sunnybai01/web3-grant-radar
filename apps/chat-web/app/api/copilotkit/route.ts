import {
  BuiltInAgent,
  CopilotRuntime,
  convertMessagesToVercelAISDKMessages,
  convertToolsToVercelAITools,
  createCopilotRuntimeHandler,
} from "@copilotkit/runtime/v2";
import { createOpenAI } from "@ai-sdk/openai";
import { stepCountIs, streamText } from "ai";

function resolveDeepseekBaseUrl(raw?: string) {
  const fallback = "https://api.deepseek.com/v1";
  if (!raw) {
    return fallback;
  }

  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return fallback;
  }

  if (/\/v\d+$/i.test(trimmed)) {
    return trimmed;
  }

  return `${trimmed}/v1`;
}

const deepseekBaseUrl = resolveDeepseekBaseUrl(process.env.DEEPSEEK_BASE_URL);
const deepseekApiKey = process.env.DEEPSEEK_API_KEY || "";
const deepseekModel = process.env.CHAT_AGENT_MODEL || "deepseek-chat";

const deepseekProvider = createOpenAI({
  baseURL: deepseekBaseUrl,
  apiKey: deepseekApiKey,
  name: "deepseek",
});

const systemPrompt =
  "You are Grant Radar, a read-only Web3 opportunity verification copilot. Use getDashboardContext before making claims about current page state (active tab, filters, selected row, and visible rows). Use analyzeDatabaseTargets whenever the user asks about trust, reward, deadlines, fit, or what to build for an opportunity. Base every conclusion on returned tool data and clearly separate verified facts, unknowns, conflicts, and assumptions.";

const runtime = new CopilotRuntime({
  agents: {
    default: new BuiltInAgent({
      type: "aisdk",
      factory: ({ input, abortSignal }) => {
        const messages = convertMessagesToVercelAISDKMessages(input.messages);
        const tools = convertToolsToVercelAITools(input.tools) as any;

        return streamText({
          model: deepseekProvider.chat(deepseekModel),
          system: systemPrompt,
          messages,
          tools,
          abortSignal,
          stopWhen: stepCountIs(5),
        });
      },
    }),
  },
});

const handler = createCopilotRuntimeHandler({
  runtime,
  basePath: "/api/copilotkit",
  mode: "single-route",
});

export const POST = handler;
