import {describe, expect, test} from "bun:test";

import {extractSlashCommands, formatTranscriptLine} from "../src/transcriptFormatting";

describe("extractSlashCommands", () => {
  test("finds slash commands without treating filesystem paths as commands", () => {
    expect(extractSlashCommands("run /git then /runtime")).toEqual(["/git", "/runtime"]);
    expect(extractSlashCommands("saved to /Users/dhyana/dharma_swarm/terminal/src/app.tsx")).toEqual([]);
  });
});

describe("formatTranscriptLine", () => {
  test("formats headings and subheadings distinctly", () => {
    expect(formatTranscriptLine({id: "1", kind: "system", text: "# Mission"}).segments[0]).toEqual({
      text: "Mission",
      color: "magenta",
      bold: true,
    });
    expect(formatTranscriptLine({id: "2", kind: "system", text: "## Active Lane"}).segments[0]).toEqual({
      text: "Active Lane",
      color: "cyan",
      bold: true,
    });
  });

  test("highlights inline slash commands in blue", () => {
    const formatted = formatTranscriptLine({
      id: "3",
      kind: "assistant",
      text: "Run /git and then /runtime for current truth.",
    });

    expect(formatted.segments.map((segment) => segment.text)).toEqual([
      "Run ",
      "/git",
      " and then ",
      "/runtime",
      " for current truth.",
    ]);
    expect(formatted.segments[1]?.color).toBe("blue");
    expect(formatted.segments[3]?.color).toBe("blue");
  });
});
