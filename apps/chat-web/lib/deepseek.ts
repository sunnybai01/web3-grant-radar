/** DeepSeek-V4.1-Flash. `deepseek-chat` is a legacy alias for the same model. */
export const DEFAULT_DEEPSEEK_MODEL = "deepseek-flash";

/**
 * DEEPSEEK_THINKING, read the same way as the Python settings: unset or empty
 * means on; otherwise 1/true/yes/on enable it and anything else disables it.
 */
export function isThinkingEnabled(raw: string | undefined): boolean {
  if (raw === undefined || raw === "") {
    return true;
  }
  return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
}

/**
 * Sets DeepSeek's `thinking` field on every request. It is sent explicitly
 * either way so a change of the API default cannot flip the mode. The AI SDK's
 * OpenAI provider has no option for this DeepSeek-only field, hence the fetch
 * wrapper.
 */
export function withThinking(enabled: boolean, fetchImpl: typeof fetch = fetch): typeof fetch {
  const thinking = { type: enabled ? "enabled" : "disabled" };
  return (input, init) => {
    if (typeof init?.body !== "string") {
      return fetchImpl(input, init);
    }
    const body = JSON.parse(init.body);
    return fetchImpl(input, { ...init, body: JSON.stringify({ ...body, thinking }) });
  };
}
