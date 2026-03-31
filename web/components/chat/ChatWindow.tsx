"use client";

import { useEffect, useRef } from "react";
import { useChatStore } from "@/lib/store";
import { MessageBubble } from "./MessageBubble";
import { Bot } from "lucide-react";

interface ChatWindowProps {
  conversationId: string;
}

export function ChatWindow({ conversationId }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const { conversations } = useChatStore();
  const conversation = conversations.find((c) => c.id === conversationId);
  const messages = conversation?.messages ?? [];

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-4 text-center px-6">
        <div className="w-12 h-12 rounded-full bg-brand-600/20 flex items-center justify-center">
          <Bot className="w-6 h-6 text-brand-400" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-surface-100">How can I help?</h2>
          <p className="text-sm text-surface-400 mt-1">
            Start a conversation with Claude Code
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-3xl mx-auto py-6 px-4 space-y-6">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
