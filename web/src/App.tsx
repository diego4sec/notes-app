import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useAuth } from "react-oidc-context";

import { useApi, type Note } from "./api";

export default function App() {
  const auth = useAuth();

  if (auth.isLoading) return <Centered>Loading…</Centered>;
  if (auth.error) return <Centered>Sign-in failed: {auth.error.message}</Centered>;

  if (!auth.isAuthenticated) {
    return (
      <Centered>
        <h1 className="mb-6 text-2xl font-semibold">Notes</h1>
        <button
          onClick={() => void auth.signinRedirect()}
          className="rounded bg-slate-900 px-5 py-2 text-white hover:bg-slate-700"
        >
          Sign in
        </button>
      </Centered>
    );
  }

  return <Notes />;
}

function Notes() {
  const auth = useAuth();
  const api = useApi();
  const qc = useQueryClient();

  const [q, setQ] = useState("");
  const [tag, setTag] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (tag) params.set("tag", tag);

  const notes = useQuery({
    queryKey: ["notes", q, tag],
    queryFn: () => api<Note[]>(`/notes?${params}`),
  });
  const tags = useQuery({ queryKey: ["tags"], queryFn: () => api<string[]>("/tags") });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ["notes"] });
    void qc.invalidateQueries({ queryKey: ["tags"] });
  };

  const create = useMutation({
    mutationFn: () =>
      api<Note>("/notes", { method: "POST", body: JSON.stringify({ title: "Untitled" }) }),
    onSuccess: (note) => {
      setSelected(note.id);
      invalidate();
    },
  });

  const save = useMutation({
    mutationFn: ({ id, ...patch }: Partial<Note> & { id: string }) =>
      api<Note>(`/notes/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api<null>(`/notes/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      setSelected(null);
      invalidate();
    },
  });

  const current = notes.data?.find((n) => n.id === selected) ?? null;

  return (
    <div className="flex h-screen text-slate-800">
      <aside className="flex w-80 flex-col border-r bg-slate-50">
        <div className="flex items-center justify-between border-b p-3">
          <span className="truncate text-sm text-slate-500">
            {auth.user?.profile.email ?? auth.user?.profile.preferred_username}
          </span>
          <button
            onClick={() => void auth.signoutRedirect()}
            className="text-sm text-slate-500 hover:text-slate-900"
          >
            Sign out
          </button>
        </div>

        <div className="space-y-2 border-b p-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search"
            className="w-full rounded border px-2 py-1"
          />
          {tags.data && tags.data.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {tags.data.map((t) => (
                <button
                  key={t}
                  onClick={() => setTag(tag === t ? null : t)}
                  className={`rounded-full px-2 py-0.5 text-xs ${
                    tag === t ? "bg-slate-900 text-white" : "bg-slate-200"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={() => create.mutate()}
            className="w-full rounded bg-slate-900 px-3 py-1.5 text-sm text-white hover:bg-slate-700"
          >
            New note
          </button>
        </div>

        <ul className="flex-1 overflow-y-auto">
          {notes.data?.map((n) => (
            <li key={n.id}>
              <button
                onClick={() => setSelected(n.id)}
                className={`w-full border-b p-3 text-left ${
                  n.id === selected ? "bg-white" : "hover:bg-slate-100"
                }`}
              >
                <div className="truncate font-medium">{n.title}</div>
                <div className="truncate text-xs text-slate-500">{n.body || "No content"}</div>
              </button>
            </li>
          ))}
          {notes.data?.length === 0 && (
            <li className="p-3 text-sm text-slate-500">Nothing here yet.</li>
          )}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto">
        {current ? (
          <Editor
            key={current.id}
            note={current}
            onSave={(patch) => save.mutate({ id: current.id, ...patch })}
            onDelete={() => remove.mutate(current.id)}
            saving={save.isPending}
          />
        ) : (
          <Centered>Select a note, or create one.</Centered>
        )}
      </main>
    </div>
  );
}

function Editor({
  note,
  onSave,
  onDelete,
  saving,
}: {
  note: Note;
  onSave: (patch: { title: string; body: string; tags: string[] }) => void;
  onDelete: () => void;
  saving: boolean;
}) {
  const [title, setTitle] = useState(note.title);
  const [body, setBody] = useState(note.body);
  const [tagText, setTagText] = useState(note.tags.join(", "));

  // The list refetches after a save and hands back a new object. Re-sync so the
  // editor shows the server's truth rather than drifting from it.
  useEffect(() => {
    setTitle(note.title);
    setBody(note.body);
    setTagText(note.tags.join(", "));
  }, [note.updated_at]);

  const dirty =
    title !== note.title || body !== note.body || tagText !== note.tags.join(", ");

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-3 p-6">
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="rounded border px-3 py-2 text-xl font-semibold"
      />
      <input
        value={tagText}
        onChange={(e) => setTagText(e.target.value)}
        placeholder="Tags, comma separated"
        className="rounded border px-3 py-1.5 text-sm"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={20}
        className="rounded border px-3 py-2 font-mono text-sm"
      />
      <div className="flex items-center gap-3">
        <button
          disabled={!dirty || saving || title.trim() === ""}
          onClick={() =>
            onSave({
              title: title.trim(),
              body,
              tags: [
                ...new Set(
                  tagText
                    .split(",")
                    .map((t) => t.trim().toLowerCase())
                    .filter(Boolean),
                ),
              ],
            })
          }
          className="rounded bg-slate-900 px-4 py-1.5 text-white disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onDelete} className="text-sm text-red-600 hover:underline">
          Delete
        </button>
        <span className="ml-auto text-xs text-slate-400">
          Updated {new Date(note.updated_at).toLocaleString()}
        </span>
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-screen flex-col items-center justify-center text-slate-600">
      {children}
    </div>
  );
}
