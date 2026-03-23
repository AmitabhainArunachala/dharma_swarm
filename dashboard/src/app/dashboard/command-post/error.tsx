"use client";

export default function CommandPostError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="rounded-2xl border border-bengara/40 bg-sumi-900/80 p-6">
      <h2 className="text-lg font-bold text-bengara">Command Post Error</h2>
      <pre className="mt-3 max-h-[300px] overflow-auto whitespace-pre-wrap rounded bg-sumi-950 p-4 text-xs text-torinoko/80">
        {error.message}
        {"\n\n"}
        {error.stack}
      </pre>
      {error.digest && (
        <p className="mt-2 text-xs text-sumi-500">Digest: {error.digest}</p>
      )}
      <button
        onClick={reset}
        className="mt-4 rounded-lg border border-sumi-700/40 bg-sumi-800 px-4 py-2 text-sm text-torinoko transition-colors hover:bg-sumi-700"
      >
        Retry
      </button>
    </div>
  );
}
