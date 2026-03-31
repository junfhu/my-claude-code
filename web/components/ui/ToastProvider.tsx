"use client";

import * as Toast from "@radix-ui/react-toast";
import { createContext, useContext, useState, useCallback } from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ToastMessage {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "destructive";
}

interface ToastContextValue {
  toast: (message: Omit<ToastMessage, "id">) => void;
}

const ToastContext = createContext<ToastContextValue>({ toast: () => {} });

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const toast = useCallback((message: Omit<ToastMessage, "id">) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...message, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  return (
    <ToastContext.Provider value={{ toast }}>
      <Toast.Provider swipeDirection="right">
        {children}
        {toasts.map((t) => (
          <Toast.Root
            key={t.id}
            className={cn(
              "flex items-start gap-3 p-4 rounded-lg shadow-lg border",
              "bg-surface-800 border-surface-700 text-surface-100",
              "data-[state=open]:animate-slide-up",
              t.variant === "destructive" && "border-red-800 bg-red-950"
            )}
            open
          >
            <div className="flex-1">
              <Toast.Title className="text-sm font-medium">{t.title}</Toast.Title>
              {t.description && (
                <Toast.Description className="text-xs text-surface-400 mt-0.5">
                  {t.description}
                </Toast.Description>
              )}
            </div>
            <Toast.Close className="text-surface-500 hover:text-surface-100">
              <X className="w-4 h-4" />
            </Toast.Close>
          </Toast.Root>
        ))}
        <Toast.Viewport className="fixed bottom-4 right-4 flex flex-col gap-2 w-80 z-50" />
      </Toast.Provider>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
