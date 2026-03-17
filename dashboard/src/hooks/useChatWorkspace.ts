"use client";

import { create } from "zustand";
import { DEFAULT_CHAT_PROFILE_ID } from "@/lib/chatProfiles";

export type OperatorDock = "floating" | "left" | "right" | "bottom" | "center";

export interface OperatorRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

const DEFAULT_RECT: OperatorRect = {
  x: 920,
  y: 88,
  width: 460,
  height: 620,
};

interface ChatWorkspaceState {
  profileId: string;
  overlayOpen: boolean;
  panelOpen: boolean;
  operatorDock: OperatorDock;
  operatorRect: OperatorRect;
  openOverlay: (profileId?: string) => void;
  closeOverlay: () => void;
  toggleOverlay: (profileId?: string) => void;
  openPanel: (profileId?: string) => void;
  closePanel: () => void;
  togglePanel: (profileId?: string) => void;
  setProfile: (profileId: string) => void;
  setOperatorDock: (dock: OperatorDock) => void;
  setOperatorRect: (rect: OperatorRect) => void;
  resetOperatorRect: () => void;
}

export const useChatWorkspace = create<ChatWorkspaceState>((set) => ({
  profileId: DEFAULT_CHAT_PROFILE_ID,
  overlayOpen: false,
  panelOpen: false,
  operatorDock: "floating",
  operatorRect: DEFAULT_RECT,

  openOverlay: (profileId) =>
    set((state) => ({
      profileId: profileId ?? state.profileId,
      overlayOpen: true,
    })),

  closeOverlay: () => set({ overlayOpen: false }),

  toggleOverlay: (profileId) =>
    set((state) => ({
      profileId: profileId ?? state.profileId,
      overlayOpen: !state.overlayOpen,
    })),

  openPanel: (profileId) =>
    set((state) => ({
      profileId: profileId ?? state.profileId,
      panelOpen: true,
    })),

  closePanel: () => set({ panelOpen: false }),

  togglePanel: (profileId) =>
    set((state) => ({
      profileId: profileId ?? state.profileId,
      panelOpen: !state.panelOpen,
    })),

  setProfile: (profileId) => set({ profileId }),
  setOperatorDock: (dock) => set({ operatorDock: dock }),
  setOperatorRect: (rect) => set({ operatorRect: rect }),
  resetOperatorRect: () =>
    set({
      operatorDock: "floating",
      operatorRect: DEFAULT_RECT,
    }),
}));
