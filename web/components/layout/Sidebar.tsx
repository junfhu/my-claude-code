"use client";

import { useState } from "react";
import { Plus, MessageSquare, Trash2, Settings } from "lucide-react";
import { useChatStore } from "@/lib/store";
import { cn, formatDate, truncate } from "@/lib/utils";

interface SidebarProps {
  className?: string;
}

export function Sidebar({ className }: SidebarProps) {
  const {
    conversations,
    activeConversationId,
    createConversation,
    setActiveConversation,
    deleteConversation,
  } = useChatStore();

  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <aside
      className={cn(
        "flex flex-col h-full bg-surface-900 border-r border-surface-800 w-64",
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-800">
        <span className="text-sm font-semibold text-surface-100">Claude Code</span>
        <button
          onClick={createConversation}
          className="p-1.5 rounded-md text-surface-400 hover:text-surface-100 hover:bg-surface-800 transition-colors"
          title="New conversation"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Conversation list */}
      <nav className="flex-1 overflow-y-auto py-2">
        {conversations.length === 0 ? (
          <div className="px-4 py-8 text-center text-surface-500 text-sm">
            No conversations yet
          </div>
        ) : (
          conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group relative flex items-center px-3 py-2 mx-2 rounded-md cursor-pointer",
                "hover:bg-surface-800 transition-colors",
                activeConversationId === conv.id && "bg-surface-800"
              )}
              onClick={() => setActiveConversation(conv.id)}
              onMouseEnter={() => setHoveredId(conv.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <MessageSquare className="w-3.5 h-3.5 text-surface-500 flex-shrink-0 mr-2" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-surface-200 truncate">
                  {truncate(conv.title, 30)}
                </p>
                <p className="text-xs text-surface-500">{formatDate(conv.updatedAt)}</p>
              </div>
              {hoveredId === conv.id && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteConversation(conv.id);
                  }}
                  className="p-1 rounded text-surface-500 hover:text-red-400 hover:bg-surface-700 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))
        )}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-surface-800">
        <button className="flex items-center gap-2 text-sm text-surface-400 hover:text-surface-100 transition-colors w-full">
          <Settings className="w-4 h-4" />
          <span>Settings</span>
        </button>
      </div>
    </aside>
  );
}
