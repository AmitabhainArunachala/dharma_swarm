import type {OutlineItem, TabSpec, TranscriptLine} from "./types.js";

function line(id: string, kind: TranscriptLine["kind"], text: string): TranscriptLine {
  return {id, kind, text};
}

export function buildInitialTabs(): TabSpec[] {
  return [
    {
      id: "chat",
      title: "Chat",
      kind: "chat",
      lines: [
        line("boot-1", "system", "Dharma Terminal rebuild alpha"),
        line("boot-2", "system", "Keyboard-first shell. Backend bridged over stdio."),
        line("boot-3", "assistant", "Use plain prompts or slash commands. Chat is conversation only; system state lives in its own tabs."),
      ],
    },
    {
      id: "mission",
      title: "Mission",
      kind: "mission",
      lines: [
        line("mission-1", "system", "# Terminal Rebuild"),
        line("mission-2", "system", "## Goal"),
        line("mission-3", "assistant", "Replace the fragmented Python CLI/Textual seam with a clean Bun/Ink operator shell."),
        line("mission-4", "system", "## Principles"),
        line("mission-5", "assistant", "One state model. One bridge. Open tabs. Minimal chrome. No duplicate output."),
      ],
    },
    {
      id: "repo",
      title: "Repo",
      kind: "repo",
      lines: [
        line("repo-1", "system", "Workspace snapshot loading..."),
        line("repo-2", "assistant", "The terminal should know what repo it is standing in."),
      ],
    },
    {
      id: "commands",
      title: "Commands",
      kind: "commands",
      lines: [
        line("commands-1", "system", "Command graph loading..."),
        line("commands-2", "assistant", "Plain language should resolve into Dharma-native commands when confidence is high."),
      ],
    },
    {
      id: "models",
      title: "Models",
      kind: "models",
      lines: [
        line("models-1", "system", "Model policy loading..."),
      ],
    },
    {
      id: "ontology",
      title: "Ontology",
      kind: "ontology",
      lines: [
        line("ontology-1", "system", "Ontology snapshot loading..."),
        line("ontology-2", "assistant", "The shell should surface DHARMA concepts, not just provider chat."),
      ],
    },
    {
      id: "runtime",
      title: "Runtime",
      kind: "runtime",
      lines: [
        line("runtime-1", "system", "Bridge: booting"),
        line("runtime-2", "system", "Python runtime: expected 3.11+"),
        line("runtime-3", "system", "Frontend runtime: Bun preferred, Node fallback only for local editing"),
      ],
    },
    {
      id: "sessions",
      title: "Sessions",
      kind: "sessions",
      lines: [
        line("sessions-1", "system", "# Session Memory"),
        line("sessions-2", "assistant", "Resumable sessions, replay integrity, and compaction truth should be first-class operator surfaces."),
      ],
    },
    {
      id: "approvals",
      title: "Approvals",
      kind: "approvals",
      lines: [
        line("approvals-1", "system", "# Approval Queue"),
        line("approvals-2", "assistant", "Dangerous actions should surface as explicit operator work, not transcript accidents."),
      ],
    },
    {
      id: "control",
      title: "Control",
      kind: "control",
      lines: [
        line("control-1", "system", "Control-plane snapshot loading..."),
      ],
    },
    {
      id: "agents",
      title: "Agents",
      kind: "agents",
      lines: [
        line("agents-1", "system", "Operator snapshot loading..."),
      ],
    },
    {
      id: "evolution",
      title: "Evolution",
      kind: "evolution",
      lines: [
        line("evolution-1", "system", "Cascade and self-improvement surface loading..."),
      ],
    },
  ];
}

export function buildInitialOutline(): OutlineItem[] {
  return [
    {id: "toc-chat", label: "Live Chat", depth: 1, targetTabId: "chat"},
    {id: "toc-mission", label: "Mission", depth: 1, targetTabId: "mission"},
    {id: "toc-goal", label: "Goal", depth: 2, targetTabId: "mission"},
    {id: "toc-principles", label: "Principles", depth: 2, targetTabId: "mission"},
    {id: "toc-repo", label: "Repo", depth: 1, targetTabId: "repo"},
    {id: "toc-commands", label: "Commands", depth: 1, targetTabId: "commands"},
    {id: "toc-models", label: "Models", depth: 1, targetTabId: "models"},
    {id: "toc-ontology", label: "Ontology", depth: 1, targetTabId: "ontology"},
    {id: "toc-runtime", label: "Runtime", depth: 1, targetTabId: "runtime"},
    {id: "toc-sessions", label: "Sessions", depth: 1, targetTabId: "sessions"},
    {id: "toc-approvals", label: "Approvals", depth: 1, targetTabId: "approvals"},
    {id: "toc-control", label: "Control", depth: 1, targetTabId: "control"},
    {id: "toc-agents", label: "Agents", depth: 1, targetTabId: "agents"},
    {id: "toc-evolution", label: "Evolution", depth: 1, targetTabId: "evolution"},
  ];
}
