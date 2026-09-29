import React, { useState } from "react";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

interface Props {
  onAuthenticated: () => void;
}

export default function LoginForm({ onAuthenticated }: Props) {
  const [tab, setTab] = useState<"login" | "signup">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const path = tab === "login" ? "/auth/login" : "/auth/signup";
      const body =
        tab === "login"
          ? { email, password }
          : { full_name: fullName, email, password };

      const res = await fetch(`${BASE_URL}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? `${tab === "login" ? "Login" : "Sign up"} failed`);
      }
      const data = await res.json();
      localStorage.setItem("auth_token", data.access_token);
      onAuthenticated();
    } catch (err: any) {
      setError(err.message ?? "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center p-6">
      <div className="mb-4 flex gap-1 rounded border border-slate-300 p-0.5 text-sm">
        <button
          className={`flex-1 rounded px-3 py-1.5 ${tab === "login" ? "bg-slate-800 text-white" : "text-slate-600"}`}
          onClick={() => setTab("login")}
        >
          Log in
        </button>
        <button
          className={`flex-1 rounded px-3 py-1.5 ${tab === "signup" ? "bg-slate-800 text-white" : "text-slate-600"}`}
          onClick={() => setTab("signup")}
        >
          Sign up
        </button>
      </div>

      <form className="space-y-3" onSubmit={handleSubmit}>
        {tab === "signup" && (
          <input
            className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
            placeholder="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            required
          />
        )}
        <input
          type="email"
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          className="w-full rounded border border-slate-300 px-3 py-2 text-sm"
          placeholder="Password (min 8 characters)"
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <button
          type="submit"
          className="w-full rounded bg-slate-800 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          disabled={loading}
        >
          {loading ? "Please wait\u2026" : tab === "login" ? "Log in" : "Create account"}
        </button>
      </form>
      <p className="mt-3 text-xs text-slate-500">
        Talks to the FastAPI backend at <code className="rounded bg-slate-100 px-1">{BASE_URL}</code>. Make sure
        it's running and reachable (check the Vite proxy in dev, or VITE_API_BASE_URL in production).
      </p>
    </div>
  );
}
