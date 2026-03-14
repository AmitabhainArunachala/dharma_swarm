"use client";

/**
 * DHARMA COMMAND -- Tasks page (L2).
 * Task queue with status/priority badges, create task dialog.
 */

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, X } from "lucide-react";
import { useTasks, useCreateTask } from "@/hooks/useTasks";
import { timeAgo } from "@/lib/utils";
import { colors } from "@/lib/theme";
import type { TaskOut } from "@/lib/types";

const statusColors: Record<string, string> = {
  pending: colors.fuji,
  running: colors.kinpaku,
  done: colors.rokusho,
  completed: colors.rokusho,
  failed: colors.bengara,
  cancelled: colors.sumi[600],
};

const priorityConfig: Record<string, { label: string; color: string }> = {
  low: { label: "Low", color: colors.fuji },
  normal: { label: "Normal", color: colors.torinoko },
  high: { label: "High", color: colors.kinpaku },
  urgent: { label: "Urgent", color: colors.bengara },
};

function getPriority(priority: string) {
  return priorityConfig[priority] ?? priorityConfig.normal;
}

export default function TasksPage() {
  const { tasks, isLoading } = useTasks();
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="glow-botan font-heading text-2xl font-bold tracking-tight text-botan">
            Task Queue
          </h1>
          <p className="mt-1 text-sm text-sumi-600">
            {tasks.length} tasks total,{" "}
            {tasks.filter((t) => t.status === "running").length} running
          </p>
        </div>
        <button
          onClick={() => setShowCreateDialog(true)}
          className="flex items-center gap-2 rounded-lg border border-botan/30 bg-botan/10 px-4 py-2 text-sm font-medium text-botan transition-all hover:border-botan/50 hover:bg-botan/20"
        >
          <Plus size={14} />
          Create Task
        </button>
      </div>

      {/* Table */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="glass-panel overflow-hidden"
      >
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <p className="animate-pulse text-sm text-sumi-600">Loading tasks...</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr
                  className="border-b text-[10px] font-semibold uppercase tracking-wider"
                  style={{ borderColor: colors.sumi[700], color: colors.sumi[600] }}
                >
                  <th className="px-5 py-3">Title</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Priority</th>
                  <th className="px-5 py-3">Assigned To</th>
                  <th className="px-5 py-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map((task, i) => (
                  <TaskRow key={task.id} task={task} index={i} />
                ))}
                {tasks.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-sm text-sumi-600">
                      No tasks in queue. Create one to begin.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </motion.div>

      {/* Create dialog */}
      <AnimatePresence>
        {showCreateDialog && (
          <CreateTaskDialog onClose={() => setShowCreateDialog(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task row
// ---------------------------------------------------------------------------

function TaskRow({ task, index }: { task: TaskOut; index: number }) {
  const statusColor = statusColors[task.status] ?? colors.sumi[600];
  const priority = getPriority(task.priority);

  return (
    <motion.tr
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.3, delay: index * 0.04 }}
      className="border-b transition-colors hover:bg-white/[0.02]"
      style={{
        borderColor: `color-mix(in srgb, ${colors.sumi[700]} 30%, transparent)`,
      }}
    >
      <td className="max-w-[300px] truncate px-5 py-3 font-medium text-torinoko">
        {task.title}
      </td>
      <td className="px-5 py-3">
        <span
          className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
          style={{
            color: statusColor,
            backgroundColor: `color-mix(in srgb, ${statusColor} 12%, transparent)`,
            border: `1px solid color-mix(in srgb, ${statusColor} 20%, transparent)`,
          }}
        >
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ backgroundColor: statusColor }}
          />
          {task.status}
        </span>
      </td>
      <td className="px-5 py-3">
        <span
          className="inline-block rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider"
          style={{
            color: priority.color,
            backgroundColor: `color-mix(in srgb, ${priority.color} 12%, transparent)`,
            border: `1px solid color-mix(in srgb, ${priority.color} 20%, transparent)`,
          }}
        >
          {priority.label}
        </span>
      </td>
      <td className="px-5 py-3 text-xs text-kitsurubami">
        {task.assigned_to ?? "--"}
      </td>
      <td className="px-5 py-3 text-xs text-sumi-600">
        {timeAgo(task.created_at)}
      </td>
    </motion.tr>
  );
}

// ---------------------------------------------------------------------------
// Create task dialog
// ---------------------------------------------------------------------------

function CreateTaskDialog({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("normal");
  const createTask = useCreateTask();

  const handleSubmit = () => {
    if (!title.trim()) return;
    createTask.mutate(
      { title, description: description || undefined, priority },
      { onSuccess: () => onClose() },
    );
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ type: "spring", damping: 25, stiffness: 300 }}
        className="fixed left-1/2 top-1/2 z-50 w-[440px] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-sumi-700/40 bg-sumi-900/95 p-6 shadow-2xl backdrop-blur-md"
      >
        <div className="mb-5 flex items-center justify-between">
          <h2 className="font-heading text-lg font-bold text-torinoko">
            Create Task
          </h2>
          <button
            onClick={onClose}
            className="rounded p-1 text-sumi-600 hover:text-torinoko"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Title
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Task title..."
              className="w-full rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-botan/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Description
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the task..."
              rows={3}
              className="w-full resize-none rounded-lg border border-sumi-700/40 bg-sumi-850 px-3 py-2 text-sm text-torinoko placeholder-sumi-600 outline-none transition-colors focus:border-botan/50"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-[0.12em] text-kitsurubami">
              Priority
            </label>
            <div className="flex gap-2">
              {[
                { value: "low", label: "Low" },
                { value: "normal", label: "Normal" },
                { value: "high", label: "High" },
                { value: "urgent", label: "Urgent" },
              ].map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPriority(p.value)}
                  className={`flex-1 rounded-lg border px-3 py-1.5 text-xs font-medium transition-all ${
                    priority === p.value
                      ? "border-botan/40 bg-botan/15 text-botan"
                      : "border-sumi-700/30 text-sumi-600 hover:border-sumi-600/40 hover:text-torinoko"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-sumi-600 hover:text-torinoko"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!title.trim() || createTask.isPending}
            className="flex items-center gap-2 rounded-lg bg-botan/20 px-4 py-2 text-sm font-medium text-botan transition-all hover:bg-botan/30 disabled:opacity-40"
          >
            <Plus size={14} />
            {createTask.isPending ? "Creating..." : "Create"}
          </button>
        </div>

        {createTask.isError && (
          <p className="mt-3 text-xs text-bengara">
            Failed to create task. Check the API server.
          </p>
        )}
      </motion.div>
    </>
  );
}
