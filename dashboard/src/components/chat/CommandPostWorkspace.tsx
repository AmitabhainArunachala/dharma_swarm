"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  ArrowLeft,
  ArrowLeftRight,
  ArrowRight,
  Cable,
  Maximize2,
  Minimize2,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { ExternalLink } from "lucide-react";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { useChat } from "@/hooks/useChat";
import {
  type ChatSessionFeedEvent,
  useChatSessionFeed,
} from "@/hooks/useChatSessionFeed";
import { useChatWorkspace } from "@/hooks/useChatWorkspace";
import {
  getChatProfiles,
  resolveCanonicalChatStatus,
  resolveCommandPostPeerProfileId,
  shortProfileLabel,
} from "@/lib/chatProfiles";
import {
  buildChatSessionConnectionState,
  type ChatSessionConnectionPhase,
} from "@/lib/chatSessionContract";
import { colors } from "@/lib/theme";
import type { ChatStatusOut } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

const CODEX_PROFILE_ID = "codex_operator";
const COMMAND_POST_MISSING_PEER_ID = "__command_post_missing_peer__";
const WAIT_AFTER_SEND_MS = 80;

type CommandPostVariant = "page" | "panel";

interface CommandPostWorkspaceProps {
  variant: CommandPostVariant;
  onClose?: () => void;
  runtimeChatStatus?: ChatStatusOut | null;
}

function accentColorForProfile(accent: string): string {
  if (accent === "kinpaku") return colors.kinpaku;
  if (accent === "botan") return colors.botan;
  if (accent === "rokusho") return colors.rokusho;
  if (accent === "fuji") return colors.fuji;
  if (accent === "bengara") return colors.bengara;
  return colors.aozora;
}

function latestRelayText(messages: Array<{ role: string; content: string }>): string {
  const assistant = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.content.trim());
  if (assistant) return assistant.content.trim();

  const fallback = [...messages]
    .reverse()
    .find((message) => message.content.trim());
  return fallback?.content.trim() ?? "";
}

function latestUserIntent(messages: Array<{ role: string; content: string }>): string {
  const user = [...messages]
    .reverse()
    .find((message) => message.role === "user" && message.content.trim());
  return user?.content.trim() ?? "";
}

function buildSeedPrompt(args: {
  selfLabel: string;
  peerLabel: string;
  operatorNote: string;
}): string {
  const note = args.operatorNote.trim()
    ? args.operatorNote.trim()
    : "No explicit operator brief was provided.";

  return [
    `[Live Command Post Boot for ${args.selfLabel}]`,
    `You are live inside the DHARMA COMMAND dual-orchestrator screen with ${args.peerLabel}.`,
    `Operator brief:\n"""\n${note}\n"""`,
    `Your reply must be directly useful to ${args.peerLabel} and visible to the operator.`,
    "Respond with:",
    "1. your frame of the task",
    `2. the first thing ${args.peerLabel} must know`,
    `3. one question, constraint, or handoff for ${args.peerLabel}`,
    "4. the residual-stream note that should persist after this turn",
  ].join("\n\n");
}

function buildRelayPrompt(args: {
  sourceLabel: string;
  peerLabel: string;
  peerMessage: string;
  operatorNote: string;
  operatorIntent?: string;
}): string {
  const note = args.operatorNote.trim()
    ? args.operatorNote.trim()
    : "No extra operator note.";
  const intent = args.operatorIntent?.trim()
    ? args.operatorIntent.trim()
    : "No explicit operator intent captured yet.";

  return [
    `[Peer relay from ${args.sourceLabel}]`,
    `You and ${args.sourceLabel} are co-orchestrators of the DHARMA COMMAND post and dharma_swarm.`,
    `Operator intent to preserve in the shared residual stream:\n${intent}`,
    `Peer message:\n"""\n${args.peerMessage}\n"""`,
    `Operator bridge note:\n${note}`,
    "Respond directly to your peer with:",
    "1. what you accept",
    "2. what you need clarified",
    "3. the next concrete action you will take",
    "4. what should be written into the swarm-wide residual stream",
  ].join("\n\n");
}

function trimSessionLabel(value: string): string {
  if (!value) return "idle";
  if (value.length <= 16) return value;
  return `${value.slice(0, 10)}...${value.slice(-4)}`;
}

function telemetryAccent(event: string): string {
  if (event === "chat_error") return colors.bengara;
  if (event === "chat_tool_call" || event === "chat_tool_result") return colors.kinpaku;
  if (event === "chat_assistant_turn") return colors.rokusho;
  if (event === "chat_user_turn") return colors.aozora;
  return colors.sumi[600];
}

function waitForUiFlush(): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, WAIT_AFTER_SEND_MS);
  });
}

function focusLaneInput(profileId: string) {
  window.dispatchEvent(
    new CustomEvent("command-post-focus-input", {
      detail: { profileId },
    }),
  );
}

function connectionToneClass(phase: ChatSessionConnectionPhase): string {
  if (phase === "linked") return "text-rokusho";
  if (phase === "pending" || phase === "linking" || phase === "degraded") {
    return "text-kinpaku";
  }
  return "text-sumi-700";
}

function missingPeerProfile() {
  return {
    id: COMMAND_POST_MISSING_PEER_ID,
    label: "Peer lane unavailable",
    provider: "runtime",
    model: "not advertised",
    accent: "bengara",
    summary:
      "Command Post needs a non-Codex peer lane from /api/chat/status before the dual-orchestrator relay can come online.",
    available: false,
    availability_kind: "not_advertised",
    status_note:
      "No non-Codex peer lane is currently advertised by the canonical chat contract.",
  };
}

function missingCodexProfile() {
  return {
    id: CODEX_PROFILE_ID,
    label: "Codex lane unavailable",
    provider: "runtime",
    model: "not advertised",
    accent: "bengara",
    summary:
      "Command Post needs the codex_operator lane from /api/chat/status before the dual-orchestrator relay can come online.",
    available: false,
    availability_kind: "not_advertised",
    status_note:
      "Codex operator is not currently advertised by the canonical chat contract.",
  };
}

export function CommandPostWorkspace({
  variant,
  onClose,
  runtimeChatStatus,
}: CommandPostWorkspaceProps) {
  const panelMode = variant === "panel";
  const [peerProfileId, setPeerProfileId] = useState(() =>
    resolveCommandPostPeerProfileId(null) ?? COMMAND_POST_MISSING_PEER_ID,
  );
  const [wide, setWide] = useState(false);
  const [isBrowserFullscreen, setIsBrowserFullscreen] = useState(false);
  const [bridgeNote, setBridgeNote] = useState("");
  const [bridgeStatus, setBridgeStatus] = useState<string | null>(null);
  const [relayBusy, setRelayBusy] = useState<string | null>(null);
  const [loopRounds, setLoopRounds] = useState(2);
  const [loopActive, setLoopActive] = useState(false);
  const rootRef = useRef<HTMLDivElement | HTMLElement | null>(null);
  const setRootElement = (element: HTMLDivElement | HTMLElement | null) => {
    rootRef.current = element;
  };
  const { profileId, setProfile } = useChatWorkspace();
  const claude = useChat(peerProfileId, { allowAdvertisedFallback: false });
  const codex = useChat(CODEX_PROFILE_ID, { allowAdvertisedFallback: false });
  const status = resolveCanonicalChatStatus(runtimeChatStatus, claude.status, codex.status);
  const advertisedProfiles = getChatProfiles(status);
  const sessionFeedAdvertised = Boolean(status?.chat_ws_path_template?.trim());
  const peerProfileOptions = advertisedProfiles.filter(
    (profile) => profile.id !== CODEX_PROFILE_ID,
  );
  const preferredPeerProfileId = resolveCommandPostPeerProfileId(status);
  const selectedPeerProfile =
    peerProfileOptions.find((profile) => profile.id === peerProfileId) ?? null;
  const selectedCodexProfile =
    advertisedProfiles.find((profile) => profile.id === CODEX_PROFILE_ID) ?? null;
  const claudeProfile = selectedPeerProfile ?? missingPeerProfile();
  const codexProfile = selectedCodexProfile ?? missingCodexProfile();
  const peerRelayReady = Boolean(
    selectedPeerProfile && selectedPeerProfile.available !== false,
  );
  const codexRelayReady = Boolean(
    selectedCodexProfile && selectedCodexProfile.available !== false,
  );
  const claudeAccent = accentColorForProfile(claudeProfile.accent);
  const codexAccent = accentColorForProfile(codexProfile.accent);
  const claudeRelay = latestRelayText(claude.messages);
  const codexRelay = latestRelayText(codex.messages);
  const operatorIntent = useMemo(() => {
    const intents = [
      latestUserIntent(claude.messages),
      latestUserIntent(codex.messages),
    ].filter(Boolean);
    return intents[0] ?? "";
  }, [claude.messages, codex.messages]);
  const claudeFeed = useChatSessionFeed({
    profileId: peerProfileId,
    profileLabel: claudeProfile.label,
    sessionId: claude.sessionId,
    wsPathTemplate: status?.chat_ws_path_template,
  });
  const codexFeed = useChatSessionFeed({
    profileId: CODEX_PROFILE_ID,
    profileLabel: codexProfile.label,
    sessionId: codex.sessionId,
    wsPathTemplate: status?.chat_ws_path_template,
  });

  const claudeMessagesRef = useRef(claude.messages);
  const codexMessagesRef = useRef(codex.messages);
  const loopCancelRef = useRef(false);

  useEffect(() => {
    claudeMessagesRef.current = claude.messages;
  }, [claude.messages]);

  useEffect(() => {
    codexMessagesRef.current = codex.messages;
  }, [codex.messages]);

  useEffect(() => {
    return () => {
      loopCancelRef.current = true;
    };
  }, []);

  useEffect(() => {
    function syncFullscreenState() {
      setIsBrowserFullscreen(document.fullscreenElement === rootRef.current);
    }

    syncFullscreenState();
    document.addEventListener("fullscreenchange", syncFullscreenState);
    return () => document.removeEventListener("fullscreenchange", syncFullscreenState);
  }, []);

  useEffect(() => {
    if (peerProfileOptions.length === 0) {
      if (peerProfileId !== COMMAND_POST_MISSING_PEER_ID) {
        setPeerProfileId(COMMAND_POST_MISSING_PEER_ID);
      }
      if (profileId === peerProfileId) {
        setProfile(CODEX_PROFILE_ID);
      }
      return;
    }
    const activePeer = peerProfileOptions.find((profile) => profile.id === peerProfileId);
    if (activePeer && activePeer.available !== false) return;
    if (activePeer && peerProfileOptions.every((profile) => profile.available === false)) return;
    if (preferredPeerProfileId) {
      setPeerProfileId(preferredPeerProfileId);
      return;
    }
    if (!activePeer && peerProfileOptions[0]) {
      setPeerProfileId(peerProfileOptions[0].id);
    }
  }, [peerProfileId, peerProfileOptions, preferredPeerProfileId, profileId, setProfile]);

  const telemetry = useMemo(() => {
    return [...claudeFeed.events, ...codexFeed.events]
      .sort((left, right) => right.timestamp.localeCompare(left.timestamp))
      .slice(0, panelMode ? 14 : 18);
  }, [claudeFeed.events, codexFeed.events, panelMode]);

  async function relay(
    sourceLabel: string,
    peerLabel: string,
    peerMessage: string,
    send: (content: string) => Promise<void>,
    targetProfileId: string,
    direction: string,
  ) {
    if (!peerMessage.trim()) {
      setBridgeStatus(`No relayable message from ${sourceLabel} yet.`);
      return;
    }

    setBridgeStatus(null);
    setRelayBusy(direction);
    setProfile(targetProfileId);
    try {
      await send(
        buildRelayPrompt({
          sourceLabel,
          peerLabel,
          peerMessage,
          operatorNote: bridgeNote,
          operatorIntent,
        }),
      );
      setBridgeStatus(`${sourceLabel} brief sent to ${peerLabel}.`);
    } catch (error) {
      setBridgeStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setRelayBusy(null);
    }
  }

  async function primeBoth() {
    if (!peerRelayReady || !codexRelayReady) {
      setBridgeStatus("Command Post needs both Codex and an advertised peer lane before priming.");
      return;
    }
    if (!bridgeNote.trim()) {
      setBridgeStatus("Write an operator brief before priming both lanes.");
      return;
    }

    setBridgeStatus(null);
    setRelayBusy("prime-both");
    try {
      await Promise.all([
        claude.sendMessage(
          buildSeedPrompt({
            selfLabel: claudeProfile.label,
            peerLabel: codexProfile.label,
            operatorNote: bridgeNote,
          }),
        ),
        codex.sendMessage(
          buildSeedPrompt({
            selfLabel: codexProfile.label,
            peerLabel: claudeProfile.label,
            operatorNote: bridgeNote,
          }),
        ),
      ]);
      setBridgeStatus("Both orchestrators are primed and visible.");
    } catch (error) {
      setBridgeStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setRelayBusy(null);
    }
  }

  async function conveneBoth() {
    if (!peerRelayReady || !codexRelayReady) {
      setBridgeStatus("Command Post needs both Codex and an advertised peer lane before convening.");
      return;
    }
    if (!claudeRelay || !codexRelay) {
      setBridgeStatus("Both orchestrators need at least one message before you can convene them.");
      return;
    }

    setBridgeStatus(null);
    setRelayBusy("convene");
    try {
      await Promise.all([
        codex.sendMessage(
          buildRelayPrompt({
            sourceLabel: claudeProfile.label,
            peerLabel: codexProfile.label,
            peerMessage: claudeRelay,
            operatorNote: bridgeNote,
            operatorIntent,
          }),
        ),
        claude.sendMessage(
          buildRelayPrompt({
            sourceLabel: codexProfile.label,
            peerLabel: claudeProfile.label,
            peerMessage: codexRelay,
            operatorNote: bridgeNote,
            operatorIntent,
          }),
        ),
      ]);
      setBridgeStatus("Both orchestrators received peer briefs.");
    } catch (error) {
      setBridgeStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setRelayBusy(null);
    }
  }

  function stopLoop() {
    loopCancelRef.current = true;
    claude.stopStreaming();
    codex.stopStreaming();
    setLoopActive(false);
    setRelayBusy(null);
    setBridgeStatus("Stopping live exchange...");
  }

  async function runLiveLoop() {
    if (!peerRelayReady || !codexRelayReady) {
      setBridgeStatus("Command Post needs both Codex and an advertised peer lane before the live loop can run.");
      return;
    }
    if (!claudeRelay || !codexRelay) {
      setBridgeStatus("Prime both lanes or convene once before starting the live loop.");
      return;
    }

    loopCancelRef.current = false;
    setLoopActive(true);
    setRelayBusy("live-loop");

    let completedRounds = 0;

    try {
      for (let round = 0; round < loopRounds; round += 1) {
        if (loopCancelRef.current) break;

        const latestClaude = latestRelayText(claudeMessagesRef.current);
        if (!latestClaude) {
          throw new Error(`${claudeProfile.label} has no relayable output for round ${round + 1}.`);
        }

        setBridgeStatus(
          `Round ${round + 1}/${loopRounds}: ${claudeProfile.label} briefing ${codexProfile.label}.`,
        );
        setProfile(CODEX_PROFILE_ID);
        await codex.sendMessage(
          buildRelayPrompt({
            sourceLabel: claudeProfile.label,
            peerLabel: codexProfile.label,
            peerMessage: latestClaude,
            operatorNote: bridgeNote,
            operatorIntent,
          }),
        );
        await waitForUiFlush();
        if (loopCancelRef.current) break;

        const latestCodex = latestRelayText(codexMessagesRef.current);
        if (!latestCodex) {
          throw new Error(`${codexProfile.label} has no relayable output for round ${round + 1}.`);
        }

        setBridgeStatus(
          `Round ${round + 1}/${loopRounds}: ${codexProfile.label} briefing ${claudeProfile.label}.`,
        );
        setProfile(peerProfileId);
        await claude.sendMessage(
          buildRelayPrompt({
            sourceLabel: codexProfile.label,
            peerLabel: claudeProfile.label,
            peerMessage: latestCodex,
            operatorNote: bridgeNote,
            operatorIntent,
          }),
        );
        await waitForUiFlush();

        completedRounds = round + 1;
      }

      setBridgeStatus(
        loopCancelRef.current
          ? "Live exchange stopped."
          : `Live exchange complete after ${completedRounds} round${completedRounds === 1 ? "" : "s"}.`,
      );
    } catch (error) {
      setBridgeStatus(error instanceof Error ? error.message : String(error));
    } finally {
      loopCancelRef.current = false;
      setLoopActive(false);
      setRelayBusy(null);
    }
  }

  async function intervene(targetProfileId: string, targetLabel: string) {
    loopCancelRef.current = true;
    claude.stopStreaming();
    codex.stopStreaming();
    setLoopActive(false);
    setRelayBusy(null);
    setProfile(targetProfileId);
    await waitForUiFlush();
    focusLaneInput(targetProfileId);
    setBridgeStatus(`Operator intervention ready on ${targetLabel}. Live exchange paused.`);
  }

  function switchPeerLane(nextProfileId: string) {
    if (
      !nextProfileId ||
      nextProfileId === CODEX_PROFILE_ID ||
      nextProfileId === peerProfileId ||
      !peerProfileOptions.some((profile) => profile.id === nextProfileId)
    ) {
      return;
    }
    loopCancelRef.current = true;
    claude.stopStreaming();
    setLoopActive(false);
    setRelayBusy(null);
    const priorProfileId = peerProfileId;
    setPeerProfileId(nextProfileId);
    if (profileId === priorProfileId) {
      setProfile(nextProfileId);
    }
    const nextProfile = advertisedProfiles.find((profile) => profile.id === nextProfileId);
    setBridgeStatus(
      `Peer lane switched to ${nextProfile ? nextProfile.label : nextProfileId}.`,
    );
  }

  async function toggleBrowserFullscreen() {
    const root = rootRef.current;
    if (!root) return;

    try {
      if (document.fullscreenElement === root) {
        await document.exitFullscreen();
        return;
      }
      await root.requestFullscreen();
    } catch (error) {
      setBridgeStatus(error instanceof Error ? error.message : String(error));
    }
  }

  const header = (
    <div
      className="flex items-center justify-between border-b px-4 py-3"
      style={{ borderColor: colors.sumi[700] + "66" }}
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="font-heading text-sm font-bold tracking-wide text-torinoko">
            Command Post
          </span>
          <span className="rounded-full bg-aozora/10 px-2 py-0.5 font-mono text-[10px] text-aozora">
            {`${shortProfileLabel(claudeProfile)} + ${shortProfileLabel(codexProfile)}`}
          </span>
          <span className="rounded-full bg-kinpaku/10 px-2 py-0.5 font-mono text-[10px] text-kinpaku">
            resident sessions
          </span>
        </div>
        <p className="mt-1 text-[11px] text-sumi-600">
          Two live orchestrator lanes, explicit relay control, and websocket telemetry from the resident sessions.
        </p>
      </div>
      <div className="flex items-center gap-1">
        {panelMode && (
          <button
            onClick={() => setWide((value) => !value)}
            className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            title={wide ? "Narrow" : "Widen"}
          >
            {wide ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        )}
        <button
          onClick={toggleBrowserFullscreen}
          className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
          title={isBrowserFullscreen ? "Exit Browser Full Screen" : "Enter Browser Full Screen"}
        >
          {isBrowserFullscreen ? <Minimize2 size={14} /> : <ExternalLink size={14} />}
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            title="Close panel"
          >
            <X size={14} />
          </button>
        )}
      </div>
    </div>
  );

  const content = (
    <div
      className="grid min-h-0 flex-1 overflow-hidden"
      style={{
        gridTemplateRows: panelMode
          ? "minmax(0, 1fr) clamp(176px, 23vh, 220px)"
          : "minmax(0, 1fr) clamp(220px, 24vh, 280px)",
      }}
    >
      <div
        className={`grid min-h-0 grid-cols-1 ${
          panelMode
            ? "grid-rows-[minmax(0,1fr)_240px_minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_184px_minmax(0,1fr)] md:grid-rows-1"
            : "grid-rows-[minmax(0,1fr)_260px_minmax(0,1fr)] xl:grid-cols-[minmax(0,1fr)_220px_minmax(0,1fr)] xl:grid-rows-1"
        }`}
      >
        <LaneColumn
          profileId={peerProfileId}
          label={claudeProfile.label}
          provider={claudeProfile.provider}
          model={claudeProfile.model}
          accentColor={claudeAccent}
          isPrimary
          focused={profileId === peerProfileId}
          isStreaming={claude.isStreaming}
          sessionId={claude.sessionId}
          wsConnected={claudeFeed.connected}
          feedAdvertised={sessionFeedAdvertised}
          onFocus={() => {
            if (selectedPeerProfile) {
              setProfile(peerProfileId);
            }
          }}
          onClear={claude.clearMessages}
          profileOptions={peerProfileOptions.map((profile) => ({
            id: profile.id,
            label: profile.label,
          }))}
          onProfileChange={switchPeerLane}
          emptyState={
            selectedPeerProfile
              ? undefined
              : {
                  title: "Peer relay degraded",
                  detail:
                    "No non-Codex peer lane is currently advertised by `/api/chat/status`. The command-post shell stays visible, but the second live lane is intentionally withheld.",
                }
          }
        />

        <ControlRail
          bridgeNote={bridgeNote}
          onBridgeNoteChange={setBridgeNote}
          bridgeStatus={bridgeStatus}
          claudeLabel={shortProfileLabel(claudeProfile)}
          codexLabel={shortProfileLabel(codexProfile)}
          claudeDisabled={!peerRelayReady || !codexRelayReady || !claudeRelay || codex.isStreaming || relayBusy !== null}
          codexDisabled={!peerRelayReady || !codexRelayReady || !codexRelay || claude.isStreaming || relayBusy !== null}
          conveneDisabled={
            !peerRelayReady ||
            !codexRelayReady ||
            !claudeRelay ||
            !codexRelay ||
            claude.isStreaming ||
            codex.isStreaming ||
            relayBusy !== null
          }
          primeDisabled={
            !peerRelayReady ||
            !codexRelayReady ||
            !bridgeNote.trim() ||
            claude.isStreaming ||
            codex.isStreaming ||
            relayBusy !== null
          }
          loopDisabled={
            !peerRelayReady ||
            !codexRelayReady ||
            !claudeRelay ||
            !codexRelay ||
            claude.isStreaming ||
            codex.isStreaming ||
            relayBusy !== null
          }
          loopActive={loopActive}
          loopRounds={loopRounds}
          onLoopRoundsChange={setLoopRounds}
          relayBusy={relayBusy}
          onPrimeBoth={primeBoth}
          onClaudeToCodex={() =>
            relay(
              claudeProfile.label,
              codexProfile.label,
              claudeRelay,
              codex.sendMessage,
              CODEX_PROFILE_ID,
              "claude-to-codex",
            )
          }
          onCodexToClaude={() =>
            relay(
              codexProfile.label,
              claudeProfile.label,
              codexRelay,
              claude.sendMessage,
              peerProfileId,
              "codex-to-claude",
            )
          }
          onConvene={conveneBoth}
          onRunLoop={runLiveLoop}
          onStopLoop={stopLoop}
        />

        <LaneColumn
          profileId={CODEX_PROFILE_ID}
          label={codexProfile.label}
          provider={codexProfile.provider}
          model={codexProfile.model}
          accentColor={codexAccent}
          focused={profileId === CODEX_PROFILE_ID}
          isStreaming={codex.isStreaming}
          sessionId={codex.sessionId}
          wsConnected={codexFeed.connected}
          feedAdvertised={sessionFeedAdvertised}
          onFocus={() => setProfile(CODEX_PROFILE_ID)}
          onClear={codex.clearMessages}
          emptyState={
            selectedCodexProfile
              ? undefined
              : {
                  title: "Codex relay degraded",
                  detail:
                    "The canonical `codex_operator` lane is not currently advertised by `/api/chat/status`. The command-post shell stays visible, but the Codex lane is intentionally withheld.",
                }
          }
        />
      </div>

      <TelemetryRail
        panelMode={panelMode}
        claudeLabel={claudeProfile.label}
        codexLabel={codexProfile.label}
        claudeAccent={claudeAccent}
        codexAccent={codexAccent}
        claudeFeed={claudeFeed}
        codexFeed={codexFeed}
        feedAdvertised={sessionFeedAdvertised}
        claudeStreaming={claude.isStreaming}
        codexStreaming={codex.isStreaming}
        claudeSessionId={claude.sessionId}
        codexSessionId={codex.sessionId}
        telemetry={telemetry}
        onInterveneClaude={() => {
          if (selectedPeerProfile) {
            void intervene(peerProfileId, claudeProfile.label);
          }
        }}
        onInterveneCodex={() => intervene(CODEX_PROFILE_ID, codexProfile.label)}
        claudeInterveneDisabled={!selectedPeerProfile}
        codexInterveneDisabled={!selectedCodexProfile}
      />
    </div>
  );

  if (panelMode) {
    return (
      <motion.div
        ref={setRootElement}
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 24, stiffness: 210 }}
        className={`fixed right-0 top-0 z-50 flex h-screen flex-col overflow-hidden border-l bg-sumi-950/98 backdrop-blur-md ${
          isBrowserFullscreen
            ? "h-screen w-screen"
            : wide
              ? "w-full md:w-[88%]"
              : "w-full md:w-[78%]"
        }`}
        style={{ borderColor: colors.sumi[700] + "66" }}
      >
        {header}
        {content}
      </motion.div>
    );
  }

  return (
    <section
      ref={setRootElement}
      className={`overflow-hidden border border-sumi-700/40 bg-sumi-950/92 shadow-[0_0_28px_rgba(79,209,217,0.05)] ${
        isBrowserFullscreen ? "h-screen rounded-none" : "rounded-[28px]"
      }`}
    >
      {header}
      {content}
    </section>
  );
}

function LaneColumn(args: {
  profileId: string;
  label: string;
  provider: string;
  model: string;
  accentColor: string;
  isPrimary?: boolean;
  focused: boolean;
  isStreaming: boolean;
  sessionId: string;
  wsConnected: boolean;
  feedAdvertised: boolean;
  onFocus: () => void;
  onClear: () => void;
  profileOptions?: Array<{ id: string; label: string }>;
  onProfileChange?: (profileId: string) => void;
  emptyState?: {
    title: string;
    detail: string;
  };
}) {
  const connection = buildChatSessionConnectionState({
    sessionId: args.sessionId,
    isStreaming: args.isStreaming,
    wsConnected: args.wsConnected,
    feedAdvertised: args.feedAdvertised,
  });

  return (
    <section
      className={`flex min-h-0 flex-col ${
        args.isPrimary ? "border-b xl:border-b-0 xl:border-r md:border-b-0 md:border-r" : ""
      }`}
      style={{
        borderColor:
          args.isPrimary ? `${colors.sumi[700]}55` : undefined,
        background: args.focused
          ? `linear-gradient(180deg, color-mix(in srgb, ${args.accentColor} 6%, ${colors.sumi[900]}), ${colors.sumi[950]})`
          : `linear-gradient(180deg, ${colors.sumi[900]}, ${colors.sumi[950]})`,
      }}
    >
      <div
        className="flex items-center justify-between border-b px-4 py-3"
        style={{ borderColor: colors.sumi[700] + "55" }}
      >
        <button onClick={args.onFocus} className="min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className="font-heading text-sm font-bold" style={{ color: args.accentColor }}>
              {args.label}
            </span>
            <span className="rounded-full bg-sumi-850 px-2 py-0.5 font-mono text-[10px] text-sumi-600">
              {args.provider}
            </span>
            {args.isStreaming && (
              <span className="flex items-center gap-1 rounded-full bg-rokusho/10 px-2 py-0.5 font-mono text-[10px] text-rokusho">
                <Radio size={10} />
                live
              </span>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2 font-mono text-[10px] text-sumi-600">
            <span>{args.model}</span>
            <span className={connectionToneClass(connection.phase)}>
              {trimSessionLabel(connection.sessionLabel)}
            </span>
            <span className={connectionToneClass(connection.phase)}>
              {connection.socketLabel}
            </span>
          </div>
        </button>
        <div className="flex items-center gap-2">
          {args.profileOptions && args.onProfileChange && args.profileOptions.length > 1 && (
            <select
              value={args.profileId}
              onChange={(event) => args.onProfileChange?.(event.target.value)}
              className="max-w-[152px] rounded-lg border border-sumi-700/40 bg-sumi-950/80 px-2 py-1 font-mono text-[10px] text-torinoko outline-none transition-colors focus:border-kinpaku/35"
              aria-label="Choose peer lane model"
            >
              {args.profileOptions.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.label}
                </option>
              ))}
            </select>
          )}
          {!args.emptyState ? (
            <button
              onClick={args.onClear}
              className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
              title={`Clear ${args.label}`}
            >
              <Trash2 size={14} />
            </button>
          ) : null}
        </div>
      </div>

      <div className="min-h-0 flex-1">
        {args.emptyState ? (
          <div className="flex h-full items-center justify-center px-4 py-6">
            <div className="w-full max-w-md rounded-3xl border border-dashed border-bengara/35 bg-sumi-950/70 px-5 py-6 text-center">
              <div className="font-heading text-base font-semibold text-bengara">
                {args.emptyState.title}
              </div>
              <p className="mt-3 text-sm text-sumi-400">{args.emptyState.detail}</p>
            </div>
          </div>
        ) : (
          <ChatInterface
            className="h-full"
            compact
            showHeader={false}
            profileId={args.profileId}
            allowProfileSwitch={false}
          />
        )}
      </div>
    </section>
  );
}

function ControlRail(args: {
  bridgeNote: string;
  onBridgeNoteChange: (value: string) => void;
  bridgeStatus: string | null;
  claudeLabel: string;
  codexLabel: string;
  claudeDisabled: boolean;
  codexDisabled: boolean;
  conveneDisabled: boolean;
  primeDisabled: boolean;
  loopDisabled: boolean;
  loopActive: boolean;
  loopRounds: number;
  onLoopRoundsChange: (value: number) => void;
  relayBusy: string | null;
  onPrimeBoth: () => void;
  onClaudeToCodex: () => void;
  onCodexToClaude: () => void;
  onConvene: () => void;
  onRunLoop: () => void;
  onStopLoop: () => void;
}) {
  return (
    <aside
      className="flex flex-col gap-3 border-y px-3 py-4 md:border-x md:border-y-0 xl:border-x xl:border-y-0"
      style={{
        borderColor: colors.sumi[700] + "55",
        background: `linear-gradient(180deg, ${colors.sumi[900]}, ${colors.sumi[850]}, ${colors.sumi[900]})`,
      }}
    >
      <div className="text-center">
        <div className="font-heading text-xs font-semibold uppercase tracking-[0.18em] text-kinpaku">
          Relay
        </div>
        <p className="mt-1 text-[10px] text-sumi-600">
          Prime both lanes, relay explicitly, or run a bounded live exchange.
        </p>
      </div>

      <textarea
        value={args.bridgeNote}
        onChange={(event) => args.onBridgeNoteChange(event.target.value)}
        placeholder="Mission, constraint, or operator brief"
        rows={6}
        className="w-full resize-none rounded-xl border border-sumi-700/40 bg-sumi-950/80 px-3 py-2 text-[11px] text-torinoko placeholder-sumi-700 outline-none transition-colors focus:border-kinpaku/35"
      />

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={args.onPrimeBoth}
          disabled={args.primeDisabled}
          className="flex items-center justify-center gap-2 rounded-xl border border-fuji/30 bg-fuji/10 px-2 py-2 text-[11px] text-fuji transition-colors hover:bg-fuji/15 disabled:cursor-not-allowed disabled:opacity-35"
          title="Send the operator brief to both lanes"
        >
          <RefreshCw size={13} />
          {args.relayBusy === "prime-both" ? "Priming" : "Prime Both"}
        </button>

        <div className="flex items-center justify-center gap-2 rounded-xl border border-sumi-700/40 bg-sumi-950/80 px-2 py-2 text-[11px] text-sumi-600">
          <span>Rounds</span>
          <input
            type="number"
            min={1}
            max={6}
            value={args.loopRounds}
            onChange={(event) => {
              const nextValue = Number.parseInt(event.target.value, 10);
              args.onLoopRoundsChange(Number.isNaN(nextValue) ? 1 : Math.max(1, Math.min(6, nextValue)));
            }}
            className="w-12 rounded border border-sumi-700/50 bg-sumi-900 px-2 py-1 text-center text-[11px] text-torinoko outline-none"
          />
        </div>
      </div>

      <button
        onClick={args.onClaudeToCodex}
        disabled={args.claudeDisabled}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-aozora/30 bg-aozora/10 px-2 py-2 text-[11px] text-aozora transition-colors hover:bg-aozora/15 disabled:cursor-not-allowed disabled:opacity-35"
        title={`Relay ${args.claudeLabel} to ${args.codexLabel}`}
      >
        <ArrowRight size={13} />
        {args.relayBusy === "claude-to-codex" ? "Sending" : `${args.claudeLabel} -> ${args.codexLabel}`}
      </button>

      <button
        onClick={args.onConvene}
        disabled={args.conveneDisabled}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-kinpaku/30 bg-kinpaku/10 px-2 py-2 text-[11px] text-kinpaku transition-colors hover:bg-kinpaku/15 disabled:cursor-not-allowed disabled:opacity-35"
        title="Convene both orchestrators once"
      >
        <ArrowLeftRight size={13} />
        {args.relayBusy === "convene" ? "Convening" : "Convene Once"}
      </button>

      <button
        onClick={args.onCodexToClaude}
        disabled={args.codexDisabled}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-rokusho/30 bg-rokusho/10 px-2 py-2 text-[11px] text-rokusho transition-colors hover:bg-rokusho/15 disabled:cursor-not-allowed disabled:opacity-35"
        title={`Relay ${args.codexLabel} to ${args.claudeLabel}`}
      >
        <ArrowLeft size={13} />
        {args.relayBusy === "codex-to-claude" ? "Sending" : `${args.codexLabel} -> ${args.claudeLabel}`}
      </button>

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={args.onRunLoop}
          disabled={args.loopDisabled}
          className="flex items-center justify-center gap-2 rounded-xl border border-botan/30 bg-botan/10 px-2 py-2 text-[11px] text-botan transition-colors hover:bg-botan/15 disabled:cursor-not-allowed disabled:opacity-35"
          title="Run a bounded Claude/Codex exchange loop"
        >
          <Play size={13} />
          {args.relayBusy === "live-loop" ? "Running" : "Run Loop"}
        </button>
        <button
          onClick={args.onStopLoop}
          disabled={!args.loopActive}
          className="flex items-center justify-center gap-2 rounded-xl border border-bengara/30 bg-bengara/10 px-2 py-2 text-[11px] text-bengara transition-colors hover:bg-bengara/15 disabled:cursor-not-allowed disabled:opacity-35"
          title="Stop the current live exchange"
        >
          <Pause size={13} />
          Stop
        </button>
      </div>

      <div className="min-h-[46px] rounded-xl border border-sumi-700/40 bg-sumi-950/70 px-3 py-2 font-mono text-[10px] text-sumi-600">
        {args.bridgeStatus ?? "Peer relay is explicit. No hidden agent-to-agent chatter is happening off-screen."}
      </div>
    </aside>
  );
}

function TelemetryRail(args: {
  panelMode: boolean;
  claudeLabel: string;
  codexLabel: string;
  claudeAccent: string;
  codexAccent: string;
  claudeFeed: {
    connected: boolean;
    events: ChatSessionFeedEvent[];
    lastEvent: ChatSessionFeedEvent | null;
    snapshotTurns: number;
  };
  codexFeed: {
    connected: boolean;
    events: ChatSessionFeedEvent[];
    lastEvent: ChatSessionFeedEvent | null;
    snapshotTurns: number;
  };
  feedAdvertised: boolean;
  claudeStreaming: boolean;
  codexStreaming: boolean;
  claudeSessionId: string;
  codexSessionId: string;
  telemetry: ChatSessionFeedEvent[];
  onInterveneClaude: () => void;
  onInterveneCodex: () => void;
  claudeInterveneDisabled?: boolean;
  codexInterveneDisabled?: boolean;
}) {
  return (
    <section
      className={`grid min-h-0 overflow-hidden border-t ${
        args.panelMode
          ? "grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)_220px]"
          : "grid-cols-1 xl:grid-cols-[240px_minmax(0,1fr)_240px]"
      }`}
      style={{ borderColor: colors.sumi[700] + "55" }}
    >
      <TelemetryCard
        compact={args.panelMode}
        label={args.claudeLabel}
        accent={args.claudeAccent}
        connected={args.claudeFeed.connected}
        isStreaming={args.claudeStreaming}
        snapshotTurns={args.claudeFeed.snapshotTurns}
        sessionId={args.claudeSessionId}
        feedAdvertised={args.feedAdvertised}
        lastEvent={args.claudeFeed.lastEvent}
        onIntervene={args.onInterveneClaude}
        interveneDisabled={args.claudeInterveneDisabled}
      />

      <div
        className={`min-h-0 overflow-hidden border-y ${
          args.panelMode ? "lg:border-x lg:border-y-0" : "xl:border-x xl:border-y-0"
        }`}
        style={{ borderColor: colors.sumi[700] + "55" }}
      >
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: colors.sumi[700] + "55" }}>
          <div className="flex items-center gap-2">
            <Activity size={14} className="text-kinpaku" />
            <span className="font-heading text-sm font-semibold text-torinoko">Live Telemetry</span>
          </div>
          <span className="font-mono text-[10px] text-sumi-600">
            {args.telemetry.length} recent events
          </span>
        </div>
        <div className="min-h-0 overflow-y-auto px-4 py-3">
          {args.telemetry.length === 0 ? (
            <div className="flex h-full min-h-[120px] items-center justify-center rounded-2xl border border-dashed border-sumi-700/50 bg-sumi-950/60 text-center text-xs text-sumi-600">
              {args.feedAdvertised
                ? "Session telemetry will appear here once the orchestrators start speaking."
                : "Session rail degraded: /api/chat/status is not advertising chat_ws_path_template, so live telemetry cannot attach."}
            </div>
          ) : (
            <div className="space-y-2">
              {args.telemetry.map((event) => (
                <div
                  key={event.id}
                  className="rounded-2xl border border-sumi-700/35 bg-sumi-950/70 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span
                      className="font-mono text-[10px] uppercase tracking-[0.14em]"
                      style={{ color: telemetryAccent(event.event) }}
                    >
                      {event.headline}
                    </span>
                    <span className="font-mono text-[10px] text-sumi-700">
                      {timeAgo(event.timestamp)}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-sumi-600">{event.detail || "No detail"}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <TelemetryCard
        compact={args.panelMode}
        label={args.codexLabel}
        accent={args.codexAccent}
        connected={args.codexFeed.connected}
        isStreaming={args.codexStreaming}
        snapshotTurns={args.codexFeed.snapshotTurns}
        sessionId={args.codexSessionId}
        feedAdvertised={args.feedAdvertised}
        lastEvent={args.codexFeed.lastEvent}
        onIntervene={args.onInterveneCodex}
        interveneDisabled={args.codexInterveneDisabled}
      />
    </section>
  );
}

function TelemetryCard(args: {
  compact: boolean;
  label: string;
  accent: string;
  connected: boolean;
  isStreaming: boolean;
  snapshotTurns: number;
  sessionId: string;
  feedAdvertised: boolean;
  lastEvent: ChatSessionFeedEvent | null;
  onIntervene: () => void;
  interveneDisabled?: boolean;
}) {
  const connection = buildChatSessionConnectionState({
    sessionId: args.sessionId,
    isStreaming: args.isStreaming,
    wsConnected: args.connected,
    feedAdvertised: args.feedAdvertised,
  });

  return (
    <div className={`min-h-0 overflow-hidden px-4 ${args.compact ? "py-2.5" : "py-3"}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Cable size={14} style={{ color: args.accent }} />
          <span className="font-heading text-sm font-semibold text-torinoko">{args.label}</span>
        </div>
        <button
          onClick={args.onIntervene}
          disabled={args.interveneDisabled}
          className="rounded-lg border border-aozora/30 bg-aozora/10 px-2 py-1 font-mono text-[10px] text-aozora transition-colors hover:bg-aozora/15"
          title={`Stop, focus, and intervene with ${args.label}`}
        >
          Intervene
        </button>
      </div>

      <div className={`mt-3 grid grid-cols-2 gap-2 ${args.compact ? "text-[11px]" : ""}`}>
        <div className="rounded-2xl border border-sumi-700/35 bg-sumi-950/65 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-700">
            Socket
          </div>
          <div className={`mt-1 text-xs ${connectionToneClass(connection.phase)}`}>
            {connection.socketLabel}
          </div>
        </div>
        <div className="rounded-2xl border border-sumi-700/35 bg-sumi-950/65 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-700">
            Stream
          </div>
          <div className={`mt-1 text-xs ${args.isStreaming ? "text-kinpaku" : "text-sumi-600"}`}>
            {args.isStreaming ? "live" : "idle"}
          </div>
        </div>
        <div className="rounded-2xl border border-sumi-700/35 bg-sumi-950/65 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-700">
            Snapshot
          </div>
          <div className="mt-1 text-xs text-torinoko">{args.snapshotTurns} turns</div>
        </div>
        <div className="rounded-2xl border border-sumi-700/35 bg-sumi-950/65 px-3 py-2">
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-700">
            Session
          </div>
          <div className={`mt-1 font-mono text-[10px] ${connectionToneClass(connection.phase)}`}>
            {trimSessionLabel(connection.sessionLabel)}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-2xl border border-sumi-700/35 bg-sumi-950/65 px-3 py-2">
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-sumi-700">
          <ClockLabel />
          Last Event
        </div>
        <div className="mt-2">
          {args.lastEvent ? (
            <>
              <div className="text-xs text-torinoko">{args.lastEvent.headline}</div>
              <div className="mt-1 text-[11px] text-sumi-600">{args.lastEvent.detail}</div>
            </>
          ) : (
            <div className="text-xs text-sumi-600">
              {args.feedAdvertised
                ? "No live events yet."
                : "Session rail degraded: websocket template not advertised."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ClockLabel() {
  return <Radio size={10} className="text-sumi-700" />;
}
