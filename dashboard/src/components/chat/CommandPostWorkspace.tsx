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
  resolveChatProfile,
  shortProfileLabel,
} from "@/lib/chatProfiles";
import { colors } from "@/lib/theme";
import { timeAgo } from "@/lib/utils";

const DEFAULT_PEER_PROFILE_ID = "qwen35_surgeon";
const CODEX_PROFILE_ID = "codex_operator";
const WAIT_AFTER_SEND_MS = 80;

type CommandPostVariant = "page" | "panel";

interface CommandPostWorkspaceProps {
  variant: CommandPostVariant;
  onClose?: () => void;
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

function trimSessionId(sessionId: string): string {
  if (!sessionId) return "pending";
  if (sessionId.length <= 16) return sessionId;
  return `${sessionId.slice(0, 10)}...${sessionId.slice(-4)}`;
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

export function CommandPostWorkspace({
  variant,
  onClose,
}: CommandPostWorkspaceProps) {
  const panelMode = variant === "panel";
  const [peerProfileId, setPeerProfileId] = useState(DEFAULT_PEER_PROFILE_ID);
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
  const claude = useChat(peerProfileId);
  const codex = useChat(CODEX_PROFILE_ID);
  const status = claude.status ?? codex.status ?? null;
  const availableProfiles = getChatProfiles(status);
  const peerProfileOptions = availableProfiles.filter((profile) => profile.id !== CODEX_PROFILE_ID);
  const claudeProfile = resolveChatProfile(status, peerProfileId);
  const codexProfile = resolveChatProfile(status, CODEX_PROFILE_ID);
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
    if (peerProfileOptions.length === 0) return;
    if (peerProfileOptions.some((profile) => profile.id === peerProfileId)) return;
    setPeerProfileId(peerProfileOptions[0].id);
  }, [peerProfileId, peerProfileOptions]);

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
    if (!nextProfileId || nextProfileId === CODEX_PROFILE_ID || nextProfileId === peerProfileId) {
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
    const nextProfile = availableProfiles.find((profile) => profile.id === nextProfileId);
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
          onFocus={() => setProfile(peerProfileId)}
          onClear={claude.clearMessages}
          profileOptions={peerProfileOptions.map((profile) => ({
            id: profile.id,
            label: profile.label,
          }))}
          onProfileChange={switchPeerLane}
        />

        <ControlRail
          bridgeNote={bridgeNote}
          onBridgeNoteChange={setBridgeNote}
          bridgeStatus={bridgeStatus}
          claudeLabel={shortProfileLabel(claudeProfile)}
          codexLabel={shortProfileLabel(codexProfile)}
          claudeDisabled={!claudeRelay || codex.isStreaming || relayBusy !== null}
          codexDisabled={!codexRelay || claude.isStreaming || relayBusy !== null}
          conveneDisabled={
            !claudeRelay || !codexRelay || claude.isStreaming || codex.isStreaming || relayBusy !== null
          }
          primeDisabled={!bridgeNote.trim() || claude.isStreaming || codex.isStreaming || relayBusy !== null}
          loopDisabled={
            !claudeRelay || !codexRelay || claude.isStreaming || codex.isStreaming || relayBusy !== null
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
          onFocus={() => setProfile(CODEX_PROFILE_ID)}
          onClear={codex.clearMessages}
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
        claudeStreaming={claude.isStreaming}
        codexStreaming={codex.isStreaming}
        claudeSessionId={claude.sessionId}
        codexSessionId={codex.sessionId}
        telemetry={telemetry}
        onInterveneClaude={() => intervene(peerProfileId, claudeProfile.label)}
        onInterveneCodex={() => intervene(CODEX_PROFILE_ID, codexProfile.label)}
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
  onFocus: () => void;
  onClear: () => void;
  profileOptions?: Array<{ id: string; label: string }>;
  onProfileChange?: (profileId: string) => void;
}) {
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
            <span>{trimSessionId(args.sessionId)}</span>
            <span className={args.wsConnected ? "text-rokusho" : "text-sumi-700"}>
              {args.wsConnected ? "ws linked" : "ws idle"}
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
          <button
            onClick={args.onClear}
            className="rounded p-1.5 text-sumi-600 transition-colors hover:bg-sumi-800 hover:text-torinoko"
            title={`Clear ${args.label}`}
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        <ChatInterface
          className="h-full"
          compact
          showHeader={false}
          profileId={args.profileId}
          allowProfileSwitch={false}
        />
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
  claudeStreaming: boolean;
  codexStreaming: boolean;
  claudeSessionId: string;
  codexSessionId: string;
  telemetry: ChatSessionFeedEvent[];
  onInterveneClaude: () => void;
  onInterveneCodex: () => void;
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
        lastEvent={args.claudeFeed.lastEvent}
        onIntervene={args.onInterveneClaude}
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
              Session telemetry will appear here once the orchestrators start speaking.
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
        lastEvent={args.codexFeed.lastEvent}
        onIntervene={args.onInterveneCodex}
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
  lastEvent: ChatSessionFeedEvent | null;
  onIntervene: () => void;
}) {
  return (
    <div className={`min-h-0 overflow-hidden px-4 ${args.compact ? "py-2.5" : "py-3"}`}>
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Cable size={14} style={{ color: args.accent }} />
          <span className="font-heading text-sm font-semibold text-torinoko">{args.label}</span>
        </div>
        <button
          onClick={args.onIntervene}
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
          <div className={`mt-1 text-xs ${args.connected ? "text-rokusho" : "text-sumi-600"}`}>
            {args.connected ? "connected" : "waiting"}
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
          <div className="mt-1 font-mono text-[10px] text-torinoko">
            {trimSessionId(args.sessionId)}
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
            <div className="text-xs text-sumi-600">No live events yet.</div>
          )}
        </div>
      </div>
    </div>
  );
}

function ClockLabel() {
  return <Radio size={10} className="text-sumi-700" />;
}
