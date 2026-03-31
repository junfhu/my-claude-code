import { create } from "zustand";
import { persist } from "zustand/middleware";
import { nanoid } from "nanoid";
import type { Conversation, Message, AppSettings } from "./types";
import { DEFAULT_MODEL } from "./constants";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  settings: AppSettings;

  // Actions
  createConversation: () => string;
  setActiveConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  addMessage: (conversationId: string, message: Omit<Message, "id" | "createdAt">) => string;
  updateMessage: (conversationId: string, messageId: string, updates: Partial<Message>) => void;
  updateSettings: (settings: Partial<AppSettings>) => void;
  getActiveConversation: () => Conversation | null;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      conversations: [],
      activeConversationId: null,
      settings: {
        theme: "dark",
        model: DEFAULT_MODEL,
        apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3001",
        streamingEnabled: true,
      },

      createConversation: () => {
        const id = nanoid();
        const now = Date.now();
        const conversation: Conversation = {
          id,
          title: "New conversation",
          messages: [],
          createdAt: now,
          updatedAt: now,
          model: get().settings.model,
        };
        set((state) => ({
          conversations: [conversation, ...state.conversations],
          activeConversationId: id,
        }));
        return id;
      },

      setActiveConversation: (id) => {
        set({ activeConversationId: id });
      },

      deleteConversation: (id) => {
        set((state) => {
          const remaining = state.conversations.filter((c) => c.id !== id);
          const nextActive =
            state.activeConversationId === id
              ? (remaining[0]?.id ?? null)
              : state.activeConversationId;
          return { conversations: remaining, activeConversationId: nextActive };
        });
      },

      addMessage: (conversationId, message) => {
        const id = nanoid();
        const now = Date.now();
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: [...c.messages, { ...message, id, createdAt: now }],
                  updatedAt: now,
                }
              : c
          ),
        }));
        return id;
      },

      updateMessage: (conversationId, messageId, updates) => {
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === conversationId
              ? {
                  ...c,
                  messages: c.messages.map((m) =>
                    m.id === messageId ? { ...m, ...updates } : m
                  ),
                  updatedAt: Date.now(),
                }
              : c
          ),
        }));
      },

      updateSettings: (settings) => {
        set((state) => ({
          settings: { ...state.settings, ...settings },
        }));
      },

      getActiveConversation: () => {
        const state = get();
        return (
          state.conversations.find((c) => c.id === state.activeConversationId) ??
          null
        );
      },
    }),
    {
      name: "claude-code-chat",
      partialize: (state) => ({
        conversations: state.conversations,
        activeConversationId: state.activeConversationId,
        settings: state.settings,
      }),
    }
  )
);
