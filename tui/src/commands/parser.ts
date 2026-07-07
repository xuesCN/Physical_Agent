import type { ParsedCommand } from "../types.js";

export function parseCommand(input: string): ParsedCommand {
  const trimmed = input.trim();
  if (!trimmed) {
    return { type: "unknown", input, message: "Enter a message or /help." };
  }
  if (!trimmed.startsWith("/")) {
    return { type: "chat", text: trimmed };
  }

  const [name, ...rest] = trimmed.split(/\s+/);
  const payload = trimmed.slice(name.length).trim();
  switch (name.toLowerCase()) {
    case "/task":
      return payload
        ? { type: "task", text: payload }
        : { type: "unknown", input, message: "/task requires text." };
    case "/approve":
      return rest[0]
        ? { type: "approve", actionId: rest[0] }
        : { type: "unknown", input, message: "/approve requires an action id." };
    case "/reject": {
      const actionId = rest[0];
      const reason = rest.slice(1).join(" ").trim();
      return actionId && reason
        ? { type: "reject", actionId, reason }
        : { type: "unknown", input, message: "/reject requires an action id and reason." };
    }
    case "/reset":
      return payload
        ? { type: "reset", confirm: payload }
        : { type: "unknown", input, message: "/reset requires confirmation text." };
    case "/refresh":
      return { type: "refresh" };
    case "/help":
      return { type: "help" };
    case "/quit":
    case "/exit":
      return { type: "quit" };
    case "/execute":
    case "/driver":
    case "/hardware-control":
      return {
        type: "unknown",
        input,
        message: `${name} is intentionally unavailable. Use Actions approval; watch remains the only executor.`
      };
    default:
      return { type: "unknown", input, message: `Unknown command: ${name}` };
  }
}

export const COMMAND_HELP = [
  "Commands:",
  "  <text>                     Send chat message",
  "  /task <text>               Submit task proposal",
  "  /approve <action_id>       Approve execution",
  "  /reject <action_id> <why>  Reject execution",
  "  /reset true                Reset workspace through API confirmation",
  "  /refresh                   Refresh snapshot",
  "  /help                      Show this help",
  "  /quit                      Exit"
].join("\n");
