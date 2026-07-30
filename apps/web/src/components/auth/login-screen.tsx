"use client";

import { FormEvent, useState } from "react";
import Image from "next/image";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

export interface LoginScreenProps {
  onSubmit: (username: string, password: string) => void;
  error: string | null;
  pending: boolean;
}

export function LoginScreen({ onSubmit, error, pending }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password) return;
    onSubmit(username.trim(), password);
  }

  return (
    <main className="grid min-h-screen place-items-center bg-[var(--color-bg)] p-6">
      <Card padding="lg" className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <Image src="/Full logo.svg" alt="" width={40} height={40} className="rounded-xl" />
          <div>
            <h1 className="font-display text-xl font-bold">Sign in to Vendrai</h1>
            <p className="mt-1 text-sm text-[var(--color-muted)]">
              Use your workspace credentials to continue.
            </p>
          </div>
        </div>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="username" className="mb-2 block text-sm font-bold">
              Username or email
            </label>
            <Input
              id="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
              autoFocus
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-2 block text-sm font-bold">
              Password
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          {error && (
            <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
              {error}
            </p>
          )}
          <Button type="submit" variant="primary" className="w-full" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
